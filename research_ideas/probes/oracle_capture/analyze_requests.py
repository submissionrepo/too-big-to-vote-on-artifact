"""Second-stage analysis of the DVM history produced by summarize_votes.py.

Reads data/requests_summary.csv and data/votes_long.csv and writes data/analysis.json plus a console report:
  - counts of resolved requests by era (SPAT 50% before 2025-04-20, 65% after) and by requester type
  - distribution of the winning answer's share of staked tokens, and how many resolutions would have rolled
    under the other threshold (counterfactual 50% <-> 65%)
  - contested requests (minority share of votes above a cutoff) and their minority shares, the empirical
    analogue of the honest block h in the model
  - pivotal voters: resolutions where removing the single largest supporter of the winning answer would have
    pushed it below the agreement requirement (the March 2025 pattern), and the smallest supporter coalition
    whose removal does so
  - stall arithmetic: the smallest number of top stakers whose combined stake reaches 1 - SPAT in each round
"""
import csv
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SPAT_CHANGE_BLOCK = 22309220  # GatAndSpatChanged 50% -> 65%, 2025-04-20
CONTESTED_CUTOFF = 0.10       # minority share of votes


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    reqs = list(csv.DictReader(open(os.path.join(DATA, "requests_summary.csv"), encoding="utf-8")))
    votes = list(csv.DictReader(open(os.path.join(DATA, "votes_long.csv"), encoding="utf-8")))
    print("resolved requests:", len(reqs), "| votes in resolving rounds:", len(votes))

    # (roundId, requestTime, identifier) is shared by Polymarket requests of one event; ancKey separates them
    votes_by_req = defaultdict(list)
    for v in votes:
        votes_by_req[(v["roundId"], v["requestTime"], v["identifier"], v["ancKey"])].append(v)

    out = {"n_requests": len(reqs)}
    eras = {"spat50": [r for r in reqs if int(r["resolvedBlock"]) < SPAT_CHANGE_BLOCK],
            "spat65": [r for r in reqs if int(r["resolvedBlock"]) >= SPAT_CHANGE_BLOCK]}
    for era, rs in eras.items():
        shares = sorted(fnum(r["modeShareOfStaked"]) for r in rs if fnum(r["modeShareOfStaked"]) is not None)
        pm = [r for r in rs if r["isPolymarket"] == "True"]
        gov = [r for r in rs if r["isGovernance"] == "True"]
        contested = [r for r in rs if (fnum(r["minorityShareOfVotes"]) or 0) >= CONTESTED_CUTOFF]
        would_roll_65 = sum(1 for s in shares if s <= 0.65)
        would_roll_50 = sum(1 for s in shares if s <= 0.50)
        q = lambda p: shares[int(p * (len(shares) - 1))] if shares else None
        out[era] = {
            "n": len(rs), "n_polymarket": len(pm), "n_governance": len(gov), "n_contested": len(contested),
            "modeShareOfStaked_quantiles": {"min": q(0), "p10": q(0.1), "p50": q(0.5), "p90": q(0.9), "max": q(1.0)},
            "n_mode_share_le_65pct": would_roll_65, "n_mode_share_le_50pct": would_roll_50,
            "participation_median": sorted(fnum(r["participation"]) for r in rs)[len(rs) // 2] if rs else None,
            "contested_minority_shares": sorted(round(fnum(r["minorityShareOfVotes"]), 3) for r in contested),
        }
        print(f"\n[{era}] n={len(rs)} polymarket={len(pm)} governance={len(gov)} contested(minority>={CONTESTED_CUTOFF:.0%})={len(contested)}")
        print(f"   winner share of staked: min {q(0):.3f} p10 {q(0.1):.3f} p50 {q(0.5):.3f} p90 {q(0.9):.3f}")
        print(f"   resolutions with winner share <= 65%: {would_roll_65}  (<= 50%: {would_roll_50})")

    # pivotal analysis on contested requests
    piv_rows = []
    for r in reqs:
        if (fnum(r["minorityShareOfVotes"]) or 0) < CONTESTED_CUTOFF:
            continue
        key = (r["roundId"], r["requestTime"], r["identifier"], r["ancKey"])
        vs = votes_by_req.get(key, [])
        win = r["resolvedPrice"]
        cs = fnum(r["cumulativeStakeAtRound"])
        req = fnum(r["minAgreement"])
        supporters = sorted((fnum(v["numTokens"]) for v in vs if v["price"] == win), reverse=True)
        total_win = sum(supporters)
        # smallest k such that removing the k largest supporters pushes the winner below the requirement
        removed, k = 0.0, 0
        for s in supporters:
            if total_win - removed <= req:
                break
            removed += s
            k += 1
        slack = total_win - req
        piv_rows.append({
            "resolvedBlock": int(r["resolvedBlock"]), "roundId": r["roundId"], "requestTime": r["requestTime"],
            "winner": win, "winnerShareOfStaked": round(total_win / cs, 4) if cs else None,
            "minorityShareOfVotes": round(fnum(r["minorityShareOfVotes"]), 4),
            "slackOverRequirement_UMA": round(slack), "slackShareOfStaked": round(slack / cs, 4) if cs else None,
            "top1SupporterShareOfStaked": round(supporters[0] / cs, 4) if supporters and cs else None,
            "kSupportersWhoseRemovalRolls": k, "isPolymarket": r["isPolymarket"], "text": r["text"][:100],
            "identifier": r["identifier"], "ancKey": r["ancKey"],
        })
    piv_rows.sort(key=lambda x: x["slackShareOfStaked"] if x["slackShareOfStaked"] is not None else 9)
    out["contested_requests_sorted_by_slack"] = piv_rows[:40]
    out["n_contested_single_voter_pivotal"] = sum(1 for p in piv_rows if p["kSupportersWhoseRemovalRolls"] == 1)
    for era, lo, hi in (("spat50", 0, SPAT_CHANGE_BLOCK), ("spat65", SPAT_CHANGE_BLOCK, 10**12)):
        sub = [p for p in piv_rows if lo <= p["resolvedBlock"] < hi]
        out[era]["n_contested_single_voter_pivotal"] = sum(1 for p in sub if p["kSupportersWhoseRemovalRolls"] == 1)
        out[era]["n_contested_k_le_3"] = sum(1 for p in sub if p["kSupportersWhoseRemovalRolls"] <= 3)
        out[era]["n_contested_winner_p4"] = sum(1 for p in sub if p["winner"] == "p4")
        out[era]["pivotal_k_distribution"] = dict(sorted(
            __import__("collections").Counter(p["kSupportersWhoseRemovalRolls"] for p in sub).items()))
        print(f"   [{era}] contested {len(sub)}: single-voter pivotal {out[era]['n_contested_single_voter_pivotal']}, "
              f"k<=3 {out[era]['n_contested_k_le_3']}, winner too-early {out[era]['n_contested_winner_p4']}, "
              f"k distribution {out[era]['pivotal_k_distribution']}")
    with open(os.path.join(DATA, "contested_requests.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(piv_rows[0].keys()))
        w.writeheader()
        w.writerows(piv_rows)
    print(f"\ncontested requests: {len(piv_rows)}; single-voter pivotal: {out['n_contested_single_voter_pivotal']}")
    for p in piv_rows[:15]:
        print(f"   block {p['resolvedBlock']} winner {p['winner']} share {p['winnerShareOfStaked']:.3f} "
              f"slack {p['slackShareOfStaked']:.4f} top1 {p['top1SupporterShareOfStaked']:.3f} k={p['kSupportersWhoseRemovalRolls']} "
              f"minority {p['minorityShareOfVotes']:.3f} pm={p['isPolymarket']} :: {p['text'][:70]!r}")

    # stall arithmetic per round: smallest number of top voters reaching 1 - spat
    by_round = defaultdict(dict)
    for v in votes:
        by_round[v["roundId"]][v["voter"]] = max(by_round[v["roundId"]].get(v["voter"], 0.0), fnum(v["numTokens"]) or 0.0)
    cs_by_round = {r["roundId"]: fnum(r["cumulativeStakeAtRound"]) for r in reqs}
    stall = []
    for rid, stakes in by_round.items():
        cs = cs_by_round.get(rid)
        if not cs:
            continue
        thr = 0.5 if int(rid) * 172800 < 1745139000 else 0.35  # before/after 2025-04-20 (approx by round time)
        top = sorted(stakes.values(), reverse=True)
        acc, k = 0.0, 0
        for s in top:
            acc += s
            k += 1
            if acc >= thr * cs:
                break
        stall.append({"roundId": int(rid), "threshold": thr, "top1Share": round(top[0] / cs, 4),
                      "kToStall": k if acc >= thr * cs else None, "nVoters": len(top)})
    stall.sort(key=lambda x: x["roundId"])
    out["stall_by_round_first_last"] = stall[:3] + stall[-3:]
    out["stall_min_k_overall"] = min((s["kToStall"] for s in stall if s["kToStall"]), default=None)
    out["stall_top1_max"] = max(s["top1Share"] for s in stall) if stall else None
    print(f"\nstall arithmetic over {len(stall)} rounds: min k to reach 1-SPAT = {out['stall_min_k_overall']}, "
          f"max single-voter share = {out['stall_top1_max']}")
    for s in stall[-5:]:
        print("   ", s)

    json.dump(out, open(os.path.join(DATA, "analysis.json"), "w"), indent=1)
    print("wrote", os.path.join(DATA, "analysis.json"))


if __name__ == "__main__":
    main()
