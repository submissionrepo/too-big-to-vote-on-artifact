"""Fetch VoteRevealed (and RequestResolved / RequestRolled) logs in a date window and print per-request tallies.

Usage: python quick_tally.py 2025-03-20 2025-03-28 [substring-filter-on-ancillary-text]
Writes the decoded votes to data/quick_tally_<from>_<to>.json.
"""
import json
import os
import sys
from collections import defaultdict

from abi_min import EVENTS, ancillary_to_text, decode_log, event_topic
from rpc import Rpc, VOTING_V2
from state_reads import block_at, read_round, ts

HERE = os.path.dirname(os.path.abspath(__file__))

P1, P2, P3 = 0, 10**18, 5 * 10**17
TOO_EARLY = -(1 << 255)


def label(price):
    return {P1: "p1/NO", P2: "p2/YES", P3: "p3/50-50", TOO_EARLY: "p4/too-early"}.get(price, str(price))


def main():
    d0, d1 = sys.argv[1], sys.argv[2]
    filt = sys.argv[3] if len(sys.argv) > 3 else None
    rpc = Rpc()
    b0, b1 = block_at(rpc, ts(d0)), block_at(rpc, ts(d1))
    print(f"blocks {b0}..{b1}")
    topics = [event_topic(EVENTS[n][0]) for n in ("VoteRevealed", "RequestResolved", "RequestRolled", "RequestAdded")]
    logs = rpc.get_logs_range(VOTING_V2, [topics], b0, b1)
    print("logs", len(logs))
    decoded = []
    for lg in logs:
        name, f = decode_log(lg)
        if name:
            f["event"] = name
            f["text"] = ancillary_to_text(f["ancillaryData"])[:400]
            decoded.append(f)
    safe = lambda s: s.replace(":", "").replace("T", "_")  # Windows file names cannot contain ':'
    out = os.path.join(HERE, "data", f"quick_tally_{safe(d0)}_{safe(d1)}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(decoded, open(out, "w"), indent=0, default=str)

    # Group reveals by request key (identifier, time, ancillaryData)
    groups = defaultdict(list)
    for f in decoded:
        if f["event"] == "VoteRevealed":
            groups[(f["identifier"], f["time"], f["ancillaryData"])].append(f)
    resolved = {(f["identifier"], f["time"], f["ancillaryData"]): f for f in decoded if f["event"] == "RequestResolved"}
    rolled = defaultdict(list)
    for f in decoded:
        if f["event"] == "RequestRolled":
            rolled[(f["identifier"], f["time"], f["ancillaryData"])].append(f["rollCount"])

    rounds_cache = {}
    for key, votes in sorted(groups.items(), key=lambda kv: kv[1][0]["blockNumber"]):
        text = ancillary_to_text(key[2])
        if filt and filt.lower() not in text.lower():
            continue
        by_price = defaultdict(int)
        by_voter = defaultdict(int)
        rids = set()
        for v in votes:
            by_price[v["price"]] += v["numTokens"]
            by_voter[v["voter"]] += v["numTokens"]
            rids.add(v["roundId"])
        total = sum(by_price.values())
        rid = max(rids)
        if rid not in rounds_cache:
            rounds_cache[rid] = read_round(rpc, rid)
        rd = rounds_cache[rid]
        cs = rd["cumulativeStakeAtRound"]
        print("=" * 100)
        print(f"request time={key[1]} round={sorted(rids)} voters={len(by_voter)} totalVotes={total/1e18:,.0f} UMA")
        print(f"  cumulativeStakeAtRound={cs/1e18:,.0f}  minParticipation={rd['minParticipationRequirement']/1e18:,.0f}  "
              f"minAgreement={rd['minAgreementRequirement']/1e18:,.0f}  ({rd['minAgreementRequirement']/cs:.3f} of staked)")
        print(f"  text: {text[:300]!r}")
        for p, n in sorted(by_price.items(), key=lambda kv: -kv[1]):
            print(f"    {label(p):14s} {n/1e18:>14,.0f} UMA  {n/total:6.1%} of votes  {n/cs:6.1%} of staked")
        if key in resolved:
            print(f"  RESOLVED -> {label(resolved[key]['price'])} at block {resolved[key]['blockNumber']}")
        if key in rolled:
            print(f"  rolled: rollCounts {rolled[key]}")
        top = sorted(by_voter.items(), key=lambda kv: -kv[1])[:12]
        for addr, n in top:
            votes_of = {label(v["price"]) for v in votes if v["voter"] == addr}
            print(f"    {addr} {n/1e18:>12,.0f} UMA {n/total:6.1%}  voted {','.join(sorted(votes_of))}")


if __name__ == "__main__":
    main()
