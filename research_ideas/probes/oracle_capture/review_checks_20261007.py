"""Checks of the external review of 2026-10-07 (points 2, 3 and 4), on the paper's own model and data.

A. Theorem 1's equilibrium sentence, in exact arithmetic. Payoffs are the DVM's pool payoffs with full participation
   and lambda_w = lambda_n = lambda: a token on the winning side earns lambda (1 - v*) / v*, a wrong or absent token
   pays lambda, and a roll pays nothing. "Everyone remaining votes F" fails for a remaining voter of stake s exactly
   when h_T + s > theta and (1 - h_T - s)/(h_T + s) > h_T/(1 - h_T), that is for s in (theta - h_T, 1 - 2 h_T);
   "everyone remaining votes T" fails exactly for s in (theta - a, 1 - 2a) with a = alpha + h_F. Both intervals are
   non-empty whenever the theorem's own conditions hold, so the sentence needs a bound on single stakes.
B. The event study under the stated criterion (a year of prices before the event), with the power of the pooled test
   at 50% and 80%, and without Indexed, whose attacker bought the token.
C. The limit applied per round instead of per market: the coalition's stake moves every market settled in one round,
   while the token loses its value once, so the cap binds on the summed open interest of the round.
"""
import csv
import json
import math
import os
import statistics as st
from collections import defaultdict
from fractions import Fraction as Fr

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
MU = 0.2


def rate(v):  # pool rate per winning token, in units of lambda, full participation
    return (1 - v) / v


def part_a():
    th, al, hF, hT = Fr(65, 100), Fr(10, 100), Fr(10, 100), Fr(34, 100)
    m = 1 - al - hF - hT
    assert m == Fr(46, 100) and 1 - hT > th and 1 - al - hF > th  # the theorem's conditions hold
    out = {}
    # all T: one remaining voter holds all of m and switches to F
    vT = hT + m
    s = m
    vF_dev = al + hF + s
    assert vF_dev > th and vT - s <= th
    out["all_T"] = {"s": str(s), "stay": str(rate(vT)), "deviate": str(rate(vF_dev)),
                    "profitable": rate(vF_dev) > rate(vT),
                    "break_interval": [str(th - al - hF), str(min(1 - 2 * (al + hF), m))]}
    # all F: a remaining voter of stake 0.315 (the rest of m in small stakes) switches to T
    vF = 1 - hT
    s = Fr(315, 1000)
    vT_dev = hT + s
    assert vT_dev > th and vF - s <= th
    out["all_F"] = {"s": str(s), "stay": str(rate(vF)), "deviate": str(rate(vT_dev)),
                    "profitable": rate(vT_dev) > rate(vF),
                    "break_interval": [str(th - hT), str(1 - 2 * hT)]}
    # the boundaries in closed form: (1 - h - s)/(h + s) = h/(1 - h)  <=>  s = 1 - 2h
    for h in (hT, al + hF):
        s_star = 1 - 2 * h
        assert rate(h + s_star) == rate(1 - h)
    # sufficient condition: no remaining stake above theta - h_T (all F) or theta - alpha - h_F (all T); then a
    # deviation either leaves the outcome (and loses lambda) or makes the request roll (and earns nothing)
    grid = [Fr(k, 1000) for k in range(1, 461)]
    brk_F = [s for s in grid if hT + s > th and rate(hT + s) > rate(1 - hT)]
    brk_T = [s for s in grid if al + hF + s > th and rate(al + hF + s) > rate(1 - al - hF)]
    out["grid_break_F"] = [str(brk_F[0]), str(brk_F[-1]), len(brk_F)]
    out["grid_break_T"] = [str(brk_T[0]), str(brk_T[-1]), len(brk_T)]
    assert all(th - hT < s < 1 - 2 * hT for s in brk_F) and all(th - al - hF < s < 1 - 2 * (al + hF) for s in brk_T)
    return out


def need_by_point():
    pts = list(csv.DictReader(open(os.path.join(DATA, "capture_economics_points.csv"), encoding="utf-8")))
    for p in pts:
        p["V"] = float(p["S"]) * float(p["uma_price"])
        p["need"] = float(p["oi"]) / ((1 - 2 * MU) * p["V"])
    return pts


def summarize(rows, need):
    drained = [r for r in rows if r["drained"]]
    clean = [r for r in rows if not r["drained"]]
    ld = sorted(r["loss_used"] for r in drained)
    pc = [r for r in clean if r["car7"] is not None and r["sd7"]]
    mean = st.mean(r["car7"] for r in pc)
    se = math.sqrt(sum(r["sd7"] ** 2 for r in pc)) / len(pc)
    det50 = 1 - math.exp(-1.96 * se)
    det80 = 1 - math.exp(-(1.96 + 0.8416) * se)
    unp = lambda d: sum(1 for x in need if x > d)
    return {"events": [r["event"] for r in rows],
            "drained": {"n": len(drained), "loss_median": st.median(ld), "loss_min": ld[0], "loss_max": ld[-1],
                        "n_sig": sum(1 for r in drained if (r["z_used"] or 0) < -1.96)},
            "clean": {"n": len(clean), "loss_median": st.median(r["loss_used"] for r in clean),
                      "n_sig": sum(1 for r in clean if (r["z_used"] or 0) < -1.96)},
            "pooled": {"n": len(pc), "mean_car7": mean, "mean_loss": 1 - math.exp(mean), "se": se, "z": mean / se,
                       "detectable_50pct_power": det50, "detectable_80pct_power": det80},
            "unprotected": {"at_det50": unp(det50), "at_det80": unp(det80), "at_drained_median": unp(st.median(ld)),
                            "of": len(need)}}


def part_b(pts):
    raw = list(csv.DictReader(open(os.path.join(DATA, "delta_event_study.csv"), encoding="utf-8")))
    rows = []
    for r in raw:
        f = lambda k: float(r[k]) if r.get(k) not in (None, "") else None
        k = 7 if f("car7_eth") is not None else (3 if f("car3_eth") is not None else 1)
        rows.append({"event": r["event"], "drained": r["drained"] == "True", "history": int(r["history_days"]),
                     "car7": f("car7_eth"), "sd7": f("sd7_eth"), "loss_used": f(f"loss{k}_eth"),
                     "z_used": f(f"z{k}_eth")})
    need = [p["need"] for p in pts]
    year = [r for r in rows if r["history"] >= 365]
    return {"history_days": {r["event"]: r["history"] for r in rows},
            "as_published": summarize(rows, need),
            "year_of_history": summarize(year, need),
            "year_of_history_without_indexed": summarize([r for r in year if r["event"] != "Indexed"], need)}


def part_c(pts):
    by = defaultdict(list)
    for p in pts:
        by[p["roundId"]].append(p)
    assert all(len({round(q["V"], 2) for q in v}) == 1 for v in by.values())  # one stake value per round
    rounds = {k: (sum(float(q["oi"]) for q in v), v[0]["V"], len(v)) for k, v in by.items()}
    out = {"market_rounds": len(pts), "rounds": len(by), "rounds_with_several": sum(1 for v in by.values() if len(v) > 1),
           "max_per_round": max(len(v) for v in by.values())}
    for label, d in (("penalty", 0.001), ("tenth", 0.10), ("third", 1 / 3)):
        per_market = sum(1 for p in pts if p["need"] > d)
        bad_rounds = [k for k, (oi, V, n) in rounds.items() if oi > d * (1 - 2 * MU) * V]
        in_bad = sum(rounds[k][2] for k in bad_rounds)
        out[label] = {"delta": d, "market_rounds_over_alone": per_market, "rounds_over_summed": len(bad_rounds),
                      "market_rounds_in_rounds_over": in_bad}
    return out


def main():
    pts = need_by_point()
    res = {"A_theorem1_equilibria": part_a(), "B_event_study": part_b(pts), "C_per_round": part_c(pts)}
    json.dump(res, open(os.path.join(DATA, "review_checks_20261007.json"), "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
