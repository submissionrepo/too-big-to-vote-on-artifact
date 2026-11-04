"""Recover the Polymarket question behind hashed DVM requests.

Since mid-2025 the Polygon bridge compresses ancillary data into
  "ancillaryDataHash:<keccak>,childBlockNumber:<n>,childOracle:<addr>,childRequester:<addr>,childChainId:137".
At Polygon block n the OptimisticOracleV2 (0xeE3A...7c24) emitted DisputePrice(..., ancillaryData, ...) with the full
ancillary data (the OO-stamped question text). One single-block eth_getLogs per request recovers it; the keccak of the
recovered bytes is checked against the hash in the DVM text.

Usage: python map_polygon_disputes.py [contested|all]
Writes data/polygon_dispute_map.csv (requestTime, identifier, hash, childBlock, title, matched).
"""
import csv
import json
import os
import re
import sys
import time

import requests

from abi_min import decode_data, event_topic, keccak256

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(DATA, "polygon_dispute_map.csv")
OOV2 = "0xeE3Afe347D5C74317041E2618C49534dAf887c24"
TOPIC = event_topic("DisputePrice(address,address,address,bytes32,uint256,bytes,int256)")
EPS = ["https://polygon-bor-rpc.publicnode.com", "https://polygon.gateway.tenderly.co", "https://rpc-mainnet.matic.quiknode.pro"]
RX = re.compile(r"ancillaryDataHash:([0-9a-f]{64}),childBlockNumber:(\d+)")


def get_logs(block):
    last = None
    for attempt in range(6):
        ep = EPS[attempt % len(EPS)]
        try:
            r = requests.post(ep, json={"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [{
                "address": OOV2, "topics": [TOPIC], "fromBlock": hex(block), "toBlock": hex(block)}]}, timeout=60)
            j = r.json()
            if "error" in j:
                last = j["error"]
                time.sleep(0.5)
                continue
            return j["result"]
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.5)
    raise RuntimeError(f"getLogs failed at {block}: {last}")


CHILD_ORACLE = "0xac60353a54873c446101216829a6a98cdbbc3f3d"


def get_child_logs(block):
    last = None
    for attempt in range(6):
        ep = EPS[attempt % len(EPS)]
        try:
            r = requests.post(ep, json={"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [{
                "address": CHILD_ORACLE, "fromBlock": hex(block), "toBlock": hex(block)}]}, timeout=60)
            j = r.json()
            if "error" in j:
                last = j["error"]
                time.sleep(0.5)
                continue
            return j["result"]
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.5)
    raise RuntimeError(f"child getLogs failed at {block}: {last}")


def title_of(text):
    m = re.search(r"q:\s*title:\s*(.*?),\s*description:", text, re.S)
    return (m.group(1) if m else text[:120]).strip()


def main():
    scope = sys.argv[1] if len(sys.argv) > 1 else "contested"
    reqs = list(csv.DictReader(open(os.path.join(DATA, "requests_summary.csv"), encoding="utf-8")))
    if scope == "contested":
        cont = list(csv.DictReader(open(os.path.join(DATA, "contested_requests.csv"), encoding="utf-8")))
        keys = {(c["roundId"], c["requestTime"], c["ancKey"]) for c in cont}
        reqs = [r for r in reqs if (r["roundId"], r["requestTime"], r["ancKey"]) in keys]
    done = {}
    if os.path.exists(OUT):
        for row in csv.DictReader(open(OUT, encoding="utf-8")):
            done[(row["requestTime"], row["hash"])] = row
    rows = list(done.values())
    n_new = 0
    for r in reqs:
        m = RX.search(r["text"])
        if not m:
            continue
        h, blk = m.group(1), int(m.group(2))
        if (r["requestTime"], h) in done:
            continue
        # The OracleChildTunnel log at childBlockNumber carries the OO-stamped ancillary data (text + ",ooRequester:<oo>")
        # whose keccak is the hash in the DVM text; disputes may come from OOv2 or from the Managed OO (since 2025-08),
        # so the tunnel log is the one place that always has it. ABI bytes payloads sit behind a 32-byte length word.
        logs = get_child_logs(blk)
        title, matched, anc_hex = "", False, ""
        for lg in logs:
            data = bytes.fromhex(lg["data"][2:])
            pos = 0
            while True:
                i = data.find(b"q: title", pos)
                if i < 0:
                    break
                p = (i // 32) * 32
                if p >= 32:
                    ln = int.from_bytes(data[p - 32:p], "big")
                    cand = data[p:p + ln]
                    if 0 < ln <= len(data) and keccak256(cand).hex() == h:
                        matched = True
                        title = title_of(cand.decode("utf-8", "replace"))
                        anc_hex = "0x" + cand.hex()
                        break
                pos = i + 8
            if matched:
                break
        if not matched:
            for lg in logs:
                data = bytes.fromhex(lg["data"][2:])
                i = data.find(b"q: title")
                if i >= 0:
                    title = title_of(data[i:i + 600].decode("utf-8", "replace"))
                    break
        rows.append({"requestTime": r["requestTime"], "roundId": r["roundId"], "identifier": r["identifier"], "hash": h,
                     "childBlock": blk, "disputes_in_block": len(logs), "matched": matched, "title": title,
                     "resolvedPrice": r["resolvedPrice"], "modeShareOfStaked": r["modeShareOfStaked"],
                     "minorityShareOfVotes": r["minorityShareOfVotes"]})
        n_new += 1
        if n_new % 20 == 0:
            print(f"{n_new} mapped", flush=True)
            with open(OUT, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        time.sleep(0.1)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("wrote", OUT, len(rows), "rows;", sum(1 for x in rows if str(x["matched"]) == "True"), "hash-matched")


if __name__ == "__main__":
    main()
