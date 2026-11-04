"""E9: tally-only resolution rules (oracle_capture_theory_20261006.md, Section 5b, T7).

A tally-only rule maps the pair (x, y) = (F share, T share) of total stake (abstention = 1 - x - y) to F, T or roll.
Three families are checked on an exact 1/N grid by brute force over coalition splits and all responses of the
remaining stake:
  staked(theta):  F iff x > theta,  T iff y > theta                     (UMA DVM 2.0: SPAT against cumulativeStake)
  votes(theta):   F iff x > theta (x + y), T iff y > theta (x + y)       (same threshold against votes cast)
  conj(t1, t2):   F iff x >= t1 and y <= t2, T symmetric                 (a rule that is not a threshold on any one share)
Quantities (all as shares of total stake):
  theta_F   full-participation threshold: smallest x with f(x, 1 - x) = F
  sigma_cap(h) smallest coalition that, with a sincere F block h, forces F against every response of the rest
  kappa     smallest coalition that can force roll against every response of the rest (it may split its stake
            between F, T and abstention)
  deadlock  width of the full-participation band where nothing resolves
Claims checked (T7): sigma_cap(h) = theta_F - h for all three; 1 - theta_F <= kappa <= 2 (1 - theta_F) with the lower
bound attained by staked and the upper bound by votes and conj; deadlock = 2 theta_F - 1.
Grid arithmetic is exact (integers out of N); each claim is a finite statement about the grid instances.
"""
import json
import os
import sys
from fractions import Fraction as Fr

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "tally_rules_probe_results.json")
N = 40  # grid resolution; all masses are multiples of 1/N


def rule_staked(theta):
    def f(x, y):
        if x > theta:
            return "F"
        if y > theta:
            return "T"
        return None
    return f


def rule_votes(theta):
    def f(x, y):
        tot = x + y
        if tot == 0:
            return None
        if x > theta * tot:
            return "F"
        if y > theta * tot:
            return "T"
        return None
    return f


def rule_conj(t1, t2):
    def f(x, y):
        if x >= t1 and y <= t2:
            return "F"
        if y >= t1 and x <= t2:
            return "T"
        return None
    return f


def theta_F(f):
    for k in range(N + 1):
        x = Fr(k, N)
        if f(x, 1 - x) == "F":
            return x
    return None


def deadlock_width(f):
    band = [Fr(k, N) for k in range(N + 1) if f(Fr(k, N), 1 - Fr(k, N)) is None]
    return (max(band) - min(band) + Fr(1, N)) if band else Fr(0), band


def sigma_cap(f, h):
    """Smallest sigma (grid) such that for every response (u, w) of the remaining 1 - sigma - h stake, f = F."""
    hk = int(h * N)
    for sk in range(0, N - hk + 1):
        rest = N - sk - hk
        ok = True
        for uk in range(rest + 1):
            for wk in range(rest - uk + 1):
                if f(Fr(sk + hk + uk, N), Fr(wk, N)) != "F":
                    ok = False
                    break
            if not ok:
                break
        if ok:
            return Fr(sk, N)
    return None


def kappa(f):
    """Smallest sigma (grid) for which some split (a, b, c) of the coalition forces roll against every response."""
    for sk in range(0, N + 1):
        rest = N - sk
        for ak in range(sk + 1):
            for bk in range(sk - ak + 1):
                ok = True
                for uk in range(rest + 1):
                    for wk in range(rest - uk + 1):
                        if f(Fr(ak + uk, N), Fr(bk + wk, N)) is not None:
                            ok = False
                            break
                    if not ok:
                        break
                if ok:
                    return Fr(sk, N), (Fr(ak, N), Fr(bk, N), Fr(sk - ak - bk, N))
    return None, None


def sigma_cap_realistic(theta, h, pi, denom):
    """Capture requirement when a fraction 1 - pi of the opposition abstains (closed forms compared to brute force)."""
    # others: opposition votes T with mass (pi - sigma - h) and abstains with mass 1 - pi
    for sk in range(0, N + 1):
        s = Fr(sk, N)
        x = s + h
        y = pi - s - h
        if y < 0:
            y = Fr(0)
        if denom == "staked":
            res = x > theta
        else:
            res = x > theta * (x + y)
        if res:
            return s
    return None


def main():
    results = {"N": N}
    # exact theta_F (the continuous infimum): theta for the two threshold families, max(t1, 1 - t2) for conj
    cases = [
        ("staked_0.50", rule_staked(Fr(1, 2)), Fr(1, 2)),
        ("staked_0.65", rule_staked(Fr(13, 20)), Fr(13, 20)),
        ("votes_0.50", rule_votes(Fr(1, 2)), Fr(1, 2)),
        ("votes_0.65", rule_votes(Fr(13, 20)), Fr(13, 20)),
        ("conj_0.60_0.20", rule_conj(Fr(3, 5), Fr(1, 5)), Fr(4, 5)),
        ("conj_0.55_0.30", rule_conj(Fr(11, 20), Fr(3, 10)), Fr(7, 10)),
    ]
    hs = [Fr(0), Fr(4, 40), Fr(10, 40), Fr(11, 40)]  # grid-aligned sincere F blocks: 0, 10%, 25%, 27.5%
    all_ok = True
    for name, f, theta in cases:
        tF_grid = theta_F(f)          # first grid point resolving F on the full-participation line
        tF = theta                    # exact infimum
        dw, band = deadlock_width(f)
        kap, split = kappa(f)
        caps = {str(h): sigma_cap(f, h) for h in hs}
        row = {"theta_F_exact": str(tF), "theta_F_grid": str(tF_grid), "deadlock_width_grid": str(dw),
               "deadlock_band": [str(b) for b in (band[0], band[-1])] if band else [],
               "kappa": str(kap), "kappa_split_F_T_abstain": [str(v) for v in split] if split else None,
               "sigma_cap": {k: str(v) for k, v in caps.items()}}
        # claim (a): the brute-force capture coalition equals the first grid sigma with f(sigma + h, 1 - sigma - h) = F,
        # i.e. the worst case is full opposition participation and the requirement is theta_F - h (grid-rounded)
        pred_caps = {}
        for h in hs:
            # predicted: smallest grid sigma with f(sigma + h, 1 - sigma - h) == F
            pred = None
            for sk in range(0, N + 1):
                s = Fr(sk, N)
                if s + h <= 1 and f(s + h, 1 - s - h) == "F":
                    pred = s
                    break
            pred_caps[str(h)] = pred
        c1 = all(caps[k] == pred_caps[k] for k in caps) and all(
            tF - h <= caps[str(h)] <= tF - h + Fr(1, N) for h in hs)   # grid value within one step above theta_F - h
        lower, upper = 1 - tF, 2 * (1 - tF)
        # kappa is an infimum; the grid returns the first grid point at or above it
        c2 = (kap is not None) and (lower <= kap <= upper + Fr(1, N))
        # the full-participation band {x : f(x, 1-x) = roll} is [1 - theta_F, theta_F] up to end points
        c3 = abs(dw - (2 * tF - 1)) <= Fr(1, N)
        row.update({"claim_cap_equals_full_participation_threshold": c1, "claim_kappa_in_bounds": c2,
                    "kappa_lower_1_minus_thetaF": str(lower), "kappa_upper_2_1_minus_thetaF": str(upper),
                    "claim_deadlock_width": c3, "deadlock_pred": str(2 * tF - 1)})
        results[name] = row
        all_ok &= c1 and c2 and c3
        print(f"{name:16s} theta_F={tF} deadlock={dw} kappa={kap} split={row['kappa_split_F_T_abstain']} "
              f"caps={row['sigma_cap']} bounds=[{lower},{upper}] ok={c1 and c2 and c3}")
    # which family attains which bound (exact grid values)
    att = {"staked_0.65_kappa": results["staked_0.65"]["kappa"], "staked_lower_bound": str(1 - Fr(13, 20)),
           "votes_0.65_kappa": results["votes_0.65"]["kappa"], "votes_upper_bound": str(2 * (1 - Fr(13, 20))),
           "votes_0.50_kappa": results["votes_0.50"]["kappa"], "conj_0.60_0.20_kappa": results["conj_0.60_0.20"]["kappa"],
           "conj_upper_bound": str(2 * (1 - Fr(4, 5)))}
    att["staked_attains_lower"] = Fr(att["staked_0.65_kappa"]) == Fr(att["staked_lower_bound"])
    att["votes_attains_upper"] = Fr(att["votes_0.65_kappa"]) == Fr(att["votes_upper_bound"])
    att["conj_within_one_step_of_upper"] = Fr(0) <= Fr(att["conj_0.60_0.20_kappa"]) - Fr(att["conj_upper_bound"]) <= Fr(1, N)
    results["kappa_attainment"] = att
    all_ok &= att["staked_attains_lower"] and att["votes_attains_upper"] and att["conj_within_one_step_of_upper"]
    # realistic capture with participation pi = 0.96, h = March's honest Yes support in the payout-deciding request
    # (index 827: Yes 12,292,521 minus the three wallets' 5,083,491, of 22,845,749 staked), theta = 0.65
    pi = Fr(24, 25)
    h = Fr(12292521 - 5083491, 22845749)
    results["realistic_capture_pi096"] = {
        "staked": str(sigma_cap_realistic(Fr(13, 20), h, pi, "staked")),
        "votes": str(sigma_cap_realistic(Fr(13, 20), h, pi, "votes")),
        "closed_form_staked": str(Fr(13, 20) - h), "closed_form_votes": str(Fr(13, 20) * pi - h),
    }
    print("realistic capture (pi=0.96, h=31.56%, theta=.65):", results["realistic_capture_pi096"])
    results["all_claims_ok"] = all_ok
    json.dump(results, open(OUT, "w"), indent=1)
    print("all_claims_ok", all_ok, "->", OUT)

    if "--record" in sys.argv:
        raise SystemExit("Ledger recording is available only in the authors workspace; omit --record to reproduce the calculation.")


if __name__ == "__main__":
    main()
