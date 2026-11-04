"""Stake history of the three March 2025 wallets: every Staked / RequestedUnstake / ExecutedUnstake event they emitted
on VotingV2, with exact block timestamps. Question: did they add stake for the vote of round 10085?
Writes data/march_stake_history.json.
"""
import glob
import json
import os
import time

import requests

from abi_min import decode_log

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
WHALE = {"0x8e349da0c6ec06e496f145e421424d2fdfe9c97a", "0xc60aa5a87d580b3181aef33a402d88bfe705fea0",
         "0xfc204fcfd2a579157898a212ea25ac98de2b1e1c"}
EP = "https://ethereum-rpc.publicnode.com"
WAD = 10**18


def block_time(b):
    for attempt in range(6):
        try:
            j = requests.post(EP, json={"jsonrpc": "2.0", "id": 1, "method": "eth_getBlockByNumber", "params": [hex(b), False]}, timeout=60).json()
            return int(j["result"]["timestamp"], 16)
        except Exception:  # noqa: BLE001
            time.sleep(1 + attempt)
    return None


def main():
    evs = []
    for path in sorted(glob.glob(os.path.join(DATA, "raw", "votingv2_logs*.jsonl"))):
        for line in open(path, encoding="utf-8"):
            if '"0x' not in line:
                continue
            lg = json.loads(line)
            topics = lg.get("topics") or []
            if not any(t[-40:] in {w[2:] for w in WHALE} for t in topics[1:]):
                continue
            try:
                name, f = decode_log(lg)
            except Exception:  # noqa: BLE001
                continue
            if name in ("Staked", "RequestedUnstake", "ExecutedUnstake", "DelegateSet", "DelegatorSet",
                        "VariableEmissionsClaimed", "RewardsWithdrawn", "WithdrawnRewards"):
                evs.append({"name": name, "block": int(lg["blockNumber"], 16), "tx": lg["transactionHash"],
                            "logIndex": int(lg["logIndex"], 16), **{k: (str(v) if isinstance(v, int) else v) for k, v in f.items()}})
    seen = set()
    uniq = []
    for e in sorted(evs, key=lambda e: (e["block"], e["logIndex"])):
        k = (e["tx"], e["logIndex"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    for e in uniq:
        e["time"] = block_time(e["block"])
    json.dump(uniq, open(os.path.join(DATA, "march_stake_history.json"), "w"), indent=1)
    import datetime as dt
    for e in uniq:
        who = next((v for k, v in e.items() if isinstance(v, str) and v.lower() in WHALE), "?")
        amt = next((int(e[k]) / WAD for k in ("amount", "unstakeAmount", "tokens") if k in e), None)
        print(dt.datetime.fromtimestamp(e["time"], dt.timezone.utc).strftime("%Y-%m-%d %H:%M"), e["name"], who[:10],
              f"{amt:,.0f}" if amt is not None else {k: v for k, v in e.items() if k not in ("tx", "logIndex", "block", "time", "name")})


if __name__ == "__main__":
    main()
