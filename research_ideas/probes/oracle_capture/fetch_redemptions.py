"""Open interest of the rare-earth market from Polygon redemption logs.

ConditionalTokens (0x4D97...6045) emits PayoutRedemption(redeemer indexed, collateralToken indexed, parentCollectionId indexed,
conditionId, indexSets, payout) when a holder redeems. conditionId is not indexed, so all PayoutRedemption logs in the window
after resolution are pulled (Tenderly / QuickNode public gateways serve 9,000-block ranges) and filtered in Python.
Total payout for the condition = YES shares redeemed (NO pays 0) = collateral paid out = a lower bound on the open interest
at resolution; the unredeemed remainder is read from the data-api holders endpoint.

Usage: python fetch_redemptions.py [from_block] [to_block]
"""
import json
import os
import sys
import time

import requests

from abi_min import decode_data, event_topic

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data", "raw", "polygon_redemptions.jsonl")
OUT = os.path.join(HERE, "data", "redemptions_summary.json")
CTF = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
COND = "0x1663edea3eba0d1ae8f064276dd426cb0497a19bb5188dae48a2f8fa8ea34da8"
USDC_E = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"
TOPIC = event_topic("PayoutRedemption(address,address,bytes32,bytes32,uint256[],uint256)")
EPS = ["https://polygon.gateway.tenderly.co", "https://rpc-mainnet.matic.quiknode.pro"]
STEP = 9_000


def get_logs(fb, tb):
    last = None
    for attempt in range(6):
        ep = EPS[attempt % len(EPS)]
        try:
            r = requests.post(ep, json={"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [{
                "address": CTF, "topics": [TOPIC], "fromBlock": hex(fb), "toBlock": hex(tb)}]}, timeout=120)
            j = r.json()
            if "error" in j:
                last = j["error"]
                time.sleep(1)
                continue
            return j["result"]
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1)
    raise RuntimeError(f"getLogs failed {fb}-{tb}: {last}")


def main():
    fb = int(sys.argv[1]) if len(sys.argv) > 1 else 69_461_000   # ~2025-03-25 00:00 UTC
    tb = int(sys.argv[2]) if len(sys.argv) > 2 else 69_745_000   # ~2025-04-01 00:00 UTC
    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    total_logs = 0
    hits = []
    t0 = time.time()
    with open(RAW, "w", encoding="utf-8") as f:
        b = fb
        while b <= tb:
            e = min(b + STEP - 1, tb)
            logs = get_logs(b, e)
            total_logs += len(logs)
            for lg in logs:
                cond, idx_sets, payout = decode_data(["bytes32", "uint256", "uint256"], lg["data"])[:3] if False else (None, None, None)
                # data layout: conditionId (32) | offset of indexSets (32) | payout (32) | indexSets array ...
                data = bytes.fromhex(lg["data"][2:])
                cond = "0x" + data[0:32].hex()
                payout = int.from_bytes(data[64:96], "big")
                if cond.lower() == COND.lower():
                    hits.append({"block": int(lg["blockNumber"], 16), "tx": lg["transactionHash"],
                                 "redeemer": "0x" + lg["topics"][1][-40:], "payout": payout})
                    f.write(json.dumps(lg) + "\n")
            print(f"{b}-{e}: {len(logs)} logs, hits so far {len(hits)}, {time.time()-t0:.0f}s", flush=True)
            b = e + 1
    total = sum(h["payout"] for h in hits)
    redeemers = {h["redeemer"] for h in hits}
    by_red = {}
    for h in hits:
        by_red[h["redeemer"]] = by_red.get(h["redeemer"], 0) + h["payout"]
    top = sorted(by_red.items(), key=lambda kv: -kv[1])[:15]
    # unredeemed remainder today
    rem = None
    try:
        r = requests.get("https://data-api.polymarket.com/holders", params={"market": COND, "limit": 500}, timeout=60).json()
        rem = sum(h["amount"] for t in r for h in t.get("holders", []) if t["token"].startswith("6072"))
    except Exception as e:  # noqa: BLE001
        rem = f"ERR {str(e)[:60]}"
    summary = {"from_block": fb, "to_block": tb, "payout_redemption_logs_scanned": total_logs, "hits": len(hits),
               "redeemers": len(redeemers), "total_payout_usdc": total / 1e6, "top_redeemers_usdc": [(a, v / 1e6) for a, v in top],
               "unredeemed_yes_shares_now": rem, "first_hit_block": min(h["block"] for h in hits) if hits else None,
               "last_hit_block": max(h["block"] for h in hits) if hits else None}
    json.dump(summary, open(OUT, "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
