"""Summarize capture_economics.csv: what the market could pay against the stake that decides it.

For each contested Polymarket question matched to its market, the attacker's answer F is the side (Yes or No) other
than the vote's winner; when the winner was "too early" or one half, F is the side with the larger vote. The stake
an incumbent needs to make F resolve is sigma_F = theta - h_F (Theorem 1 with h_F the recorded vote for F, as a share
of the staked supply), valued at the UMA close of the round's last day. The most any position can gain from F is
the open interest at the round's end, so delta_F = OI / V_F bounds the fraction of the stake's value a capture can
cost and still pay. Questions settled in the same round share one stake, so the round is also summarized.
Only votes that decide a payout enter (payout_votes.py): a question's first dispute is voted on too, but that vote
only settles the dispute's bonds, because the adapter has already reset the question.
Also computes the March 2025 incumbent numbers and the token's abnormal returns after that vote.
Writes data/capture_economics_summary.json and data/capture_economics_points.csv (the figure's data).
"""
import csv
import datetime as dt
import json
import math
import os
import statistics as st
from collections import defaultdict

import payout_votes
from reqkey import req_key

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SIDES = ("p1", "p2")


def load(name):
    return list(csv.DictReader(open(os.path.join(DATA, name), encoding="utf-8")))


_ANC, _REQ = {}, {}


def derived_qid(r):
    """questionID derived from the oracle-stamped ancillary text of the request in row r (pm_markets.py)."""
    import pm_markets as pm
    if not _ANC:
        _ANC.update(pm.load_ancillary())
        _REQ.update({req_key(q): q for q in load("requests_summary.csv")})
    q = _REQ[req_key(r)]
    st = pm.stamped(_ANC[(q["identifier"], int(r["requestTime"]), q["ancKey"])])
    cond, qid, _ = pm.derive_condition(st)
    assert cond == r["conditionId"]
    return qid.lower()


def closes(name):
    return {r["date"]: float(r["close"]) for r in load(name)}


def main():
    roles = payout_votes.roles()
    allrows = load("capture_economics.csv")
    rows_all = [r for r in allrows if r["status"] == "ok"]
    rows = [r for r in rows_all if payout_votes.is_payout(r, roles)]
    tallies = {req_key(t): t for t in load("contested_answer_tallies.csv")}
    pts = []
    for r in rows:
        t = tallies[req_key(r)]
        w = r["winner"]
        if w in SIDES:
            F = "p1" if w == "p2" else "p2"
        else:
            F = max(SIDES, key=lambda p: float(t[p]))
        hF = float(t[F])
        theta = float(r["theta"])
        S = float(r["stakedSupply"])
        px = float(r["uma_price"])
        sigma = max(0.0, theta - hF)
        V = sigma * S * px
        oi = float(r["oi_usdc"])
        pts.append({"roundId": r["roundId"], "requestTime": r["requestTime"], "ancKey": r["ancKey"], "conditionId": r["conditionId"],
                    "title": r["title"], "winner": w, "F": F, "hF": round(hF, 5), "theta": theta, "sigma_F": round(sigma, 5),
                    "S": round(S), "uma_price": px, "V_F": round(V), "oi": round(oi, 2),
                    "delta_F": round(oi / V, 6) if V > 0 else None, "k": r["k"],
                    "era": "A" if theta == 0.5 else "B", "match": r["match"]})
    # one point per (round, market): the market is paid on its latest vote
    best = {}
    for p in pts:
        key = (p["roundId"], p["conditionId"])
        if key not in best or int(p["requestTime"]) > int(best[key]["requestTime"]):
            best[key] = p
    uniq = sorted(best.values(), key=lambda p: -(p["delta_F"] or 0))
    with open(os.path.join(DATA, "capture_economics_points.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(uniq[0]))
        w.writeheader()
        w.writerows(uniq)
    ds = sorted(p["delta_F"] for p in uniq if p["delta_F"] is not None)
    ois = sorted(p["oi"] for p in uniq)
    vs = sorted(p["V_F"] for p in uniq)
    q = lambda xs, a: xs[min(len(xs) - 1, int(a * len(xs)))]
    summ = {
        "n_contested_polymarket": len(allrows),
        "status_counts": {s: sum(1 for r in allrows if r["status"] == s) for s in sorted({r["status"] for r in allrows})},
        "match_counts": {m: sum(1 for r in rows_all if r["match"] == m) for m in sorted({r["match"] for r in rows_all})},
        "n_requests_ok": len(rows_all), "n_payout_requests_ok": len(rows),
        "n_bond_only_requests_ok": len(rows_all) - len(rows), "n_market_rounds": len(uniq),
        "n_market_rounds_any_vote": len({(r["roundId"], r["conditionId"]) for r in rows_all}),
        "oi_quantiles": {a: q(ois, a) for a in (0.1, 0.25, 0.5, 0.75, 0.9)}, "oi_max": ois[-1], "oi_total": round(sum(ois)),
        "V_F_quantiles": {a: q(vs, a) for a in (0.1, 0.5, 0.9)}, "V_F_min": vs[0],
        "delta_quantiles": {a: q(ds, a) for a in (0.1, 0.25, 0.5, 0.75, 0.9)},
        "n_delta_ge": {str(c): sum(1 for d in ds if d >= c) for c in (0.01, 0.05, 0.1, 0.25, 0.5, 1.0)},
        "top": [{k: p[k] for k in ("title", "roundId", "winner", "F", "hF", "sigma_F", "V_F", "oi", "delta_F", "era", "k")} for p in uniq[:8]],
        "pivotal_k1": {"n": sum(1 for p in uniq if p["k"] == "1"),
                       "n_delta_ge_0.1": sum(1 for p in uniq if p["k"] == "1" and (p["delta_F"] or 0) >= 0.1)},
    }
    # the derived identifiers against the market API: same questionID, or not listed by the API at all
    import glob
    eq = ne = miss = 0
    for r in rows_all:
        if r["match"] != "derived":
            continue
        g = glob.glob(os.path.join(DATA, "raw", "pm_cache", f"gamma_{r['conditionId'][:24]}.json"))
        gm = json.load(open(g[0], encoding="utf-8")) if g else []
        if not gm:
            miss += 1
            continue
        # capture_economics.py keeps only the conditionId, so the questionID is recomputed from the stamped text
        if (gm[0].get("questionID") or "").lower() == derived_qid(r):
            eq += 1
        else:
            ne += 1
    summ["derived_api_check"] = {"same_questionID": eq, "different": ne, "not_listed": miss}
    # who could have collected: coalitions the size of today's k largest stakers (voters_current.csv)
    shares = [float(v["shareOfCumulative"]) for v in load("voters_current.csv")]
    coal = {}
    for k in (1, 2, 4, 10):
        s = sum(shares[:k])
        cap = [p for p in uniq if p["sigma_F"] <= s]
        coal[str(k)] = {"share": s, "n_capturable": len(cap),
                        "n_delta_ge_0.1": sum(1 for p in cap if (p["delta_F"] or 0) >= 0.1),
                        "max_delta": max((p["delta_F"] or 0) for p in cap) if cap else None}
    coal["sigma_F_of_delta_ge_1"] = sorted(p["sigma_F"] for p in uniq if (p["delta_F"] or 0) >= 1)
    summ["coalitions_today"] = coal
    # per round: a stake votes on every request of its round with full weight
    by_round = defaultdict(list)
    for p in uniq:
        by_round[p["roundId"]].append(p)
    per_round = []
    for rid, L in by_round.items():
        S, px = L[0]["S"], L[0]["uma_price"]
        for sig in (0.10, 0.20, 0.30):
            cap = [p for p in L if p["sigma_F"] < sig]
            if cap:
                gain = sum(p["oi"] for p in cap)
                per_round.append({"roundId": rid, "sigma": sig, "n": len(cap), "oi": round(gain), "V": round(sig * S * px),
                                  "ratio": gain / (sig * S * px)})
    summ["per_round"] = {str(sig): sorted([x for x in per_round if x["sigma"] == sig], key=lambda x: -x["ratio"])[:3]
                         for sig in (0.10, 0.20, 0.30)}
    summ["rounds_with_several_markets"] = sum(1 for L in by_round.values() if len(L) > 1)
    summ["max_markets_in_a_round"] = max(len(L) for L in by_round.values())

    # March 2025: the three wallets as incumbents
    # the market was paid on the second request (index 827): the first (828) settled only the first dispute's bonds
    mar = next(p for p in pts if p["requestTime"] == "1742684664")
    port = json.load(open(os.path.join(DATA, "dvm_port_results.json")))
    whale = port["827"]["counterfactuals"]["whale_stake_actual"] / 1e18
    uma = closes("uma_usd_daily_coinbase.csv")
    eth = closes("eth_usd_daily_coinbase.csv")
    btc = closes("btc_usd_daily_coinbase.csv")
    p0 = uma["2025-03-24"]
    summ["march"] = {"oi_round_end": mar["oi"], "whale_tokens": whale, "uma_close_2025_03_24": p0,
                     "whale_value_usd": whale * p0, "delta_whale": mar["oi"] / (whale * p0)}
    d0 = dt.date(2025, 3, 24)  # the close of March 24 UTC is the end of round 10085
    lr = lambda px, a, b: math.log(px[str(b)] / px[str(a)])
    ev = {}
    for h in (1, 3, 7):
        d1 = d0 + dt.timedelta(days=h)
        ev[str(h)] = {"uma_pct": 100 * (uma[str(d1)] / uma[str(d0)] - 1),
                      "eth_pct": 100 * (eth[str(d1)] / eth[str(d0)] - 1), "btc_pct": 100 * (btc[str(d1)] / btc[str(d0)] - 1),
                      "abn_eth_lp": 100 * (lr(uma, d0, d1) - lr(eth, d0, d1)), "abn_btc_lp": 100 * (lr(uma, d0, d1) - lr(btc, d0, d1))}
    sd = {}
    for h in (1, 3, 7):
        for name, bm in (("eth", eth), ("btc", btc)):
            xs, d = [], dt.date(2024, 3, 24)
            while d + dt.timedelta(days=h) <= dt.date(2025, 3, 17):
                e = d + dt.timedelta(days=h)
                xs.append(lr(uma, d, e) - lr(bm, d, e))
                d = e
            sd[f"{h}_{name}"] = {"sd_lp": 100 * st.pstdev(xs), "n": len(xs)}
    summ["march_event"] = {"returns": ev, "prior_year_sd_of_abnormal": sd,
                           "note": "abnormal = UMA log return minus benchmark log return; prior year 2024-03-24..2025-03-17, non-overlapping windows"}
    json.dump(summ, open(os.path.join(DATA, "capture_economics_summary.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in summ.items() if k not in ("top", "per_round")}, indent=1))
    for x in summ["top"]:
        print(x)
    for sig, L in summ["per_round"].items():
        print("per round", sig, L)


if __name__ == "__main__":
    main()
