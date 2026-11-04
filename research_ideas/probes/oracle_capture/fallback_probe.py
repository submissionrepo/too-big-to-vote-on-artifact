"""E8: the tape-fallback rule F_mu against the DVM history (oracle_capture_theory_20261006.md, Section 6, T6).

Rule F_mu: a resolution pays 0/1 by the oracle only if the winner's share of staked tokens x* >= 1 - mu;
otherwise (contested) and whenever the request is deleted after rho_max rolls, every share pays the
pre-dispute reference price. This script computes, from data/requests_summary.csv:
  - the trigger rate: share of historical resolutions with x* < 1 - mu, by SPAT era and overall;
  - the capture requirement uplift: 1 - mu - h_F versus theta - h_F for the March h_F and the contested quantiles;
  - how many of the 169 contested resolutions and the 56 single-voter-pivotal ones would have paid at the tape.
Exact rational arithmetic on the recorded shares; results to data/fallback_probe_results.json.
"""
import csv
import json
import os
from fractions import Fraction as Fr

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SPAT_CHANGE_BLOCK = 22309220
MUS = [Fr(1, 10), Fr(3, 20), Fr(1, 5), Fr(1, 4), Fr(3, 10)]
# March: the payout-deciding request (index 827); the first request (828, Yes 11,465,793) settled only the bonds
H_F = {"march": Fr(12292521 - 5083491, 22845749), "p25": Fr(138, 1000), "median": Fr(188, 1000), "p75": Fr(256, 1000)}
TOP4 = Fr(3263178 + 1611497 + 1162487 + 1149045, 19357995)
TOP1 = Fr(3263178, 19357995)


def main():
    reqs = list(csv.DictReader(open(os.path.join(DATA, "requests_summary.csv"), encoding="utf-8")))
    cont = list(csv.DictReader(open(os.path.join(DATA, "contested_requests.csv"), encoding="utf-8")))
    out = {"n_resolved": len(reqs), "n_contested": len(cont)}
    shares = [(int(r["resolvedBlock"]), Fr(r["modeShareOfStaked"]), r["isPolymarket"] == "True")
              for r in reqs if r["modeShareOfStaked"]]
    for mu in MUS:
        bar = 1 - mu
        row = {"bar_1_minus_mu": float(bar)}
        for era, sel in (("all", lambda b: True), ("spat50", lambda b: b < SPAT_CHANGE_BLOCK),
                         ("spat65", lambda b: b >= SPAT_CHANGE_BLOCK)):
            sub = [s for s in shares if sel(s[0])]
            trig = sum(1 for s in sub if s[1] < bar)
            row[f"trigger_{era}"] = {"n": len(sub), "paid_at_tape": trig, "rate": float(Fr(trig, len(sub))) if sub else None}
        csub = [c for c in cont if c["winnerShareOfStaked"]]
        ctrig = sum(1 for c in csub if Fr(c["winnerShareOfStaked"]) < bar)
        piv = [c for c in csub if c["kSupportersWhoseRemovalRolls"] == "1"]
        ptrig = sum(1 for c in piv if Fr(c["winnerShareOfStaked"]) < bar)
        row["contested_paid_at_tape"] = {"n": len(csub), "tape": ctrig}
        row["single_voter_pivotal_paid_at_tape"] = {"n": len(piv), "tape": ptrig}
        up = {}
        for name, hf in H_F.items():
            req_tape = bar - hf          # stake needed for a 0/1 capture under F_mu
            req_65 = Fr(13, 20) - hf     # stake needed today
            up[name] = {"h_F": float(hf), "capture_req_theta65": float(req_65), "capture_req_F_mu": float(req_tape),
                        "top4_can_capture_now": TOP4 > req_65, "top4_can_capture_F_mu": TOP4 > req_tape,
                        "top1_can_capture_F_mu": TOP1 > req_tape}
        row["capture_requirement"] = up
        out[f"mu_{mu}"] = row

    # ---- votes-cast trigger (the version the paper recommends): winner share of the votes cast = 1 - minority share
    vshares = [(int(r["resolvedBlock"]), 1 - Fr(r["minorityShareOfVotes"]))
               for r in reqs if r["minorityShareOfVotes"]]
    stakes_now = [Fr(r["shareOfCumulative"]) for r in csv.DictReader(open(os.path.join(DATA, "voters_current.csv"), encoding="utf-8"))]
    stakes_now.sort(reverse=True)
    vc = {}
    for mu in MUS:
        bar = 1 - mu
        row = {"bar_1_minus_mu": float(bar)}
        for era, sel in (("all", lambda b: True), ("spat50", lambda b: b < SPAT_CHANGE_BLOCK),
                         ("spat65", lambda b: b >= SPAT_CHANGE_BLOCK)):
            sub = [s for s in vshares if sel(s[0])]
            trig = sum(1 for s in sub if s[1] < bar)
            row[f"trigger_{era}"] = {"n": len(sub), "paid_at_tape": trig, "rate": float(Fr(trig, len(sub))) if sub else None}
        csub = [c for c in cont if c["minorityShareOfVotes"]]
        row["contested_paid_at_tape"] = {"n": len(csub), "tape": sum(1 for c in csub if 1 - Fr(c["minorityShareOfVotes"]) < bar)}
        piv = [c for c in csub if c["kSupportersWhoseRemovalRolls"] == "1"]
        row["single_voter_pivotal_paid_at_tape"] = {"n": len(piv), "tape": sum(1 for c in piv if 1 - Fr(c["minorityShareOfVotes"]) < bar)}
        # stake that forces the tape against an honest electorate with no honest support (hF = 0): more than mu
        acc, k = Fr(0), 0
        for s in stakes_now:
            acc += s
            k += 1
            if acc > mu:
                break
        row["largest_stakers_to_force_tape_hF0"] = k
        row["capture_req_march"] = float(bar - H_F["march"])
        vc[f"mu_{mu}"] = row
    out["votes_cast"] = vc
    # who can block today under the deployed rule: era-B resolutions whose winner held less than 65% + the largest stake
    top1 = stakes_now[0]
    eraB = [s for b, s, pm in shares if b >= SPAT_CHANGE_BLOCK]
    eraB_cont = [c for c in cont if int(c["resolvedBlock"]) >= SPAT_CHANGE_BLOCK]
    out["block_by_largest_staker"] = {
        "top1": float(top1),
        "eraB_resolutions": len(eraB),
        "eraB_below_65_plus_top1": sum(1 for s in eraB if s < Fr(13, 20) + top1),
        "eraB_contested": len(eraB_cont),
        "eraB_contested_below_65_plus_top1": sum(1 for c in eraB_cont if Fr(c["winnerShareOfStaked"]) < Fr(13, 20) + top1),
    }
    json.dump(out, open(os.path.join(DATA, "fallback_probe_results.json"), "w"), indent=1, default=str)
    for mu in MUS:
        r = vc[f"mu_{mu}"]
        print(f"[votes cast] mu={float(mu):.2f}: tape all {r['trigger_all']['rate']:.3%}, era B {r['trigger_spat65']['rate']:.3%} "
              f"({r['trigger_spat65']['paid_at_tape']}/{r['trigger_spat65']['n']}); contested {r['contested_paid_at_tape']['tape']}/"
              f"{r['contested_paid_at_tape']['n']}; pivotal {r['single_voter_pivotal_paid_at_tape']['tape']}/{r['single_voter_pivotal_paid_at_tape']['n']}; "
              f"capture req (March hF) {r['capture_req_march']:.4f}; largest stakers to force tape {r['largest_stakers_to_force_tape_hF0']}")
    print("[block] ", out["block_by_largest_staker"])
    for mu in MUS:
        r = out[f"mu_{mu}"]
        print(f"mu={float(mu):.2f} bar={r['bar_1_minus_mu']:.2f}: tape rate all {r['trigger_all']['rate']:.3%} "
              f"(spat50 {r['trigger_spat50']['rate']:.3%}, spat65 {r['trigger_spat65']['rate']:.3%}); "
              f"contested paid at tape {r['contested_paid_at_tape']['tape']}/{r['contested_paid_at_tape']['n']}; "
              f"single-voter pivotal {r['single_voter_pivotal_paid_at_tape']['tape']}/{r['single_voter_pivotal_paid_at_tape']['n']}; "
              f"march capture req {r['capture_requirement']['march']['capture_req_theta65']:.3f} -> {r['capture_requirement']['march']['capture_req_F_mu']:.3f} "
              f"(top4 now {r['capture_requirement']['march']['top4_can_capture_now']}, under F_mu {r['capture_requirement']['march']['top4_can_capture_F_mu']})")
    print("wrote fallback_probe_results.json")

    if "--record" in sys.argv:
        raise SystemExit("Ledger recording is available only in the authors workspace; omit --record to reproduce the calculation.")


if __name__ == "__main__":
    import sys
    main()
