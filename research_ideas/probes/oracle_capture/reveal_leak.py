"""The vote publishes its answer before the round ends. For every contested Polymarket resolution whose winner was a
side (Yes or No), find the reveal at which the winner's revealed stake first exceeded theta * S. From that block on no
other answer can reach the line (theta >= 1/2 against the whole staked supply) and the participation floor is met, so
the outcome is fixed and readable on-chain, while the round, the bridge and the market's settlement are still ahead.
Compare with the market: the price of the winning side at that moment, at the round's end, and when it first reached
0.95.

Inputs: data/contested_requests.csv, data/requests_summary.csv, data/votes_long.csv,
        data/capture_economics.csv (conditionIds), data/raw/pm_cache/gamma_*.json (token ids).
Writes data/reveal_leak.csv and data/reveal_leak_summary.json; caches in data/raw/leak_cache/.
"""
import csv
import glob
import json
import os
import statistics as st
import time

import requests

import payout_votes
from reqkey import req_key

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "raw", "leak_cache")
os.makedirs(CACHE, exist_ok=True)
SPAT_CHANGE_BLOCK = 22309220
ROUND = 172_800
ETH_EP = "https://ethereum-rpc.publicnode.com"


def eth_block_time(b):
    path = os.path.join(CACHE, f"eth_ts_{b}.json")
    if os.path.exists(path):
        return json.load(open(path))["t"]
    for attempt in range(6):
        try:
            j = requests.post(ETH_EP, json={"jsonrpc": "2.0", "id": 1, "method": "eth_getBlockByNumber",
                                            "params": [hex(b), False]}, timeout=60).json()
            t = int(j["result"]["timestamp"], 16)
            json.dump({"t": t}, open(path, "w"))
            return t
        except Exception:  # noqa: BLE001
            time.sleep(1 + attempt)
    return None


def minute_prices(token, t0, t1):
    path = os.path.join(CACHE, f"px_{token[:20]}_{t0}_{t1}.json")
    if os.path.exists(path):
        return json.load(open(path))
    for attempt in range(5):
        try:
            j = requests.get("https://clob.polymarket.com/prices-history",
                             params={"market": token, "startTs": t0, "endTs": t1, "fidelity": 1}, timeout=60).json()
            h = [(x["t"], x["p"]) for x in j.get("history", [])]
            json.dump(h, open(path, "w"))
            time.sleep(0.2)
            return h
        except Exception:  # noqa: BLE001
            time.sleep(1.5 + attempt)
    return []


def main():
    reqs = {req_key(r): r for r in csv.DictReader(open(os.path.join(DATA, "requests_summary.csv"), encoding="utf-8"))}
    roles = payout_votes.roles(list(reqs.values()))
    # only votes that decide a payout: a question's first dispute is voted on too, but it only settles the bonds
    cont = [c for c in csv.DictReader(open(os.path.join(DATA, "contested_requests.csv"), encoding="utf-8"))
            if c["isPolymarket"] == "True" and c["winner"] in ("p1", "p2") and payout_votes.is_payout(c, roles)]
    econ = {req_key(r): r for r in csv.DictReader(open(os.path.join(DATA, "capture_economics.csv"), encoding="utf-8"))
            if r["status"] == "ok"}
    keys = {req_key(c) for c in cont}
    votes = {k: [] for k in keys}
    with open(os.path.join(DATA, "votes_long.csv"), encoding="utf-8") as f:
        rd = csv.reader(f)
        h = next(rd)
        iR, iT, iP, iN, iB, iA = (h.index(x) for x in ("roundId", "requestTime", "price", "numTokens", "block", "ancKey"))
        for row in rd:
            k = (row[iR], row[iT], row[iA])
            if k in votes:
                votes[k].append((int(row[iB]), row[iP], float(row[iN])))
    rows = []
    for c in cont:
        k = req_key(c)
        r = reqs[k]
        e = econ.get(k)
        theta = 0.5 if int(r["resolvedBlock"]) < SPAT_CHANGE_BLOCK else 0.65
        S = float(r["cumulativeStakeAtRound"])
        cum, cross = 0.0, None
        for b, p, n in sorted(votes[k]):
            if p == c["winner"]:
                cum += n
                if cum > theta * S:
                    cross = b
                    break
        base = {"roundId": c["roundId"], "requestTime": c["requestTime"], "ancKey": c["ancKey"], "winner": c["winner"],
                "winnerShareOfStaked": c["winnerShareOfStaked"], "k": c["kSupportersWhoseRemovalRolls"]}
        if cross is None or e is None:
            rows.append({**base, "status": "no-cross" if cross is None else "no-market"})
            continue
        t_cross = eth_block_time(cross)
        t_end = (int(c["roundId"]) + 1) * ROUND
        g = glob.glob(os.path.join(DATA, "raw", "pm_cache", f"gamma_{e['conditionId'][:24]}.json"))
        gm = json.load(open(g[0], encoding="utf-8")) if g else []
        toks = json.loads(gm[0]["clobTokenIds"]) if gm and isinstance(gm[0].get("clobTokenIds"), str) else (gm[0].get("clobTokenIds") if gm else None)
        if not toks:
            rows.append({**base, "status": "no-token", "title": e["title"]})
            continue
        tok = toks[0] if c["winner"] == "p2" else toks[1]
        hist = minute_prices(tok, t_cross - 3600, t_end + 6 * 3600)
        if not hist:
            rows.append({**base, "status": "no-prices", "title": e["title"]})
            continue
        before = [p for t, p in hist if t <= t_cross]
        at_end = [p for t, p in hist if t <= t_end]
        p_cross = before[-1] if before else hist[0][1]
        p_end = at_end[-1] if at_end else None
        t95 = next((t for t, p in hist if t >= t_cross and p >= 0.95), None)
        rows.append({**base, "status": "ok", "title": e["title"], "conditionId": e["conditionId"], "oi": e["oi_usdc"],
                     "cross_block": cross, "t_cross": t_cross, "t_end": t_end, "lead_min": round((t_end - t_cross) / 60, 1),
                     "p_cross": p_cross, "p_end": p_end, "t95": t95,
                     "min_to_95": round((t95 - t_cross) / 60, 1) if t95 else None,
                     "p95_after_end": (t95 is None or t95 > t_end)})
        x = rows[-1]
        print(f"{x['title'][:44]:44s} lead {x['lead_min']:7.1f} min  p_cross {p_cross:.3f}  p_end {p_end}  to95 {x['min_to_95']}", flush=True)
    keys_out = sorted({kk for r in rows for kk in r})
    with open(os.path.join(DATA, "reveal_leak.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys_out)
        w.writeheader()
        w.writerows(rows)
    # one row per market and round (a market voted twice in a round counts once, by its earlier crossing)
    best = {}
    for x in rows:
        if x["status"] != "ok":
            continue
        kk = (x["roundId"], x["conditionId"])
        if kk not in best or x["t_cross"] < best[kk]["t_cross"]:
            best[kk] = x
    ok = list(best.values())
    leads = sorted(x["lead_min"] for x in ok)
    pc = sorted(x["p_cross"] for x in ok)
    summ = {"n_sided_contested_requests": len(cont), "status_counts": {s: sum(1 for x in rows if x["status"] == s) for s in sorted({x["status"] for x in rows})},
            "n_market_rounds": len(ok), "lead_min_quantiles": {q: leads[int(q * (len(leads) - 1))] for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
            "n_lead_ge_60": sum(1 for v in leads if v >= 60), "n_lead_ge_360": sum(1 for v in leads if v >= 360),
            "p_cross_quantiles": {q: pc[int(q * (len(pc) - 1))] for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
            "n_p_cross_le_0.9": sum(1 for v in pc if v <= 0.9), "n_p_cross_le_0.5": sum(1 for v in pc if v <= 0.5),
            "n_95_only_after_end": sum(1 for x in ok if x["p95_after_end"]),
            "n_95_after_end_given_pcross_le_0.9": sum(1 for x in ok if x["p95_after_end"] and x["p_cross"] <= 0.9)}
    json.dump(summ, open(os.path.join(DATA, "reveal_leak_summary.json"), "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
