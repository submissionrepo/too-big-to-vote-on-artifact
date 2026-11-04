"""Fixture for the mainnet-fork replay of the March 2025 vote (prototype/test/MarchReplay.fork.t.sol).

Collects every VoteRevealed event of round 10085 for the minerals-deal request that decided the payout (time
1742684664; the first request, time 1742680702, settled only the first dispute's bonds) from the raw logs,
picks the fork block just before the first reveal by one of the three wallets, and fetches every reveal transaction
from that block on (from, to, input, value, block, timestamp) so that the test can replay them, with or without the
three wallets' reveals, against the real VotingV2 state. Writes prototype/fixtures/march_reveals.json.
"""
import glob
import json
import os
import time

import requests

from abi_min import decode_log, event_topic

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "prototype", "fixtures", "march_reveals.json")
EP = "https://mainnet.gateway.tenderly.co"
WHALE = {"0x8e349da0c6ec06e496f145e421424d2fdfe9c97a": "A", "0xc60aa5a87d580b3181aef33a402d88bfe705fea0": "B",
         "0xfc204fcfd2a579157898a212ea25ac98de2b1e1c": "C"}
# the payout-deciding request (index 827, the second dispute); the first (1742680702) settled only the first dispute's bonds
TIME, ROUND_ID = 1742684664, 10085


def rpc(method, params):
    for attempt in range(6):
        try:
            j = requests.post(EP, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=60).json()
            if "result" in j:
                return j["result"]
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1 + attempt)
    raise RuntimeError(method)


def main():
    t_vr = event_topic("VoteRevealed(address,address,uint32,bytes32,uint256,bytes,int256,uint128)")
    pad = format(TIME, "064x")
    reveals, seen, anc = [], set(), None
    for path in sorted(glob.glob(os.path.join(DATA, "raw", "votingv2_logs*.jsonl"))):
        for line in open(path, encoding="utf-8"):
            if t_vr not in line:
                continue
            lg = json.loads(line)
            if lg["topics"][0] != t_vr or lg["data"][2 + 64:2 + 128] != pad:
                continue
            uid = (lg["transactionHash"], lg["logIndex"])
            if uid in seen:
                continue
            seen.add(uid)
            _, f = decode_log(lg)
            if int(f["roundId"]) != ROUND_ID:
                continue
            anc = f["ancillaryData"]
            reveals.append({"tx": lg["transactionHash"], "block": int(lg["blockNumber"], 16),
                            "logIndex": int(lg["logIndex"], 16), "ts": int(lg.get("blockTimestamp", "0x0"), 16),
                            "voter": f["voter"].lower(), "price": str(f["price"]), "tokens": str(f["numTokens"]),
                            "identifier": f["identifier"]})
    reveals.sort(key=lambda r: (r["block"], r["logIndex"]))
    first_whale = min(r["block"] for r in reveals if r["voter"] in WHALE)
    fork_block = first_whale - 1
    later = [r for r in reveals if r["block"] >= first_whale]
    txs, order = {}, []
    for r in later:
        if r["tx"] not in txs:
            t = rpc("eth_getTransactionByHash", [r["tx"]])
            txs[r["tx"]] = {"hash": r["tx"], "from": t["from"], "to": t["to"], "input": t["input"], "value": t["value"],
                            "block": r["block"], "ts": r["ts"], "voters": [], "tokens": []}
            order.append(r["tx"])
        txs[r["tx"]]["voters"].append(r["voter"])
        txs[r["tx"]]["tokens"].append(r["tokens"])
    out = {"forkBlock": fork_block, "roundId": ROUND_ID, "identifier": later[0]["identifier"], "time": TIME,
           "ancillaryData": anc, "roundEnd": (ROUND_ID + 1) * 172800,
           "txs": [{**txs[h], "whale": "".join(sorted({WHALE[v] for v in txs[h]["voters"] if v in WHALE}))} for h in order]}
    # parallel arrays, the form Foundry's JSON cheatcodes decode most simply
    out["froms"] = [t["from"] for t in out["txs"]]
    out["tos"] = [t["to"] for t in out["txs"]]
    out["inputs"] = [t["input"] for t in out["txs"]]
    out["blocks"] = [t["block"] for t in out["txs"]]
    out["timestamps"] = [t["ts"] for t in out["txs"]]
    out["whales"] = [t["whale"] or "-" for t in out["txs"]]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1)
    print("reveals in round:", len(reveals), "| fork block", fork_block, "| later reveal txs", len(order))
    for t in out["txs"]:
        print(" ", t["block"], t["ts"], t["from"][:12], "to", t["to"][:12], "voters", len(t["voters"]), "whale", t["whale"] or "-",
              "tokens", sum(int(x) for x in t["tokens"]) / 1e18)


if __name__ == "__main__":
    main()
