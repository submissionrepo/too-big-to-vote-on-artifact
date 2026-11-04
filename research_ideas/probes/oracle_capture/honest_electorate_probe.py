"""E12: thresholds against an honest electorate (oracle_capture_theory_20261006.md, Section 5c).

Setting: the whole non-coalition stake is honest: a block hT votes the true answer T and a block hF votes the
coalition's answer F; each honest voter participates with probability pi (the rest abstain), so honest votes are
pi*hT and pi*hF. The coalition sigma = 1 - hT - hF splits into F-votes a, T-votes b, abstention c.
For each rule we compute, by exact enumeration on a 1/N grid of the coalition's splits, the smallest sigma that can
  stall    no answer resolves
  capture  F resolves (0/1 payout to F)
  tape     the fallback F_mu pays the reference price (T or F wins with winner share < 1 - mu, or a roll)
Rules: threshold against all staked tokens (deployed) and against votes cast, each with the fallback trigger measured
against the same denominator.
Claims checked:
  (i)  stall: both denominators need 1 - theta - hF at pi = 1 (the votes-cast rule does not double it);
  (ii) capture: theta - hF (staked) and theta*pi*(1) - pi*hF... reported, not asserted;
  (iii) tape-forcing under F_mu: mu - hF (votes cast, pi = 1); under the staked trigger with pi < 1 it drops to
       1 - hF - (1 - mu)/pi, e.g. 16.7% for mu = .2, pi = .96, hF = 0: below today's largest stake (16.86%).
"""
import json
import os
import sys
from fractions import Fraction as Fr

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "honest_electorate_results.json")
N = 400


def outcome(rule, theta, x, y, S=Fr(1)):
    """x, y: stake voting F and T (absolute shares of the supply). Returns 'F', 'T' or None (roll)."""
    if rule == "staked":
        if x > theta * S:
            return "F"
        if y > theta * S:
            return "T"
        return None
    tot = x + y
    if tot == 0:
        return None
    if x > theta * tot:
        return "F"
    if y > theta * tot:
        return "T"
    return None


def winner_share(rule, x, y, win):
    v = x if win == "F" else y
    if rule == "staked":
        return v
    return v / (x + y)


def min_sigma(goal, rule, theta, hF, pi, mu):
    """Smallest sigma on the grid that achieves the goal against the honest electorate."""
    for sk in range(0, N + 1):
        sigma = Fr(sk, N)
        hT = 1 - sigma - hF
        if hT < 0:
            return None
        for ak in range(sk + 1):
            for bk in range(sk - ak + 1):
                a, b = Fr(ak, N), Fr(bk, N)
                x = pi * hF + a
                y = pi * hT + b
                w = outcome(rule, theta, x, y)
                if goal == "stall" and w is None:
                    return sigma
                if goal == "capture" and w == "F":
                    return sigma
                if goal == "tape":
                    if w is None:
                        return sigma
                    if winner_share(rule, x, y, w) < 1 - mu:
                        return sigma
                if goal == "capture01" and w == "F" and winner_share(rule, x, y, w) >= 1 - mu:
                    return sigma
    return None


def main():
    theta, mu = Fr(13, 20), Fr(1, 5)
    rows = {}
    ok = True
    for pi in (Fr(1), Fr(24, 25)):
        for hF in (Fr(0), Fr(1, 10), Fr(1, 4)):
            for rule in ("staked", "votes"):
                key = f"pi={pi} hF={hF} rule={rule}"
                r = {g: min_sigma(g, rule, theta, hF, pi, mu) for g in ("stall", "capture", "tape", "capture01")}
                rows[key] = {g: (str(v) if v is not None else None) for g, v in r.items()}
                print(key, {g: (float(v) if v is not None else None) for g, v in r.items()})
                if pi == 1:
                    # (i) stall equals 1 - theta - hF (grid: first point at or above, strictness gives one step)
                    st = r["stall"]
                    ok &= st is not None and (1 - theta - hF) <= st <= (1 - theta - hF) + Fr(1, N)
                    # (iii) tape-forcing equals mu - hF (one grid step for strict inequality)
                    tp = r["tape"]
                    ok &= tp is not None and max(Fr(0), mu - hF) <= tp <= max(Fr(0), mu - hF) + Fr(1, N)
    # (iii) staked trigger with pi = .96, hF = 0: 1 - (1 - mu)/pi
    pred = 1 - (1 - mu) / Fr(24, 25)
    got = Fr(rows["pi=24/25 hF=0 rule=staked"]["tape"])
    ok &= pred <= got <= pred + Fr(1, N)
    rows["staked_trigger_tape_pi096_pred"] = str(pred)
    rows["largest_stake_today"] = "0.16857"
    rows["all_ok"] = ok
    json.dump(rows, open(OUT, "w"), indent=1)
    print("predicted staked-trigger tape threshold at pi = .96, hF = 0:", float(pred), "| all claims ok:", ok)

    if "--record" in sys.argv:
        raise SystemExit("Ledger recording is available only in the authors workspace; omit --record to reproduce the calculation.")


if __name__ == "__main__":
    main()
