"""E13: the disagreement variant of the tape fallback (oracle_capture_theory_20261006.md, Section 11).

Rule F_mu^d: a DVM resolution pays as the oracle says unless the winner holds less than 1 - mu of the votes cast AND
the winner was the market's underdog before the dispute (its reference price below 1/2); then, and when the request
is deleted after rolling, every share is paid its reference price. F_mu (the paper's main rule) pays the reference
price on every contested resolution.

Setting as in E12 with full participation: a coalition of stake sigma splits into F-votes a, T-votes b and
abstention; honest blocks hF (votes F) and hT = 1 - sigma - hF (votes T). The DVM resolves an answer whose votes
exceed theta of the staked supply, otherwise rolls; with an unchanged electorate a roll repeats until deletion, so a
roll is counted as deletion. Exact integer enumeration on a 1/N grid (N divisible by every denominator).

Claims checked for every (mu, hF, pF) on the grid, theta = 13/20, pF = pre-dispute price of F:
  pF < 1/2 (the market favored the honest answer):
    full capture (F paid 1) iff sigma >= 1 - mu - hF;  reference price forced iff sigma >= 1 - theta - hF;
    below 1 - mu - hF every F share is paid 0 or pF.
  pF >= 1/2 (the market favored the coalition's answer):
    full capture iff sigma > theta - hF;  reference price forced iff sigma > mu - hF (or hF >= mu... at sigma = 0
    when the honest vote is already contested).
  and, for comparison, F_mu: full capture iff sigma >= 1 - mu - hF, reference price iff sigma > mu - hF.
"""
import json
import os
import sys
from fractions import Fraction as Fr

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "variant_probe_results.json")
N = 200
THETA = Fr(13, 20)


def payout_F(rule, x, y, mu, pF):
    """x, y: F and T votes as integers out of N (full participation). Returns F's payout as a Fraction."""
    th = THETA * N
    if x > th:
        w, v, pw = "F", x, pF
    elif y > th:
        w, v, pw = "T", y, 1 - pF
    else:
        return pF                              # roll until deletion: reference price under both rules
    contested = v < (1 - mu) * (x + y)         # winner below 1 - mu of the votes cast
    tape = contested and (rule == "F" or pw < Fr(1, 2))
    if tape:
        return pF
    return Fr(1) if w == "F" else Fr(0)


def scan(rule, mu, hF, pF):
    """Smallest sigma (out of N) for a full capture and for the reference price, plus the set of F payouts seen below
    the full-capture threshold."""
    hFn = int(hF * N)
    first_full = first_tape = None
    seen_below_full = set()
    for s in range(0, N - hFn + 1):
        hTn = N - s - hFn
        full = tape = False
        pays = set()
        for a in range(s + 1):
            for b in range(s - a + 1):
                p = payout_F(rule, hFn + a, hTn + b, mu, pF)
                pays.add(p)
                if p == 1:
                    full = True
                elif p == pF and pF not in (0, 1):
                    tape = True
        if tape and first_tape is None:
            first_tape = s
        if full and first_full is None:
            first_full = s
        if first_full is None:
            seen_below_full |= pays
        if first_full is not None and first_tape is not None:
            break
    return first_full, first_tape, seen_below_full


def main():
    rows, ok = {}, True
    for mu in (Fr(1, 10), Fr(1, 5), Fr(1, 4)):
        for hF in (Fr(0), Fr(1, 10), Fr(1, 4)):
            for pF in (Fr(1, 5), Fr(1, 2), Fr(4, 5)):
                for rule in ("F", "Fd"):
                    full, tape, below = scan(rule, mu, hF, pF)
                    key = f"rule={rule} mu={mu} hF={hF} pF={pF}"
                    rows[key] = {"full": str(Fr(full, N)) if full is not None else None,
                                 "tape": str(Fr(tape, N)) if tape is not None else None,
                                 "payouts_below_full": sorted(str(p) for p in below)}
                    # predictions: the smallest grid point satisfying the weak or strict inequality
                    above = lambda t: t + Fr(1, N) if t >= 0 else Fr(0)   # smallest sigma on the grid with sigma > t
                    if rule == "F":
                        want_full = 1 - mu - hF                        # weak inequality
                        want_tape = above(mu - hF)                     # contested from sigma > mu - hF
                    elif pF < Fr(1, 2):
                        want_full = 1 - mu - hF
                        want_tape = 1 - THETA - hF                     # blocking (roll to deletion), weak
                    else:
                        want_full = above(THETA - hF)                  # F must exceed theta
                        want_tape = above(mu - hF) if pF > Fr(1, 2) else 1 - THETA - hF
                    got_full = Fr(full, N) if full is not None else None
                    got_tape = Fr(tape, N) if tape is not None else None
                    good = (got_full == want_full) and (got_tape == want_tape)
                    if rule == "Fd" and pF < Fr(1, 2):
                        good &= below <= {Fr(0), pF}
                    if rule == "F":
                        good &= below <= {Fr(0), pF}
                    rows[key]["predicted"] = {"full": str(want_full), "tape": str(want_tape)}
                    rows[key]["ok"] = bool(good)
                    ok &= good
                    print(key, "full", got_full, "tape", got_tape, "| predicted", want_full, want_tape, "OK" if good else "MISMATCH")
    rows["all_ok"] = ok
    json.dump(rows, open(OUT, "w"), indent=1)
    print("all claims ok:", ok)

    if "--record" in sys.argv:
        raise SystemExit("Ledger recording is available only in the authors workspace; omit --record to reproduce the calculation.")


if __name__ == "__main__":
    main()
