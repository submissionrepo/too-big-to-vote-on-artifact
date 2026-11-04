"""Checks for the fourth external review of 2026-10-07.

A. The reviewer's example (exact): V = 1e6, price loss 1%, theta = 0.65, mu = 0.2, coalition 0.46, honest F 0.20,
   honest T 0.34; at OI = delta (1 - 2 mu) V the payout gain equals the stake's price loss, and the penalty-pool reward
   rises from 115 to 234.6 (at the lower price), so the coalition nets 119.6: Theorem 4 (iv) with delta read as the
   price loss alone is false.
B. The repaired statement (exact, random instances): with delta the loss net of penalty-pool rewards, no coalition
   profits when OI <= delta (1 - 2 mu) V. Pool payoffs follow the DVM (full participation, lambda_w = lambda_n):
   a token on the side that resolves earns lambda (1 - v)/v, a wrong token pays lambda, a roll pays nothing; the
   coalition's honest vote is T. Also checked: a coalition's pool payoff lies between -sigma lambda (on the losing side)
   and sigma lambda (1 - theta)/theta (on a side that resolves), so a manipulation changes it by at most
   sigma lambda / theta per request, and the net loss is at least the price loss less lambda/theta per request moved.
   The tighter (1 - theta)/theta fails when the honest vote already loses.
C. Counts: the contested market-rounds beyond the limit at the scenario losses, with the price loss reduced by
   lambda/theta (the most the pool can return per request).
D. Neg-risk market-rounds among the 127, and the counts without them.
"""
import csv
import json
import os
import random
from fractions import Fraction as Fr

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
LAM = Fr(1, 1000)


def rho(f, mu):
    return min(Fr(1), max(Fr(0), (f - mu) / (1 - 2 * mu)))


def resolve(x_f, x_t, theta):
    return "F" if x_f > theta else ("T" if x_t > theta else None)


def coalition_pool(side, x_f, x_t, sigma, theta, lam):
    """Pool payoff of a coalition of share sigma voting `side`, per unit of staked supply (value units / V)."""
    w = resolve(x_f, x_t, theta)
    if w is None:
        return Fr(0)
    v = x_f if w == "F" else x_t
    if side == w:
        return sigma * lam * (1 - v) / v
    return -sigma * lam


def part_a():
    V, d, th, mu, s, hF, hT = Fr(10 ** 6), Fr(1, 100), Fr(13, 20), Fr(1, 5), Fr(46, 100), Fr(20, 100), Fr(34, 100)
    Q = d * (1 - 2 * mu) * V
    gain = Q * (rho(hF + s, mu) - rho(hF, mu))
    loss = d * s * V
    pool_h = coalition_pool("T", hF, hT + s, s, th, LAM) * V
    pool_m = coalition_pool("F", hF + s, hT, s, th, LAM) * V * (1 - d)
    net = gain - loss + pool_m - pool_h
    assert gain == loss and net > 0
    return {"OI": str(Q), "payout_gain": str(gain), "price_loss": str(loss), "pool_honest": str(pool_h),
            "pool_manipulated_at_lower_price": str(pool_m), "net": float(net)}


def part_b(n=20000, seed=20261007):
    rng = random.Random(seed)
    worst, checked, bound_ok, tight_fails = None, 0, True, 0
    for _ in range(n):
        th = Fr(rng.choice([50, 55, 60, 65, 70]), 100)
        mu = Fr(rng.choice([0, 10, 15, 20, 25, 30]), 100)
        s = Fr(rng.randint(1, 90), 100)
        hF = Fr(rng.randint(0, 100 - s.numerator * 100 // s.denominator), 100) if s < 1 else Fr(0)
        if hF + s > 1:
            continue
        hT = 1 - s - hF
        dp = Fr(rng.randint(0, 300), 1000)                       # price loss of the stake
        # the coalition's best deviation from honest T: any split of its stake between F, T and abstention
        best = None
        for a in range(0, 11):
            for b in range(0, 11 - a):
                fa, fb = s * a / 10, s * b / 10
                x_f, x_t = hF + fa, hT + fb
                cast = x_f + x_t
                if cast == 0:
                    continue
                pay_shift = rho(x_f / cast, mu) - rho(hF / (hF + hT + s), mu)
                pool_m = (coalition_pool("F", x_f, x_t, fa, th, LAM) + coalition_pool("T", x_f, x_t, fb, th, LAM)
                          - (s - fa - fb) * LAM * (1 if resolve(x_f, x_t, th) else 0))
                visible = not (a == 0 and b == 10)              # the honest split is not a manipulation
                if not visible:
                    continue
                cand = (pay_shift, pool_m, fa)
                best = cand if best is None or pay_shift > best[0] else best
        if best is None:
            continue
        pay_shift, pool_m, fa = best
        pool_h = coalition_pool("T", hF, hT + s, s, th, LAM)
        dpool = pool_m * (1 - dp) - pool_h                       # rewards valued at the lower price
        if dpool > s * LAM / th:
            bound_ok = False
        if dpool > s * LAM * (1 - th) / th:
            tight_fails += 1
        delta_net = dp - dpool / s                               # loss net of pool rewards, per unit of stake
        if delta_net <= 0:
            continue
        Q = delta_net * (1 - 2 * mu)                             # OI at the repaired limit, per unit of V
        profit = Q * pay_shift - dp * s + dpool
        checked += 1
        worst = profit if worst is None or profit > worst else worst
        assert profit <= 0, (th, mu, s, hF, dp, profit)
    return {"instances": checked, "max_profit_at_limit": float(worst), "pool_gain_bound_lambda_over_theta_holds": bound_ok,
            "instances_beyond_the_tighter_bound": tight_fails}


def part_c():
    pts = list(csv.DictReader(open(os.path.join(DATA, "capture_economics_points.csv"), encoding="utf-8")))
    de = json.load(open(os.path.join(DATA, "delta_event_study.json")))
    need = lambda p: float(p["oi"]) / (0.6 * float(p["S"]) * float(p["uma_price"]))
    adj = lambda p: float(LAM) / float(p["theta"])
    out = {}
    for label, d in (("detectable", de["pooled_not_drained"]["detectable_loss"]), ("drained_median", de["drained"]["loss_median"]),
                     ("one", 1.0)):
        out[label] = {"delta": d, "beyond": sum(1 for p in pts if need(p) > d),
                      "beyond_net": sum(1 for p in pts if need(p) > d - adj(p))}
        assert out[label]["beyond"] == out[label]["beyond_net"]
    return out


def part_d():
    pts = list(csv.DictReader(open(os.path.join(DATA, "capture_economics_points.csv"), encoding="utf-8")))
    ce = {r["conditionId"]: r["negRisk"] for r in csv.DictReader(open(os.path.join(DATA, "capture_economics.csv"), encoding="utf-8"))}
    de = json.load(open(os.path.join(DATA, "delta_event_study.json")))
    need = lambda p: float(p["oi"]) / (0.6 * float(p["S"]) * float(p["uma_price"]))
    neg = lambda p: ce.get(p["conditionId"]) == "True"
    out = {"market_rounds": len(pts), "neg_risk": sum(1 for p in pts if neg(p)),
           "unknown": sum(1 for p in pts if ce.get(p["conditionId"]) in ("", None))}
    for label, d in (("penalty", 0.001), ("detectable", de["pooled_not_drained"]["detectable_loss"]),
                     ("drained_median", de["drained"]["loss_median"]), ("one", 1.0)):
        b = [p for p in pts if need(p) > d]
        out[label] = {"beyond": len(b), "neg_risk_beyond": sum(1 for p in b if neg(p)),
                      "beyond_without_neg_risk": sum(1 for p in b if not neg(p))}
    top = max(pts, key=need)
    out["largest_ratio_market"] = {"title": top["title"], "neg_risk": neg(top)}
    return out


def main():
    res = {"A_example": part_a(), "B_repaired_iv": part_b(), "C_counts_net": part_c(), "D_neg_risk": part_d()}
    json.dump(res, open(os.path.join(DATA, "review4_checks_20261007.json"), "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
