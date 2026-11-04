"""Control for the prize minted during the vote: how much do undisputed markets mint between an answer's proposal and
the end of its two-hour liveness, when the market is about to settle without a vote?

Sample, matched in time to the disputed markets: for each standard-adapter market-round of prize_growth.csv we take the
proposals that Polymarket's standard adapters received within two hours of that market's escalating dispute
(0x6a9d... and 0x157c... on OOv2, 0x6507... on the managed OO), keep Yes or No proposals that were not disputed, derive
each market (conditionId from the adapter and the question's ancillary data), and keep markets whose Gamma volume is at
least $50,000, at most eight per window, largest first. For each: open interest (PositionSplit minus PositionsMerge) at
the proposal block and at the block of the liveness's end. For the disputed markets, the same measure two hours after
the escalating dispute, so that the two rates compare like for like, beside the growth over the whole vote.

Outputs data/undisputed_control.csv and data/undisputed_control_summary.json.
"""
import csv
import json
import os
import statistics as st
from concurrent.futures import ThreadPoolExecutor

import pm_markets as pm
import requests
from abi_min import decode_data, event_topic, keccak256
from capture_economics import T_MERGE, T_SPLIT, amount_of, logs_by_cond, preparation_block
from prize_growth import block_at_or_before, block_ts, oi_events

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "raw", "control_cache")
os.makedirs(CACHE, exist_ok=True)
OOS = ["0xeE3Afe347D5C74317041E2618C49534dAf887c24", "0x2c0367a9db231ddebd88a94b4f6461a6e47c58b1"]
ADAPTERS = ["0x6a9d222616c90fca5754cd1333cfd9b7fb6a4f74", "0x157ce2d672854c848c9b79c49a8cc6cc89176a49",
            "0x65070be91477460d8a7aeeb94ef92fe056c2f2a7"]
T_PROPOSE = event_topic("ProposePrice(address,address,bytes32,uint256,bytes,int256,uint256,address)")
T_DISPUTE = event_topic("DisputePrice(address,address,address,bytes32,uint256,bytes,int256)")
MIN_VOLUME, PER_WINDOW, HALF = 50_000, 8, 2 * 3600


def as_bytes(x):
    return bytes.fromhex(x[2:]) if isinstance(x, str) else bytes(x)


def topic_addr(a):
    return "0x" + a.lower().replace("0x", "").rjust(64, "0")


def window_logs(topic0, b0, b1):
    key = os.path.join(CACHE, f"{topic0[:10]}_{b0}_{b1}.json")
    if os.path.exists(key):
        return json.load(open(key))
    out, b, span = [], b0, 50_000
    while b <= b1:
        e = min(b + span - 1, b1)
        try:
            out += pm.rpc("eth_getLogs", [{"address": OOS, "topics": [topic0, [topic_addr(a) for a in ADAPTERS]],
                                           "fromBlock": hex(b), "toBlock": hex(e)}])
        except RuntimeError:
            if span > 2_000:
                span //= 5
                continue
            raise
        b = e + 1
    json.dump(out, open(key, "w"))
    return out


VOL_PATH = os.path.join(CACHE, "gamma_volumes.json")
VOL = json.load(open(VOL_PATH)) if os.path.exists(VOL_PATH) else {}


def gamma_volumes(conds):
    """conditionId -> (volume, question) from Gamma's market list, forty conditions per request, cached."""
    todo = [c for c in conds if c not in VOL]
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        j = None
        for attempt in range(5):
            try:
                j = requests.get("https://gamma-api.polymarket.com/markets",
                                 params=[("condition_ids", c) for c in batch] + [("closed", "true"), ("limit", 100)],
                                 timeout=60).json()
                break
            except Exception:  # noqa: BLE001
                pass
        found = {}
        for m in (j or []):
            found[(m.get("conditionId") or "").lower()] = (float(m.get("volumeNum") or 0), (m.get("question") or "")[:80])
        for c in batch:
            VOL[c] = found.get(c, (0.0, ""))
    json.dump(VOL, open(VOL_PATH, "w"))
    return {c: VOL[c] for c in conds}


def oi_path(cond, fb, tb):
    ev = []
    for topic, sign in ((T_SPLIT, 1), (T_MERGE, -1)):
        for lg in logs_by_cond(topic, cond, fb, tb):
            ev.append((int(lg["blockNumber"], 16), sign * amount_of(lg) / 1e6))
    return sorted(ev)


def at(ev, b):
    return sum(a for bb, a in ev if bb <= b)


def main():
    disp = [r for r in csv.DictReader(open(os.path.join(DATA, "prize_growth.csv"), encoding="utf-8"))
            if r["status"] == "ok" and r["negRisk"] not in ("True", "true", "1")]
    # disputed side: two hours after the escalating dispute
    drows = []
    for r in disp:
        ev = oi_events(r["conditionId"], *next((e["prep_block"], e["round_end_block"]) for e in csv.DictReader(
            open(os.path.join(DATA, "capture_economics.csv"), encoding="utf-8"))
            if e["roundId"] == r["roundId"] and e["conditionId"] == r["conditionId"]))
        esc = int(r["esc_block"])
        b2 = block_at_or_before(int(r["t_esc"]) + 7200)
        drows.append({"conditionId": r["conditionId"], "oi_esc": at(ev, esc), "oi_esc_2h": at(ev, b2),
                      "oi_first_end": float(r["oi_first_end"]), "title": r["title"]})
    # undisputed side: proposals within two hours of each escalation; markets are chosen window by window, then their
    # open interest is read in parallel
    seen, chosen = set(), []
    for i, r in enumerate(disp):
        t = int(r["t_esc"])
        b0, b1 = block_at_or_before(t - HALF), block_at_or_before(t + HALF)
        props = window_logs(T_PROPOSE, b0, b1)
        disps = window_logs(T_DISPUTE, b0, block_at_or_before(t + HALF + 3 * 3600))
        disputed = set()
        for lg in disps:
            f = decode_data(["bytes32", "uint256", "bytes", "int256"], lg["data"])
            disputed.add((lg["topics"][1].lower(), int(f[1]), keccak256(as_bytes(f[2])).hex()))
        pre = []
        for lg in props:
            f = decode_data(["bytes32", "uint256", "bytes", "int256", "uint256", "address"], lg["data"])
            requester = "0x" + lg["topics"][1][-40:].lower()
            anc, price, expiry = as_bytes(f[2]), int(f[3]), int(f[4])
            if price not in (0, 10 ** 18):
                continue
            if (lg["topics"][1].lower(), int(f[1]), keccak256(anc).hex()) in disputed:
                continue
            qid = keccak256(anc)
            cond = "0x" + keccak256(bytes.fromhex(requester[2:]) + qid + (2).to_bytes(32, "big")).hex()
            if cond in seen:
                continue
            pre.append((cond, int(lg["blockNumber"], 16), expiry))
        vols = gamma_volumes(sorted({c for c, _, _ in pre}))
        cands = sorted({(vols[c][0], c, bp, ex, vols[c][1]) for c, bp, ex in pre if vols[c][0] >= MIN_VOLUME}, reverse=True)
        for vol, cond, bp, expiry, q in cands[:PER_WINDOW]:
            seen.add(cond)
            chosen.append((vol, cond, bp, expiry, q, r["conditionId"]))
        print(f"{i+1}/{len(disp)} window around {r['title'][:40]!r}: {len(cands)} candidates, kept {min(len(cands), PER_WINDOW)}",
              flush=True)

    def one(c):
        vol, cond, bp, expiry, q, disputed_cond = c
        be = block_at_or_before(expiry)
        prep = preparation_block(cond, bp)
        if prep is None:
            return None
        ev = oi_path(cond, prep, be)
        return {"conditionId": cond, "title": (q or "")[:80], "volume": vol, "window_of": disputed_cond,
                "proposal_block": bp, "liveness_end_block": be, "liveness_hours": (expiry - block_ts(bp)) / 3600,
                "oi_proposal": at(ev, bp), "oi_liveness_end": at(ev, be)}

    def write(name, rows):
        if rows:
            with open(os.path.join(DATA, name), "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

    write("undisputed_control_disputed.csv", drows)
    urows = []
    with ThreadPoolExecutor(8) as pool:
        for k, row in enumerate(pool.map(one, chosen)):
            if row:
                urows.append(row)
            if (k + 1) % 20 == 0 or k + 1 == len(chosen):
                write("undisputed_control.csv", urows)
                print(f"open interest read for {k+1}/{len(chosen)} markets", flush=True)

    def growth(rows, a, b, floor=10_000):
        g = [r[b] / r[a] for r in rows if r[a] >= floor]
        return {"n": len(g), "median": st.median(g) if g else None,
                "p90": sorted(g)[int(0.9 * (len(g) - 1))] if g else None,
                "share_minted_total": (1 - sum(r[a] for r in rows if r[a] >= floor) / sum(r[b] for r in rows if r[a] >= floor))
                if g else None}
    summ = {"undisputed_liveness": growth(urows, "oi_proposal", "oi_liveness_end"),
            "disputed_first_2h": growth(drows, "oi_esc", "oi_esc_2h"),
            "disputed_vote": growth(drows, "oi_esc", "oi_first_end"),
            "undisputed_n_all": len(urows), "undisputed_liveness_hours_median": st.median(r["liveness_hours"] for r in urows) if urows else None,
            "undisputed_volume_median": st.median(r["volume"] for r in urows) if urows else None}
    json.dump(summ, open(os.path.join(DATA, "undisputed_control_summary.json"), "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
