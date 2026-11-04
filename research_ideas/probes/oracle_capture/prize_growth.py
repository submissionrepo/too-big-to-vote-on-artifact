"""When was the prize minted? Open interest of each contested Polymarket market at three moments: when the vote that
decides its payout was called (the Polygon block of the dispute that escalated that request; payout_votes.py), at the
end of that request's first voting round, and
at the end of the round that resolved it; plus the same market one vote-length before the escalation, as a
within-market control.

Escalation block: hash-era requests carry the Polygon block of the dispute that sent them to Ethereum in their DVM
text (polygon_dispute_map.csv). For the others we find that dispute directly: the DisputePrice log of the optimistic
oracle whose requester is the market's adapter, whose timestamp is the DVM request time (the adapter re-requests after
a first dispute, so the escalated request carries the reset time) and whose ancillary data is the DVM text.
First round = resolving round - rollCount (requests_summary.csv). Open interest = PositionSplit minus PositionsMerge
of the conditionId up to a block (the same cached logs as capture_economics.py).

Outputs data/prize_growth.csv and data/prize_growth_summary.json.
"""
import csv
import json
import os
import re
import statistics as st

import payout_votes
import pm_markets as pm
from abi_min import event_topic, keccak256

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ECON = os.path.join(DATA, "raw", "econ_cache")
CACHE = os.path.join(DATA, "raw", "prize_cache")
os.makedirs(CACHE, exist_ok=True)
ROUND = 172_800
T_DISPUTE = event_topic("DisputePrice(address,address,address,bytes32,uint256,bytes,int256)")
OOV2 = "0xeE3Afe347D5C74317041E2618C49534dAf887c24"
MOOV2 = "0x2c0367a9db231ddebd88a94b4f6461a6e47c58b1"
T_SPLIT, T_MERGE = "0x2e6bb91f", "0x6f13ca62"
MU = 0.2
TS_PATH = os.path.join(CACHE, "block_ts.json")
TS = {int(k): v for k, v in json.load(open(TS_PATH)).items()} if os.path.exists(TS_PATH) else {}
for k, v in json.load(open(os.path.join(ECON, "polygon_block_ts.json"))).items():
    TS.setdefault(int(k), v)


def block_ts(b):
    if b not in TS:
        TS[b] = int(pm.rpc("eth_getBlockByNumber", [hex(b), False])["timestamp"], 16)
    return TS[b]


def block_at_or_before(t):
    """Last Polygon block with timestamp <= t (bisection seeded by the cached points)."""
    pts = sorted(TS.items())
    lo = max((p for p in pts if p[1] <= t), default=None)
    hi = min((p for p in pts if p[1] > t), default=None)
    if lo is None:
        lo = (40_000_000, block_ts(40_000_000))
    if hi is None:
        latest = int(pm.rpc("eth_blockNumber", []), 16)
        hi = (latest, block_ts(latest))
    a, b = lo[0], hi[0]
    while b - a > 1:
        g = a + int((t - TS[a]) * (b - a) / max(TS[b] - TS[a], 1))
        g = min(max(g, a + 1), b - 1)
        if block_ts(g) <= t:
            a = g
        else:
            b = g
    return a


def escalation_block(t_req, dvm_anc):
    """Polygon block of the dispute that sent the request to the DVM. For the event-based requests Polymarket's adapters
    make, the optimistic oracle stamps the DVM request with the time of the disputed proposal, so the dispute is the
    first DisputePrice log after that time (within a day) of the oracle named in the DVM text (childRequester, else
    either known oracle) whose requester is the ooRequester and whose ancillary data is the DVM text cut before
    ",ooRequester:"."""
    text = dvm_anc.decode("utf-8", "replace")
    m_req = re.search(r"ooRequester:([0-9a-fA-F]{40})", text)
    m_oo = re.search(r"childRequester:([0-9a-fA-F]{40})", text)
    if not m_req:
        return None
    key = os.path.join(CACHE, f"dispute2_{t_req}_{m_req.group(1)[:10]}_{keccak256(dvm_anc).hex()[:12]}.json")
    if os.path.exists(key):
        return json.load(open(key))["block"]
    cut = dvm_anc.find(b",ooRequester:")
    prefix = dvm_anc[:cut] if cut > 0 else dvm_anc
    oos = ["0x" + m_oo.group(1)] if m_oo else [OOV2, MOOV2]
    fb = block_at_or_before(t_req) - 10
    tb = block_at_or_before(t_req + 86_400)
    topic1 = "0x" + m_req.group(1).lower().rjust(64, "0")
    found = None
    for oo in oos:
        b0, span = fb, 400_000
        while b0 <= tb and found is None:
            b1 = min(b0 + span - 1, tb)
            logs = pm.rpc("eth_getLogs", [{"address": oo, "topics": [T_DISPUTE, topic1], "fromBlock": hex(b0), "toBlock": hex(b1)}])
            for lg in logs:
                data = bytes.fromhex(lg["data"][2:])
                if prefix in data:
                    found = int(lg["blockNumber"], 16)
                    break
            b0 = b1 + 1
        if found:
            break
    json.dump({"block": found}, open(key, "w"))
    return found


def oi_events(cond, fb, tb):
    ev = []
    for topic, sign in ((T_SPLIT, 1), (T_MERGE, -1)):
        p = os.path.join(ECON, f"{topic}_{cond[:18]}_{fb}_{tb}.json")
        if not os.path.exists(p):
            return None
        for lg in json.load(open(p)):
            a = int.from_bytes(bytes.fromhex(lg["data"][2:])[64:96], "big") / 1e6
            ev.append((int(lg["blockNumber"], 16), sign * a))
    return sorted(ev)


def oi_at(ev, b):
    return sum(a for bb, a in ev if bb <= b)


def main():
    pts = list(csv.DictReader(open(os.path.join(DATA, "capture_economics_points.csv"), encoding="utf-8")))
    econ = {(r["roundId"], r["conditionId"]): r for r in csv.DictReader(open(os.path.join(DATA, "capture_economics.csv"), encoding="utf-8"))}
    reqs = {(r["roundId"], r["requestTime"], r["ancKey"]): r for r in csv.DictReader(open(os.path.join(DATA, "requests_summary.csv"), encoding="utf-8"))}
    dmap = {}
    for r in csv.DictReader(open(os.path.join(DATA, "polygon_dispute_map.csv"), encoding="utf-8")):
        if r["childBlock"]:
            dmap.setdefault(r["requestTime"], set()).add(int(r["childBlock"]))
    anc_by_key = {(tt, ak): v for (ident, tt, ak), v in pm.load_ancillary().items()}
    by_mr = {}
    roles = payout_votes.roles()
    for r in csv.DictReader(open(os.path.join(DATA, "capture_economics.csv"), encoding="utf-8")):
        # the vote that decides the payout: a first dispute's vote only settles the dispute's bonds
        if r.get("conditionId") and payout_votes.is_payout(r, roles):
            by_mr.setdefault((r["roundId"], r["conditionId"]), []).append((r["requestTime"], r["ancKey"]))
    rows = []
    for i, p in enumerate(pts):
        e = econ.get((p["roundId"], p["conditionId"]))
        q = reqs.get((p["roundId"], p["requestTime"], p["ancKey"]))
        if not e or not q or not e.get("prep_block"):
            continue
        t_req, rid = int(p["requestTime"]), int(p["roundId"])
        rolls = int(float(q["rollCount"] or 0))
        first = rid - rolls
        # the payout vote's escalation (one payout request per market and round; the latest if there were several)
        escs = []
        for tq, ak in by_mr.get((p["roundId"], p["conditionId"]), [(p["requestTime"], p["ancKey"])]):
            cands = dmap.get(tq, set())
            anc = anc_by_key.get((int(tq), ak))
            if len(cands) == 1:
                escs.append(next(iter(cands)))
            elif anc is not None:
                b = escalation_block(int(tq), anc)
                if b:
                    escs.append(b)
        esc = max(escs) if escs else None
        ev = oi_events(p["conditionId"], e["prep_block"], e["round_end_block"])
        if ev is None or esc is None:
            rows.append({"roundId": rid, "conditionId": p["conditionId"], "title": p["title"], "status": "no-esc" if ev else "no-oi"})
            continue
        t_esc = block_ts(esc)
        t_first_end = (first + 1) * ROUND
        b_first_end = block_at_or_before(t_first_end)
        b_end = int(e["round_end_block"])
        b_pre = block_at_or_before(t_esc - (t_first_end - t_esc))
        S, px, V_F = float(p["S"]), float(p["uma_price"]), float(p["V_F"])
        V = S * px
        row = {"roundId": rid, "firstRound": first, "rollCount": rolls, "requestTime": t_req, "conditionId": p["conditionId"],
               "title": p["title"], "negRisk": e.get("negRisk"), "era": p["era"], "F": p["F"], "sigma_F": float(p["sigma_F"]),
               "esc_block": esc, "t_esc": t_esc, "t_first_end": t_first_end, "vote_hours": (t_first_end - t_esc) / 3600,
               "oi_pre": oi_at(ev, b_pre), "oi_esc": oi_at(ev, esc), "oi_first_end": oi_at(ev, b_first_end),
               "oi_end": oi_at(ev, b_end), "V_F": V_F, "V": V, "status": "ok"}
        row["delta_F_esc"] = row["oi_esc"] / V_F if V_F else None
        row["delta_F_first"] = row["oi_first_end"] / V_F if V_F else None
        row["dreq_esc"] = row["oi_esc"] / ((1 - 2 * MU) * V)
        row["dreq_first"] = row["oi_first_end"] / ((1 - 2 * MU) * V)
        rows.append(row)
        print(f"{i+1}/{len(pts)} {p['title'][:46]:46s} pre {row['oi_pre']:>12,.0f} esc {row['oi_esc']:>12,.0f} "
              f"first {row['oi_first_end']:>12,.0f} end {row['oi_end']:>12,.0f}", flush=True)
    json.dump({str(k): v for k, v in TS.items()}, open(TS_PATH, "w"))
    keys = sorted({k for r in rows for k in r})
    with open(os.path.join(DATA, "prize_growth.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    ok = [r for r in rows if r["status"] == "ok"]
    std = [r for r in ok if str(r["negRisk"]) not in ("True", "true", "1")]

    def summ(rs):
        big = sorted(rs, key=lambda r: -r["oi_first_end"])[:20]
        tot_esc, tot_first = sum(r["oi_esc"] for r in rs), sum(r["oi_first_end"] for r in rs)
        return {"n": len(rs), "oi_pre_total": sum(r["oi_pre"] for r in rs), "oi_esc_total": tot_esc,
                "oi_first_total": tot_first, "oi_end_total": sum(r["oi_end"] for r in rs),
                "share_after_esc_total": 1 - tot_esc / tot_first if tot_first else None,
                "share_after_esc_top20_median": st.median(1 - r["oi_esc"] / r["oi_first_end"] for r in big if r["oi_first_end"] > 0),
                "growth_pre_to_esc_top20_median": st.median((r["oi_esc"] / r["oi_pre"]) if r["oi_pre"] > 0 else float("inf") for r in big),
                "growth_esc_to_first_top20_median": st.median((r["oi_first_end"] / r["oi_esc"]) if r["oi_esc"] > 0 else float("inf") for r in big),
                "vote_hours_median": st.median(r["vote_hours"] for r in rs),
                "deltaF_ge1_esc": sum(1 for r in rs if r["delta_F_esc"] and r["delta_F_esc"] >= 1),
                "deltaF_ge1_first": sum(1 for r in rs if r["delta_F_first"] and r["delta_F_first"] >= 1),
                "deltaF_ge01_esc": sum(1 for r in rs if r["delta_F_esc"] and r["delta_F_esc"] >= 0.1),
                "deltaF_ge01_first": sum(1 for r in rs if r["delta_F_first"] and r["delta_F_first"] >= 0.1),
                "dreq_ge1_esc": sum(1 for r in rs if r["dreq_esc"] >= 1), "dreq_ge1_first": sum(1 for r in rs if r["dreq_first"] >= 1),
                "dreq_ge014_esc": sum(1 for r in rs if r["dreq_esc"] >= 0.14), "dreq_ge014_first": sum(1 for r in rs if r["dreq_first"] >= 0.14),
                "dreq_gepen_esc": sum(1 for r in rs if r["dreq_esc"] >= 0.001), "dreq_gepen_first": sum(1 for r in rs if r["dreq_first"] >= 0.001)}
    out = {"all": summ(ok), "standard": summ(std), "missing": [r["title"] for r in rows if r["status"] != "ok"],
           "rolled_first_ne_resolving": sum(1 for r in ok if r["rollCount"] > 0)}
    cf = [r for r in ok if r["conditionId"].startswith("0x9823d715")]
    out["ceasefire"] = cf[0] if cf else None
    json.dump(out, open(os.path.join(DATA, "prize_growth_summary.json"), "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in out.items() if k != "ceasefire"}, indent=1, default=str))


if __name__ == "__main__":
    main()
