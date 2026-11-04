"""Checks of the statements as repaired after the second external review of 2026-10-07.

E19  Theorem 3 with its range and infima. For tally-only rules on (x, y) = (F share, T share) of the staked supply,
     against an honest electorate (a block h_F votes F, the rest of the non-coalition stake votes T) and a coalition
     that splits sigma among F, T and abstention: the infimum of the coalitions that make F resolve is
     max(0, theta_f - h_F) and that of the coalitions that keep T from resolving is max(0, 1 - theta_f - h_F) for every
     h_F, and the two add up to 1 - 2 h_F exactly when h_F <= 1 - theta_f. Integer enumeration on a 1/N grid for three
     rules: staked threshold with strict and with weak inequality, and the votes-cast threshold (strict). On a grid the
     smallest coalition is the infimum or one step above it.

E20  The sufficiency of equation (1) under a proportional cost. A capturing coalition alpha earns lambda S g(alpha) from
     the pool, g(alpha) = alpha (1 - alpha - h_F)/(alpha + h_F); with v = alpha + h_F >= theta >= h_F,
     (1 - theta)/theta - g'(alpha) = (v^2 - theta h_F)/(theta v^2) >= 0 (sympy identity; the sign follows from
     v^2 >= theta^2 >= theta h_F), so a cost that grows by at least lambda (1 - theta)/theta per unit of stake makes the
     smallest capturing coalition the binding one. Exact spot check on a grid of (theta, h_F, alpha).
"""
import json
import os
import sys
from fractions import Fraction as Fr

import sympy as sp

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "review2_repair_checks_20261007.json")
N = 40


def resolves(rule, x, y, th):
    """Which answer resolves, in grid units: x, y votes for F and T out of N staked."""
    if rule == "staked_strict":
        return "F" if x > th else ("T" if y > th else None)
    if rule == "staked_weak":
        return "F" if x >= th else ("T" if y >= th else None)
    if rule == "votes_cast_strict":                      # share of votes cast above theta
        cast = x + y
        if cast == 0:
            return None
        return "F" if x * N > th * cast else ("T" if y * N > th * cast else None)
    raise ValueError(rule)


def e19():
    rows, ok = {}, True
    for rule in ("staked_strict", "staked_weak", "votes_cast_strict"):
        for th in (20, 22, 26, 32):                     # theta_f in {1/2, 11/20, 13/20, 4/5}
            for h in range(0, N + 1):                   # h_F over its whole range
                cap = blk = None
                for s in range(0, N - h + 1):
                    hT = N - s - h
                    outs = set()
                    for a in range(s + 1):
                        for b in range(s - a + 1):
                            outs.add(resolves(rule, h + a, hT + b, th))
                    if cap is None and "F" in outs:
                        cap = s
                    if blk is None and any(o != "T" for o in outs):
                        blk = s
                    if cap is not None and blk is not None:
                        break
                want_cap = max(0, th - h)
                want_blk = max(0, N - th - h)
                good = cap is not None and blk is not None and cap - want_cap in (0, 1) and blk - want_blk in (0, 1)
                if h <= N - th:
                    good &= (cap + blk) - (N - 2 * h) in (0, 1, 2) and want_cap + want_blk == N - 2 * h
                else:
                    good &= blk == 0 or (blk == 1 and want_blk == 0 and rule == "staked_weak")
                if not good:
                    ok = False
                    print("MISMATCH", rule, th, h, cap, blk, want_cap, want_blk)
            rows[f"{rule} theta={Fr(th, N)}"] = "ok"
    return {"N": N, "cases": rows, "ok": ok}


def e20():
    a, h, th = sp.symbols("alpha h_F theta", positive=True)
    g = a * (1 - a - h) / (a + h)
    v = a + h
    resid = sp.simplify((1 - th) / th - sp.diff(g, a) - (v ** 2 - th * h) / (th * v ** 2))
    assert resid == 0
    worst = Fr(0)
    for thn in range(50, 96, 5):
        T = Fr(thn, 100)
        for hn in range(0, thn + 1, 5):
            H = Fr(hn, 100)
            for an in range(max(0, thn - hn), 100 - hn + 1, 5):
                A = Fr(an, 100)
                V = A + H
                if V < T or V == 0:
                    continue
                gp = (H - V * V) / (V * V)
                slack = (1 - T) / T - gp
                assert slack >= 0, (T, H, A)
                worst = min(worst, slack)
    return {"identity_residual": str(resid), "grid_min_slack": str(worst), "ok": True}


def main():
    out = {"E19": e19(), "E20": e20()}
    out["all_ok"] = out["E19"]["ok"] and out["E20"]["ok"]
    json.dump(out, open(OUT, "w"), indent=1)
    print(json.dumps({"E19_ok": out["E19"]["ok"], "E19_cases": len(out["E19"]["cases"]), "E20": out["E20"],
                      "all_ok": out["all_ok"]}, indent=1))
    if "--record" in sys.argv:
        raise SystemExit("Ledger recording is available only in the authors workspace; omit --record to reproduce the calculation.")


if __name__ == "__main__":
    main()
