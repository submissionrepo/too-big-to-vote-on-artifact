"""Pull VotingV2 / Staker events from public RPCs into data/raw/votingv2_logs.jsonl.

Usage: python fetch_votingv2_logs.py [from_block] [to_block|latest]
Resumable: progress is kept in data/raw/fetch_state.json; re-running continues from the last finished block.
Only the events listed in abi_min.EVENTS are requested (topic0 OR-filter). Commit / encrypted-vote /
reward-accounting events are skipped to keep the dump small. Chunks are capped at rpc.MAX_LOG_RANGE because
the free endpoints that serve historical logs (drpc, mevblocker) refuse ranges above 10,000 blocks.
"""
import json
import os
import sys
import time

from abi_min import EVENTS, event_topic
from rpc import MAX_LOG_RANGE, RangeError, Rpc, VOTING_V2

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data", "raw")

# VoterSlashed is emitted once per (voter, request) pair whenever trackers are updated, i.e. millions of logs;
# it is skipped here and fetched per request later when the slashing port is validated.
SKIP = {"VoterSlashed"}
TOPICS0 = [event_topic(sig) for name, (sig, _, _, _) in EVENTS.items() if name not in SKIP]


def main():
    os.makedirs(RAW, exist_ok=True)
    rpc = Rpc()
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 16_000_000
    end_arg = sys.argv[2] if len(sys.argv) > 2 else "latest"
    tag = sys.argv[3] if len(sys.argv) > 3 else "all"
    OUT = os.path.join(RAW, f"votingv2_logs_{tag}.jsonl")
    STATE = os.path.join(RAW, f"fetch_state_{tag}.json")
    end = rpc.block_number() if end_arg == "latest" else int(end_arg)

    if os.path.exists(STATE):
        st = json.load(open(STATE))
        if st.get("next_block", 0) > start:
            start = st["next_block"]
            print(f"resuming from {start}")

    total = 0
    t0 = time.time()
    chunk = MAX_LOG_RANGE
    with open(OUT, "a", encoding="utf-8") as f:
        b = start
        while b <= end:
            e = min(b + chunk - 1, end)
            try:
                logs = rpc.get_logs(VOTING_V2, [TOPICS0], b, e)
            except RangeError as ex:
                if chunk > 500:
                    chunk //= 2
                    print(f"  shrinking chunk to {chunk} after: {str(ex)[:120]}", flush=True)
                    continue
                raise
            for lg in logs:
                f.write(json.dumps(lg) + "\n")
            total += len(logs)
            f.flush()
            json.dump({"next_block": e + 1, "end": end, "chunk": chunk}, open(STATE, "w"))
            if len(logs) < 3000 and chunk < MAX_LOG_RANGE:
                chunk = min(chunk * 2, MAX_LOG_RANGE)
            if (b // chunk) % 20 == 0 or len(logs) > 0:
                print(f"{b}-{e}: {len(logs)} logs (total {total}, chunk {chunk}, {time.time()-t0:.0f}s, "
                      f"calls {rpc.calls})", flush=True)
            b = e + 1
    print("done", total, "logs in", f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
