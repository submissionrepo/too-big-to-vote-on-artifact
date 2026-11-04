"""Checks of the second external review of 2026-10-07 (point 2: what the 14% in Section 6.5 is).

  A. The reviewer's computation: Table 5's weekly returns as printed (simple returns, rounded to 0.1%), equal weights,
     one-sided one-sample t-test at 5%, the effect that has 80% power (statsmodels TTestPower), with and without
     Indexed.
  B. The paper's computation: weekly abnormal log returns against ETH, standard error from each token's own weekly
     noise in the 365 days before the event, two-sided z-test at 5%, 80% power: 1 - exp(-(1.96 + 0.8416) se).
  C. What the review asks for instead: the estimate and a one-sided 95% upper confidence bound on the mean loss, both
     with the time-series standard error of B and with the cross-sectional (t) standard error, with and without
     Indexed; and how many of the 127 contested market-rounds exceed delta (1 - 2 mu) V at each bound (mu = 0.2).
"""
import csv
import json
import math
import os
import statistics as st

from scipy import stats
from statsmodels.stats.power import TTestPower

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def main():
    rows = [r for r in csv.DictReader(open(os.path.join(DATA, "delta_event_study.csv"), encoding="utf-8"))
            if r["included"] == "True" and r["drained"] == "False"]
    for r in rows:
        r["car7"] = float(r["car7_eth"])
        r["sd7"] = float(r["sd7_eth"])
        r["simple_printed"] = round(100 * (math.exp(r["car7"]) - 1), 1) / 100   # as Table 5 prints it
    pts = list(csv.DictReader(open(os.path.join(DATA, "capture_economics_points.csv"), encoding="utf-8")))
    need = [float(p["oi"]) / (0.6 * float(p["S"]) * float(p["uma_price"])) for p in pts]
    unp = lambda d: sum(1 for x in need if x > d)
    out = {"events": [r["event"] for r in rows]}
    for label, sub in (("all", rows), ("without_indexed", [r for r in rows if r["event"] != "Indexed"])):
        n = len(sub)
        # A: the reviewer's one-sided t-test on printed simple returns
        x = [r["simple_printed"] for r in sub]
        sd_x = st.stdev(x)
        d80 = TTestPower().solve_power(nobs=n, alpha=0.05, power=0.8, alternative="larger")
        # B: the paper's test
        mean_l = st.mean(r["car7"] for r in sub)
        se_ts = math.sqrt(sum(r["sd7"] ** 2 for r in sub)) / n
        mde_paper = 1 - math.exp(-(1.96 + 0.8416) * se_ts)
        # C: estimate and one-sided 95% upper confidence bounds on the mean loss (log scale, then as a loss)
        se_cs = st.stdev([r["car7"] for r in sub]) / math.sqrt(n)
        ub_ts = 1 - math.exp(min(0.0, mean_l - 1.645 * se_ts))
        ub_cs = 1 - math.exp(min(0.0, mean_l - stats.t.ppf(0.95, n - 1) * se_cs))
        out[label] = {
            "n": n,
            "A_reviewer": {"sd_simple": sd_x, "cohen_d_80pct_power": d80, "mde_simple_pp": 100 * d80 * sd_x},
            "B_paper": {"mean_log": mean_l, "se_timeseries": se_ts, "mde_80pct_power": mde_paper},
            "C_bounds": {"mean_loss": 1 - math.exp(mean_l),
                         "se_crosssection": se_cs,
                         "upper95_loss_timeseries_se": ub_ts, "upper95_loss_crosssection_t": ub_cs,
                         "unprotected_at_upper95_ts": unp(ub_ts) if ub_ts > 0 else None,
                         "unprotected_at_upper95_cs": unp(ub_cs) if ub_cs > 0 else None,
                         "unprotected_at_14pct": unp(0.14)},
        }
    out["D_budget_iff"] = part_d()
    json.dump(out, open(os.path.join(DATA, "review2_checks_20261007.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


def part_d():
    """Point 3b: equation (1) checks only the smallest capture coalition. With pool payoffs (full participation,
    lambda_w = lambda_n), a coalition alpha > theta - h_F that captures earns alpha (1 - alpha - h_F)/(alpha + h_F)
    lambda S from the pool, which rises in alpha while (alpha + h_F)^2 < h_F. At a March-like point (theta = 1/2,
    h_F = 7/25) it rises from the infimum 11/50 up to alpha = 1/4. With an increasing cost c(x) = C0 + k x, C0 and k
    chosen below, equation (1) holds at the infimum (no gain there) while alpha = 1/4 profits: the 'if' direction
    needs an assumption on c, e.g. that c(alpha S) minus the pool term does not fall in alpha."""
    from fractions import Fraction as Fr
    th, hF, lam, S = Fr(1, 2), Fr(7, 25), Fr(1, 1000), Fr(1)
    pool = lambda a: a * (1 - a - hF) / (a + hF) * lam * S
    a0, a1 = th - hF, Fr(1, 4)
    assert a0 == Fr(11, 50) and pool(a1) > pool(a0)
    k = Fr(1, 100000)                       # cost per unit share of the supply, increasing
    q0 = Fr(1, 1000)                        # (1 - pbar) Q_max
    C0 = q0 + pool(a0) - k * a0 * S + Fr(1, 10 ** 7)   # equation (1) holds with a margin of 1e-7
    c = lambda a: C0 + k * a * S
    holds_at_inf = c(a0) > q0 + pool(a0)
    profit_a1 = q0 + pool(a1) - c(a1)
    assert holds_at_inf and profit_a1 > 0
    return {"theta": str(th), "h_F": str(hF), "alpha_inf": str(a0), "alpha_profitable": str(a1),
            "pool_gain_rise": str(pool(a1) - pool(a0)), "cost_rise": str(c(a1) - c(a0)),
            "eq1_holds_at_infimum": holds_at_inf, "profit_of_larger_coalition": str(profit_a1)}


if __name__ == "__main__":
    main()
