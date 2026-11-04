"""Python port of the DVM 2.0 resolution and slashing arithmetic, validated against on-chain VoterSlashed events,
then used for counterfactuals on the 2025-03 rare-earth requests (indices 827 and 828, round 10085).

Port (integer arithmetic exactly as VotingV2.sol / ResultComputationV2.sol / FixedSlashSlashingLibrary):
  resolved  iff totalVotes > minParticipation (= gat) and modeVotes > minAgreement (= spat * cumulativeStake / 1e18)
  totalSlashed = (noVoteSlash * (S - totalVotes) + wrongVoteSlash * (totalVotes - totalCorrect)) // 1e18
  correct voter  : + stake * totalSlashed // totalCorrect
  wrong voter    : - stake * wrongVoteSlash // 1e18
  absent staker  : - stake * noVoteSlash // 1e18
with wrongVoteSlash = noVoteSlash = baseSlashAmount = 1e15 for non-governance requests.

Validation: VoterSlashed(voter, requestIndex, slashedTokens) is emitted lazily when a staker's trackers update, so
the comparison covers the voters whose events exist in the scanned window; absent stakers need their round stake,
which is not in the vote events, so they are compared only when their event exists and stake can be inferred
(slashedTokens / noVoteSlash).

Usage: python dvm_port.py [--fetch] [--record]
  --fetch  pulls VoterSlashed logs for indices 827/828 from the resolution block onward (about 180 range calls)
"""
import json
import os
import sys
from collections import defaultdict

from abi_min import EVENTS, decode_log, event_topic
from rpc import Rpc, VOTING_V2
from state_reads import read_round

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TALLY = os.path.join(DATA, "quick_tally_2025-03-20_000000_2025-03-28_000000.json")
SLASH_RAW = os.environ.get("SLASH_RAW", os.path.join(DATA, "raw", "voterslashed_827_828.jsonl"))
OUT = os.path.join(DATA, "dvm_port_results.json")

WAD = 10**18
BASE_SLASH = 10**15            # FixedSlashSlashingLibrary.baseSlashAmount (read from chain 2026-10-06)
GOV_SLASH = 0
ROUND = 10085
REQS = {828: 1742680702, 827: 1742684664}   # requestIndex -> request time
RESOLVED_BLOCK = 22120202
P2 = WAD
WHALE = {"0x8e349da0c6ec06e496f145e421424d2fdfe9c97a", "0xc60aa5a87d580b3181aef33a402d88bfe705fea0",
         "0xfc204fcfd2a579157898a212ea25ac98de2b1e1c"}


# ----------------------------------------------------------------------------- the port
def resolve(tally, total_votes, min_participation, min_agreement):
    """tally: dict price -> stake (wei). Mirrors ResultComputationV2.getResolvedPrice."""
    if not tally:
        return False, None
    mode, mode_votes = max(tally.items(), key=lambda kv: kv[1])
    if total_votes > min_participation and mode_votes > min_agreement:
        return True, mode
    return False, None


def slashing_trackers(S, total_votes, total_correct, is_governance=False):
    wrong = GOV_SLASH if is_governance else BASE_SLASH
    no = BASE_SLASH
    total_slashed = (no * (S - total_votes) + wrong * (total_votes - total_correct)) // WAD
    return wrong, no, total_slashed


def ceil_div(a, b):
    return -((-a) // b)


def voter_slash(stake, participation, trackers):
    """VotingV2._updateAccountSlashingTrackers: penalties use Math.ceilDiv, the correct voter's share uses floor division."""
    wrong, no, total_slashed, total_correct = trackers
    if participation == "correct":
        return (stake * total_slashed) // total_correct
    if participation == "wrong":
        return -ceil_div(stake * wrong, WAD)
    return -ceil_div(stake * no, WAD)


# ----------------------------------------------------------------------------- data
def load_votes():
    d = json.load(open(TALLY))
    by_req = {}
    for idx, t in REQS.items():
        votes = {}
        for x in d:
            if x["event"] == "VoteRevealed" and x["time"] == t and x["roundId"] == ROUND:
                votes[x["voter"]] = (int(x["price"]), int(x["numTokens"]))
        by_req[idx] = votes
    return by_req


def fetch_slashes(rpc):
    os.makedirs(os.path.dirname(SLASH_RAW), exist_ok=True)
    topic0 = event_topic(EVENTS["VoterSlashed"][0])
    latest = rpc.block_number()
    n = 0
    with open(SLASH_RAW, "w", encoding="utf-8") as f:
        for idx in REQS:
            topics = [topic0, None, "0x" + format(idx, "064x")]
            logs = rpc.get_logs_range(VOTING_V2, topics, RESOLVED_BLOCK, latest)
            for lg in logs:
                f.write(json.dumps(lg) + "\n")
            n += len(logs)
            print(f"request {idx}: {len(logs)} VoterSlashed logs", flush=True)
    return n


def load_slashes():
    out = defaultdict(dict)
    if not os.path.exists(SLASH_RAW):
        return out
    for line in open(SLASH_RAW, encoding="utf-8"):
        name, f = decode_log(json.loads(line))
        if name == "VoterSlashed":
            out[f["requestIndex"]][f["voter"]] = (f["slashedTokens"], f["blockNumber"])
    return out


# ----------------------------------------------------------------------------- main
def main():
    rpc = Rpc()
    if "--fetch" in sys.argv:
        fetch_slashes(rpc)
    rd = read_round(rpc, ROUND)
    S = rd["cumulativeStakeAtRound"]
    min_part, min_agree = rd["minParticipationRequirement"], rd["minAgreementRequirement"]
    votes_by_req = load_votes()
    slashes = load_slashes()
    results = {"round": ROUND, "S_wei": S, "minParticipation_wei": min_part, "minAgreement_wei": min_agree}

    for idx, votes in votes_by_req.items():
        tally = defaultdict(int)
        for v, (p, s) in votes.items():
            tally[p] += s
        total_votes = sum(tally.values())
        ok, mode = resolve(dict(tally), total_votes, min_part, min_agree)
        total_correct = tally[mode] if ok else 0
        wrong, no, total_slashed = slashing_trackers(S, total_votes, total_correct)
        trackers = (wrong, no, total_slashed, total_correct)
        # validation against chain events
        ev = slashes.get(idx, {})
        matched = mism = 0
        mismatches = []
        absent_checked = 0
        for voter, (slashed, blk) in ev.items():
            if voter in votes:
                p, s = votes[voter]
                pred = voter_slash(s, "correct" if p == mode else "wrong", trackers)
                if pred == slashed:
                    matched += 1
                else:
                    mism += 1
                    if len(mismatches) < 10:
                        mismatches.append({"voter": voter, "pred": pred, "chain": slashed, "price": p, "stake": s})
            else:
                # absent staker: the event implies stake = -slashed * 1e18 / noVoteSlash; check it is a clean multiple
                absent_checked += 1
        # counterfactuals
        whale_votes = {v: s for v, (p, s) in votes.items() if v in WHALE}
        whale_total = sum(whale_votes.values())
        yes_without_whale = tally[P2] - whale_total
        cf = {}
        cf["resolved_on_chain_port"] = ok and mode == P2
        cf["yes_votes"] = tally[P2]
        cf["yes_minus_whale"] = yes_without_whale
        cf["margin_over_minAgreement"] = tally[P2] - min_agree
        cf["min_whale_stake_to_resolve_yes_50pct"] = max(0, min_agree + 1 - yes_without_whale)
        cf["whale_stake_actual"] = whale_total
        t65 = (65 * S) // 100
        cf["min_whale_stake_to_resolve_yes_65pct"] = max(0, t65 + 1 - yes_without_whale)
        cf["whale_short_under_65pct"] = max(0, t65 + 1 - tally[P2])
        # votes-cast denominator at the same thresholds (abstention neutral): need yes > theta * totalVotes
        cf["min_whale_stake_votescast_50pct"] = max(0, (total_votes // 2) + 1 - yes_without_whale)
        cf["min_whale_stake_votescast_65pct"] = max(0, (65 * total_votes) // 100 + 1 - yes_without_whale)
        # stall coalitions under each rule (share of S)
        cf["stall_coalition_staked_50pct"] = S - min_agree      # abstain so that no answer can exceed minAgreement
        cf["stall_coalition_staked_65pct"] = S - t65
        cf["stall_coalition_votescast_65pct"] = 2 * (S - t65)   # T7(b): two vetoes of 1 - theta each
        # F_mu with mu = 0.2: winner share 50.2% < 80% -> tape
        cf["winner_share_of_staked"] = tally[P2] / S
        cf["F_mu_0.2_pays_at_tape"] = tally[P2] < (80 * S) // 100
        # slashing accounting (port)
        cf["totalSlashed_wei"] = total_slashed
        cf["pool_from_wrong_voters_wei"] = (wrong * (total_votes - total_correct)) // WAD
        cf["pool_from_absent_wei"] = (no * (S - total_votes)) // WAD
        cf["whale_gain_wei"] = sum(voter_slash(s, "correct", trackers) for s in whale_votes.values())
        results[str(idx)] = {
            "request_time": REQS[idx], "n_voters": len(votes), "total_votes_wei": total_votes,
            "tally_wei": {str(k): v for k, v in tally.items()}, "port_resolved": ok, "port_mode": mode,
            "validation": {"events_found": len(ev), "voters_matched": matched, "voters_mismatched": mism,
                           "absent_stakers_with_events": absent_checked, "mismatch_samples": mismatches},
            "counterfactuals": cf,
        }
        print(f"request {idx}: voters {len(votes)}, total {total_votes/WAD:,.0f}, resolved={ok} mode={mode}; "
              f"events {len(ev)}, matched {matched}, mismatched {mism}, absent-with-events {absent_checked}")
        print(f"   margin over 50% line {cf['margin_over_minAgreement']/WAD:,.1f} UMA; whale {whale_total/WAD:,.0f}; "
              f"min whale for YES@50% {cf['min_whale_stake_to_resolve_yes_50pct']/WAD:,.0f}; @65% {cf['min_whale_stake_to_resolve_yes_65pct']/WAD:,.0f} "
              f"(short by {cf['whale_short_under_65pct']/WAD:,.0f}); votes-cast@50% {cf['min_whale_stake_votescast_50pct']/WAD:,.0f}, @65% {cf['min_whale_stake_votescast_65pct']/WAD:,.0f}")
        print(f"   stall: staked@50% {cf['stall_coalition_staked_50pct']/WAD:,.0f}, staked@65% {cf['stall_coalition_staked_65pct']/WAD:,.0f}, "
              f"votes-cast@65% {cf['stall_coalition_votescast_65pct']/WAD:,.0f}; totalSlashed {total_slashed/WAD:,.3f} (wrong {cf['pool_from_wrong_voters_wei']/WAD:,.3f} + absent {cf['pool_from_absent_wei']/WAD:,.3f}); whale gain {cf['whale_gain_wei']/WAD:,.3f}")
    json.dump(results, open(OUT, "w"), indent=1, default=str)
    print("wrote", OUT)

    if "--record" in sys.argv:
        raise SystemExit("Ledger recording is available only in the authors workspace; omit --record to reproduce the calculation.")


if __name__ == "__main__":
    main()
