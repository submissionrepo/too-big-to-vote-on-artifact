"""Exact checks of the statements as repaired after the external review of 2026-10-07.

E17  Theorem 1, equilibrium sentence with bounds on single stakes. DVM pool payoffs with full participation and
     lambda_w = lambda_n = lambda: a token on the side that resolves earns lambda (1 - v*)/v*, a wrong or absent token
     pays lambda, a roll pays nothing. Claim: "everyone remaining votes F" is a pure Nash equilibrium when
     1 - h_T > theta and no remaining voter holds more than theta - h_T; "everyone remaining votes T" when
     1 - alpha - h_F > theta and none holds more than theta - alpha - h_F. Deviations to the other answer and to
     abstention are both tried. Random rational instances with unequal remaining stakes below the bound must pass;
     instances with one remaining stake inside the break interval (theta - h, 1 - 2h) must fail.

E18  Theorem 4 with the third answer. Honest electorate with full participation votes Yes or No: a block h_F votes the
     coalition's answer F and the rest of the non-coalition stake votes T. The coalition splits its stake sigma into
     F, T, "too early" and abstention. Under R_mu a modal "too early" (strictly most votes) has the question asked
     again; otherwise F is paid rho of its share f of the votes cast, a "too early" vote counting against Yes.
     Claims, for F = Yes and for F = No:
       (i)  over all splits that do not make "too early" lead, F's payout ranges exactly over [rho(h_F), rho(h_F + sigma)];
       (v)  some split makes "too early" lead iff sigma > max(h_F, (1 - h_F)/2).
     Exact integer enumeration on a 1/N grid.
"""
import json
import os
import random
import sys
from fractions import Fraction as Fr

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "review_repair_checks_20261007.json")


# ----------------------------------------------------------------------------------------------------------- E17
def payoff_per_token(votes, stakes, theta, i):
    """Pool payoff per token of voter i (in units of lambda); votes in {"F", "T", None}."""
    vF = sum(s for s, v in zip(stakes, votes) if v == "F")
    vT = sum(s for s, v in zip(stakes, votes) if v == "T")
    win = "F" if vF > theta else ("T" if vT > theta else None)
    if win is None:
        return Fr(0)
    v_win = vF if win == "F" else vT
    if votes[i] == win:
        return (1 - v_win) / v_win
    return Fr(-1)


def is_equilibrium(profile, fixed_votes, fixed_stakes, rest, theta):
    stakes = fixed_stakes + rest
    votes = fixed_votes + [profile] * len(rest)
    for j in range(len(fixed_stakes), len(stakes)):
        base = payoff_per_token(votes, stakes, theta, j)
        for dev in ("F", "T", None):
            if dev == votes[j]:
                continue
            alt = list(votes)
            alt[j] = dev
            if payoff_per_token(alt, stakes, theta, j) > base:
                return False
    return True


def split(total, k, cap, rng):
    """k positive rational stakes summing to total, each at most cap (None if impossible)."""
    if total > k * cap:
        return None
    for _ in range(200):
        w = [Fr(rng.randint(1, 100)) for _ in range(k)]
        xs = [total * wi / sum(w) for wi in w]
        if all(x <= cap for x in xs):
            return xs
    xs = [total / k] * k
    return xs if all(x <= cap for x in xs) else None


def e17(rng, n_inst=4000):
    res = {"bounded_instances": 0, "bounded_allF_ok": 0, "bounded_allT_ok": 0, "bounded_failures": [],
           "break_instances_F": 0, "break_F_detected": 0, "break_instances_T": 0, "break_T_detected": 0}
    for _ in range(n_inst):
        theta = Fr(rng.choice([50, 55, 60, 65, 70]), 100)
        alpha = Fr(rng.randint(0, 40), 100)
        hF = Fr(rng.randint(0, 40), 100)
        hT = Fr(rng.randint(0, 40), 100)
        m = 1 - alpha - hF - hT
        if m <= 0 or alpha + hF > theta:          # below the guarantee only
            continue
        fixed_votes, fixed_stakes = ["F", "F", "T"], [alpha, hF, hT]
        okF, okT = 1 - hT > theta, 1 - alpha - hF > theta
        # bounded remaining stakes: every claimed equilibrium must hold
        cap = min([b for b, ok in ((theta - hT, okF), (theta - alpha - hF, okT)) if ok] or [m])
        if cap > 0:
            k = rng.randint(1, 12)
            rest = split(m, k, cap, rng)
            if rest is not None:
                res["bounded_instances"] += 1
                if okF:
                    good = is_equilibrium("F", fixed_votes, fixed_stakes, rest, theta)
                    res["bounded_allF_ok"] += good
                    if not good:
                        res["bounded_failures"].append(("F", str(theta), str(alpha), str(hF), str(hT), [str(x) for x in rest]))
                if okT:
                    good = is_equilibrium("T", fixed_votes, fixed_stakes, rest, theta)
                    res["bounded_allT_ok"] += good
                    if not good:
                        res["bounded_failures"].append(("T", str(theta), str(alpha), str(hF), str(hT), [str(x) for x in rest]))
                res["bounded_allF_claims"] = res.get("bounded_allF_claims", 0) + okF
                res["bounded_allT_claims"] = res.get("bounded_allT_claims", 0) + okT
        # one remaining stake inside the break interval: the profile must fail
        for prof, ok, h in (("F", okF, hT), ("T", okT, alpha + hF)):
            lo, hi = theta - h, min(1 - 2 * h, m)
            if not ok or hi <= lo:
                continue
            s = lo + (hi - lo) * Fr(rng.randint(1, 99), 100)
            rest = [s] + ([m - s] if m - s > 0 else [])
            key = "F" if prof == "F" else "T"
            res[f"break_instances_{key}"] += 1
            res[f"break_{key}_detected"] += not is_equilibrium(prof, fixed_votes, fixed_stakes, rest, theta)
    res["ok"] = (not res["bounded_failures"]
                 and res["break_F_detected"] == res["break_instances_F"]
                 and res["break_T_detected"] == res["break_instances_T"])
    return res


# ----------------------------------------------------------------------------------------------------------- E18
def rho(f, mu):
    return min(Fr(1), max(Fr(0), (f - mu) / (1 - 2 * mu)))


def e18(N=40):
    rows, ok = {}, True
    for mu in (Fr(1, 10), Fr(1, 5), Fr(3, 10)):
        for hF in (Fr(0), Fr(1, 10), Fr(1, 4), Fr(2, 5)):
            hFn = int(hF * N)
            assert Fr(hFn, N) == hF
            for F_is_yes in (True, False):
                for s in range(0, N - hFn + 1):
                    sigma = Fr(s, N)
                    hTn = N - s - hFn
                    vals, te_leads = [], False
                    for a in range(s + 1):                  # coalition votes for F
                        for b in range(s - a + 1):          # for T
                            for e in range(s - a - b + 1):  # for "too early"; the rest abstains
                                x, y = hFn + a, hTn + b
                                cast = x + y + e
                                if cast == 0:
                                    continue
                                if e > x and e > y:
                                    te_leads = True
                                    continue
                                yes = x if F_is_yes else y
                                pay_yes = rho(Fr(yes, cast), mu)
                                vals.append(pay_yes if F_is_yes else 1 - pay_yes)
                    lo, hi = min(vals), max(vals)
                    want = (rho(hF, mu), rho(hF + sigma, mu))
                    pred_te = sigma > max(hF, (1 - hF) / 2)
                    good = (lo, hi) == want and te_leads == pred_te
                    if not good:
                        ok = False
                        print("MISMATCH", mu, hF, F_is_yes, sigma, lo, hi, want, te_leads, pred_te)
                rows[f"mu={mu} hF={hF} F={'Yes' if F_is_yes else 'No'}"] = "ok"
    return {"N": N, "cases": rows, "ok": ok}


def main():
    rng = random.Random(20261007)
    out = {"E17": e17(rng), "E18": e18()}
    out["all_ok"] = out["E17"]["ok"] and out["E18"]["ok"]
    json.dump(out, open(OUT, "w"), indent=1, default=str)
    print(json.dumps({k: (v if k != "E18" else {"N": v["N"], "ok": v["ok"], "n_cases": len(v["cases"])})
                      for k, v in out.items()}, indent=1, default=str))
    if "--record" in sys.argv:
        raise SystemExit("Ledger recording is available only in the authors workspace; omit --record to reproduce the calculation.")


if __name__ == "__main__":
    main()
