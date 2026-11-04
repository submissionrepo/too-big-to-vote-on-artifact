"""Theorem 4 (i), (ii), (iii), (v) with honest abstention (2026-10-08, after an external review built a counterexample
to the full-participation reading of Corollary 1). Exact integer enumeration; first-layer check, finite instances.

Setting, staked supply 1 on a 1/N grid: honest blocks hF (vote the coalition's answer F) and hT (vote the other
answer), the rest of the non-coalition stake abstains; the coalition's stake s splits into a (F), b (T), t ('too
early'), h (one half) and c (abstain). A 'too early' vote counts against Yes, a vote for one half counts half for Yes,
and a strictly modal 'too early' asks the question again. pi = hF + hT + s is the share that votes when the coalition
does. Claims checked for F = Yes and F = No:
  (i)   over every split that does not make 'too early' strictly modal, F's share of the votes ranges exactly over
        [hF / pi, (hF + s) / pi] (so F's payout ranges over [rho(hF/pi), rho((hF + s)/pi)] and moves by at most
        s / (pi (1 - 2 mu)));
  (ii)  some split pays F one dollar iff hF + s >= (1 - mu) pi, for mu in {1/10, 1/5, 1/4, 3/10};
  (v)   some split makes 'too early' strictly modal iff s > max(hF, hT);
  (iii) at hF = hT = mu pi and s = (1 - 2 mu) pi the coalition moves F's payout from 0 to 1.
Splits with no vote at all are skipped (the rule has no tally to pay on).
"""
import itertools
import json
import os
from fractions import Fraction as Fr

HERE = os.path.dirname(os.path.abspath(__file__))
MUS = (Fr(1, 10), Fr(1, 5), Fr(1, 4), Fr(3, 10))


def rho(f, mu):
    return min(Fr(1), max(Fr(0), (f - mu) / (1 - 2 * mu)))


def splits(s, parts):
    """All compositions of s into `parts` non-negative integers."""
    for cut in itertools.combinations(range(s + parts - 1), parts - 1):
        prev, out = -1, []
        for x in cut:
            out.append(x - prev - 1)
            prev = x
        out.append(s + parts - 1 - prev - 1)
        yield out


def run(N, with_half):
    fails, n_cases, n_splits = [], 0, 0
    for hF in range(N + 1):
        for hT in range(N + 1 - hF):
            for s in range(N + 1 - hF - hT):
                pi = hF + hT + s
                if pi == 0:
                    continue
                for F in ("Yes", "No"):
                    lo = hi = None          # F's share as (num, den) with den > 0
                    ask_again = False
                    for sp in splits(s, 5 if with_half else 4):
                        a, b, t, c = sp[0], sp[1], sp[2], sp[-1]
                        h = sp[3] if with_half else 0
                        n_splits += 1
                        yes = hF + a if F == "Yes" else hT + b
                        no = hT + b if F == "Yes" else hF + a
                        W = yes + no + t + h
                        if W == 0:
                            continue
                        if t > max(yes, no, h):
                            ask_again = True
                            continue
                        num_yes2 = 2 * yes + h              # Yes share = num_yes2 / (2 W)
                        numF = num_yes2 if F == "Yes" else 2 * W - num_yes2
                        den = 2 * W
                        if lo is None or numF * lo[1] < lo[0] * den:
                            lo = (numF, den)
                        if hi is None or numF * hi[1] > hi[0] * den:
                            hi = (numF, den)
                    n_cases += 1
                    case = dict(N=N, hF=hF, hT=hT, s=s, F=F)
                    if lo is None:
                        fails.append({**case, "why": "no valid split"})
                        continue
                    lo_f, hi_f = Fr(*lo), Fr(*hi)
                    if s > 0 and (lo_f != Fr(hF, pi) or hi_f != Fr(hF + s, pi)):
                        fails.append({**case, "why": "range", "lo": str(lo_f), "hi": str(hi_f)})
                    if s == 0 and hF + hT > 0 and not (lo_f == hi_f == Fr(hF, hF + hT)):
                        fails.append({**case, "why": "range at s = 0"})
                    if ask_again != (s > max(hF, hT)):
                        fails.append({**case, "why": "(v)", "ask_again": ask_again})
                    for mu in MUS:
                        pays_one = hi_f >= 1 - mu
                        if pays_one != (hF + s >= (1 - mu) * pi):
                            fails.append({**case, "why": "(ii)", "mu": str(mu)})
    return {"N": N, "with_half": with_half, "cases": n_cases, "splits": n_splits, "failures": fails[:20],
            "n_failures": len(fails)}


def construction():
    """(iii): hF = hT = mu pi, s = (1 - 2 mu) pi moves F's payout from rho(mu) = 0 to rho(1 - mu) = 1."""
    out = []
    for mu in MUS:
        for pi in (Fr(1), Fr(9, 10), Fr(3, 5), Fr(3, 10)):
            hF = hT = mu * pi
            s = (1 - 2 * mu) * pi
            lo, hi = hF / (hF + hT + s), (hF + s) / (hF + hT + s)
            out.append({"mu": str(mu), "pi": str(pi), "ok": rho(lo, mu) == 0 and rho(hi, mu) == 1
                        and hF + hT + s == pi})
    return out


if __name__ == "__main__":
    res = {"grid_with_half_N24": run(24, True), "grid_N40": run(40, False), "construction": construction()}
    res["all_pass"] = (res["grid_with_half_N24"]["n_failures"] == 0 and res["grid_N40"]["n_failures"] == 0
                       and all(x["ok"] for x in res["construction"]))
    json.dump(res, open(os.path.join(HERE, "data", "participation_checks_20261008.json"), "w"), indent=1)
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != "failures"})
                      for k, v in res.items() if k != "construction"}, indent=1))
    print("construction ok:", all(x["ok"] for x in res["construction"]))
