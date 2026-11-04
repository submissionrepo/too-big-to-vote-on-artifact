"""Read current VotingV2 / Staker state via eth_call, and map timestamps to block numbers."""
import datetime as dt
import json
import os
import sys

from abi_min import decode_data, encode_call
from rpc import Rpc, VOTING_V2

HERE = os.path.dirname(os.path.abspath(__file__))


def read_getters(rpc, block="latest"):
    out = {}
    simple = {
        "gat()": "uint128", "spat()": "uint64", "maxRolls()": "uint32", "maxRequestsPerRound()": "uint32",
        "cumulativeStake()": "uint128", "emissionRate()": "uint128", "unstakeCoolDown()": "uint64",
        "getCurrentRoundId()": "uint32", "voteTiming()": "uint256",
    }
    for sig, typ in simple.items():
        try:
            res = rpc.eth_call(VOTING_V2, encode_call(sig), block)
            out[sig] = decode_data([typ], res)[0]
        except Exception as e:  # voteTiming is a struct getter; tolerate failures
            out[sig] = f"ERR {str(e)[:80]}"
    return out


def read_round(rpc, round_id, block="latest"):
    res = rpc.eth_call(VOTING_V2, encode_call("rounds(uint256)", [round_id]), block)
    vals = decode_data(["address", "uint128", "uint128", "uint128", "uint32"], res)
    return dict(zip(["slashingLibrary", "minParticipationRequirement", "minAgreementRequirement",
                     "cumulativeStakeAtRound", "numberOfRequestsToVote"], vals))


def read_voter(rpc, voter, block="latest"):
    res = rpc.eth_call(VOTING_V2, encode_call("voterStakes(address)", [voter]), block)
    vals = decode_data(["uint128", "uint128", "uint128", "uint128", "int128", "uint64", "uint64", "address"], res)
    return dict(zip(["stake", "pendingUnstake", "rewardsPaidPerToken", "outstandingRewards", "unappliedSlash",
                     "nextIndexToProcess", "unstakeTime", "delegate"], vals))


def block_at(rpc, ts, lo=15_000_000, hi=None):
    """First block with timestamp >= ts (binary search)."""
    if hi is None:
        hi = rpc.block_number()
    while lo < hi:
        mid = (lo + hi) // 2
        b = rpc.get_block(mid)
        if int(b["timestamp"], 16) < ts:
            lo = mid + 1
        else:
            hi = mid
    return lo


def ts(s):
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp())


if __name__ == "__main__":
    rpc = Rpc()
    g = read_getters(rpc)
    print(json.dumps(g, indent=1, default=str))
    if len(sys.argv) > 1:
        for d in sys.argv[1:]:
            print(d, "->", block_at(rpc, ts(d)))
