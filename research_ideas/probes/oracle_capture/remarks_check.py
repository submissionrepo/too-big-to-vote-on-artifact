"""First-layer symbolic checks behind the tally-settlement text of the paper (Definition 1, the proof of Theorem 4,
Remarks 1 and 2 of Section 6.4).

  (a) with two answers a No share is paid rho of its own share: 1 - rho(f) = rho(1 - f) on every piece of rho;
  (b) Remark 1: Q sigma / (1 - 2 mu) <= lambda sigma V  <=>  Q <= lambda (1 - 2 mu) V   (sigma > 0, 0 <= mu < 1/2);
  (c) Freeman, Lahaie and Pennock's 1/prior-with-midpoint payments: pay k(1 - c) when both report 1 and k c when both
      report 0, with c = (rho0 + rho1)/2; a truthful report earns k (rho1 - rho0)/2 more than a false one in
      expectation, whichever signal was received;
  (d) Remark 2: sigma R Delta / 2 >= Q sigma / (1 - 2 mu)  <=>  R >= 2Q / (Delta (1 - 2 mu)), and that bound is at
      least 2Q / (1 - 2 mu) for 0 < Delta <= 1;
  (e) the paper's numbers: lambda (1 - 2 mu) V at the census end and 2Q/(1 - 2 mu) for March, in exact rationals;
  (g) Theorem 4 (iv) for the markets settled in one round: with Q_j <= OI_j shares in market j, the gain bound
      sigma sum_j OI_j / (1 - 2 mu) is at most the stake's loss delta sigma V  <=>  sum_j OI_j <= delta (1 - 2 mu) V.
"""
import json
import os
from fractions import Fraction as Fr

import sympy as sp

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def main():
    f, mu, Q, s, lam, V, R, D, k, r0, r1 = sp.symbols("f mu Q sigma lambda V R Delta k rho0 rho1", real=True)
    out = {}
    # (a) the middle piece; the outer pieces swap 0 and 1 because f <= mu iff 1 - f >= 1 - mu
    mid = sp.simplify(1 - (f - mu) / (1 - 2 * mu) - ((1 - f) - mu) / (1 - 2 * mu))
    out["a_middle_piece_residual"] = str(mid)
    assert mid == 0
    # (b)
    pos = {s: sp.Symbol("s", positive=True)}
    lhs_b = sp.simplify((lam * s * V - Q * s / (1 - 2 * mu)) / s * (1 - 2 * mu))
    out["b_scaled_difference"] = str(sp.expand(lhs_b))
    assert sp.expand(lhs_b - (lam * (1 - 2 * mu) * V - Q)) == 0
    # (c) expected advantage of a truthful report under the midpoint payments
    c = (r0 + r1) / 2
    adv1 = k * (1 - c) * r1 - k * c * (1 - r1)          # signal 1: report 1 vs report 0
    adv0 = k * c * (1 - r0) - k * (1 - c) * r0          # signal 0: report 0 vs report 1
    out["c_advantage_signal1"] = str(sp.factor(sp.expand(adv1)))
    out["c_advantage_signal0"] = str(sp.factor(sp.expand(adv0)))
    assert sp.expand(adv1 - k * (r1 - r0) / 2) == 0 and sp.expand(adv0 - k * (r1 - r0) / 2) == 0
    # (d) solve the deterrence condition for R, and compare with Delta = 1
    lhs_d = sp.expand((s * R * D / 2 - Q * s / (1 - 2 * mu)) * 2 / (s * D))
    assert sp.simplify(lhs_d - (R - 2 * Q / (D * (1 - 2 * mu)))) == 0
    gap = sp.simplify(2 * Q / (D * (1 - 2 * mu)) - 2 * Q / (1 - 2 * mu))
    out["d_gap_over_Delta_one"] = str(sp.factor(gap))
    assert sp.simplify(gap - 2 * Q * (1 - D) / (D * (1 - 2 * mu))) == 0  # >= 0 for 0 < Delta <= 1, Q >= 0, mu < 1/2
    # (f) Corollary 1 (the limit): with hF = mu and a coalition of 1 - 2 mu, the ramp moves F from rho(mu) = 0 to
    # rho(1 - mu) = 1, so a coalition holding Q shares gains Q and its stake loses delta (1 - 2 mu) V; the gain exceeds
    # the loss exactly when Q > delta (1 - 2 mu) V, and per unit of stake the shift is 1/(1 - 2 mu)
    dl = sp.Symbol("delta", positive=True)
    r = lambda x: (x - mu) / (1 - 2 * mu)
    assert sp.simplify(r(mu)) == 0 and sp.simplify(r(1 - mu) - 1) == 0
    shift_per_stake = sp.simplify((r(1 - mu) - r(mu)) / (1 - 2 * mu))
    out["f_shift_per_unit_stake"] = str(shift_per_stake)
    assert sp.simplify(shift_per_stake - 1 / (1 - 2 * mu)) == 0
    net = sp.expand(Q * (r(1 - mu) - r(mu)) - dl * (1 - 2 * mu) * V)
    out["f_net_gain"] = str(sp.simplify(net))
    assert sp.simplify(net - (Q - dl * (1 - 2 * mu) * V)) == 0
    # (g) one round, several markets: the coalition's stake moves every market the round settles and loses its value
    # once, so the per-market bound adds up across markets and the cap binds on their total open interest
    O = sp.symbols("O1:6", nonnegative=True)
    Qj = sp.symbols("Q1:6", nonnegative=True)
    gain = s * sum(Qj) / (1 - 2 * mu)
    gain_bound = s * sum(O) / (1 - 2 * mu)
    assert sp.simplify((gain_bound - gain) * (1 - 2 * mu) / s - sum(o - q for o, q in zip(O, Qj))) == 0
    slack = sp.simplify((dl * s * V - gain_bound) * (1 - 2 * mu) / s)
    out["g_scaled_slack"] = str(slack)
    assert sp.simplify(slack - (dl * (1 - 2 * mu) * V - sum(O))) == 0
    # (e) numbers quoted in the paper
    conc = json.load(open(os.path.join(DATA, "concentration.json")))
    import csv
    px = {r["date"]: r["close"] for r in csv.DictReader(open(os.path.join(DATA, "uma_usd_daily_coinbase.csv")))}
    last = max(px)
    cap = Fr(1, 1000) * Fr(3, 5) * Fr(str(conc["cumulativeStake"])) * Fr(px[last])
    my = json.load(open(os.path.join(DATA, "executable_profit_march_yes.json")))
    q = my["windows"]["dispute_to_reveal_start"]["net_yes_shares"] + my["windows"]["reveal_start_to_last_whale"]["net_yes_shares"]
    pool = Fr(2 * q) / Fr(3, 5)
    out["e_penalty_cap_usd"] = float(cap)
    out["e_last_price_date"] = last
    out["e_march_Q"] = q
    out["e_march_pool_lower_bound_usd"] = float(pool)
    json.dump(out, open(os.path.join(DATA, "remarks_check.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
