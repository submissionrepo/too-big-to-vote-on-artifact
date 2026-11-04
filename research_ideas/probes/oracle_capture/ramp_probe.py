"""E14: ramp settlement R_mu (oracle_capture_theory_20261006.md, Section 12).

Rule R_mu, mu in (0, 1/2): a disputed question is settled on the tally of its first DVM round, whether or not the DVM
resolves it (a modal "too early" re-asks the question as today), and pays the
shares of an answer whose share of the votes cast is f the amount rho(f) = clip((f - mu) / (1 - 2 mu), 0, 1); the two
sides of a binary market are paid rho(f) and rho(1 - f) = 1 - rho(f). No market price enters.

Setting (as E12/E13, full participation): honest blocks hF (votes F) and hT = 1 - sigma - hF (votes T); a coalition of
stake sigma splits into F-votes a, T-votes b and abstention c. F's share of the votes cast is
f = (hF + a) / (1 - c). Exact integer enumeration on a 1/N grid.

Claims checked for every (mu, hF, sigma) on the grid:
  (i)   over all coalition splits, F's payout ranges exactly over [rho(hF), rho(hF + sigma)], so the coalition moves any
        share's payout by at most sigma / (1 - 2 mu), with equality while hF + sigma stays in the linear part;
  (ii)  F is paid one dollar iff sigma >= 1 - mu - hF;
  (iii) the payout is unchanged by rolling: blocking (keeping both answers below theta) gives a payout between the same
        bounds, so there is no cheaper route to any payout than voting.
Also checks the self-financing identity behind the appendix remark on F_mu: buying q_k shares at prices p_k over a
window whose reference price is the quantity-weighted mean costs exactly what the reference price pays on them.
"""
import json
import os
import sys
from fractions import Fraction as Fr

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "ramp_probe_results.json")
N = 200
THETA = Fr(13, 20)


def rho(f, mu):
    return min(Fr(1), max(Fr(0), (f - mu) / (1 - 2 * mu)))


def payouts(mu, hF, s):
    """All F payouts reachable by a coalition of s/N, and whether each came from a roll."""
    hFn = int(hF * N)
    hTn = N - s - hFn
    out = []
    for a in range(s + 1):
        for b in range(s - a + 1):
            c = s - a - b
            x, y = hFn + a, hTn + b
            cast = N - c
            if cast == 0:
                continue
            f = Fr(x, cast)
            rolled = not (x > THETA * N or y > THETA * N)
            out.append((rho(f, mu), rolled))
    return out


def main():
    rows, ok = {}, True
    for mu in (Fr(1, 10), Fr(1, 5), Fr(1, 4), Fr(3, 10)):
        for hF in (Fr(0), Fr(1, 10), Fr(1, 4), Fr(2, 5)):
            first_full = None
            worst_gap = Fr(0)
            for s in range(0, N - int(hF * N) + 1):
                sigma = Fr(s, N)
                ps = payouts(mu, hF, s)
                vals = [p for p, _ in ps]
                lo, hi = min(vals), max(vals)
                want_lo, want_hi = rho(hF, mu), rho(hF + sigma, mu)
                good = (lo == want_lo) and (hi == want_hi) and (hi - lo <= sigma / (1 - 2 * mu))
                # (iii) a roll never reaches outside the voting range
                good &= all(want_lo <= p <= want_hi for p, r in ps if r)
                if not good:
                    ok = False
                    print("MISMATCH", mu, hF, sigma, lo, hi, want_lo, want_hi)
                if hi == 1 and first_full is None:
                    first_full = sigma
                worst_gap = max(worst_gap, (hi - lo) - sigma / (1 - 2 * mu))
            want_full = max(Fr(0), 1 - mu - hF)
            good_full = first_full == want_full
            ok &= good_full
            key = f"mu={mu} hF={hF}"
            rows[key] = {"first_full_capture": str(first_full), "predicted": str(want_full), "ok": bool(good_full),
                         "max(range - sigma/(1-2mu))": str(worst_gap)}
            print(key, "full capture from", first_full, "predicted", want_full, "OK" if good_full else "MISMATCH")
    # self-financing identity: sum q_k p_k == (sum q_k) * (sum q_k p_k / sum q_k), exact on random rationals
    import random
    random.seed(7)
    ident = True
    for _ in range(1000):
        q = [Fr(random.randint(1, 50)) for _ in range(12)]
        p = [Fr(random.randint(1, 99), 100) for _ in range(12)]
        ref = sum(qi * pi for qi, pi in zip(q, p)) / sum(q)
        ident &= sum(qi * pi for qi, pi in zip(q, p)) == sum(q) * ref
    rows["self_financing_identity_1000_draws"] = ident
    ok &= ident
    rows["all_ok"] = ok
    json.dump(rows, open(OUT, "w"), indent=1)
    print("all claims ok:", ok)

    if "--record" in sys.argv:
        raise SystemExit("Ledger recording is available only in the authors workspace; omit --record to reproduce the calculation.")


if __name__ == "__main__":
    main()
