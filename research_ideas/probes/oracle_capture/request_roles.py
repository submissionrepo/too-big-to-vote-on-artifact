"""Which DVM votes decide what a Polymarket market pays?

Polymarket's adapter resets a question on its first dispute: the priceDisputed callback sends a new price request to
the optimistic oracle, and the market is then paid on that new request, either by an undisputed proposal or, if that
proposal is disputed too, by a second DVM vote. The DVM vote on the first dispute still happens, but it only decides
who keeps the bonds of that dispute. So a DVM request decides the payout iff the dispute that escalated it did not
reset the question; a reset shows on-chain as a RequestPrice log of the same oracle, for the same requester and
question, in the transaction of the dispute.

For every contested Polymarket request of capture_economics.csv: the escalating dispute (as in prize_growth.py), its
transaction, whether that transaction reset the question, and the market's payout-deciding request in the round.
Outputs data/request_roles.csv and data/request_roles_summary.json.
"""
import csv
import json
import os
import re
from collections import defaultdict

import pm_markets as pm
from abi_min import event_topic, keccak256
from prize_growth import CACHE, MOOV2, OOV2, T_DISPUTE, escalation_block

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
T_REQUEST = event_topic("RequestPrice(address,bytes32,uint256,bytes,address,uint256,uint256)")


def dispute_tx(block, requester, prefix=None, anc_hash=None):
    """The DisputePrice log in `block` for this requester and question; returns (tx, oo, reset?)."""
    key = os.path.join(CACHE, f"role_{block}_{requester[:10]}_{(anc_hash or keccak256(prefix).hex())[:12]}.json")
    if os.path.exists(key):
        return tuple(json.load(open(key)))
    topic1 = "0x" + requester.lower().replace("0x", "").rjust(64, "0")
    hit = None
    for oo in (OOV2, MOOV2):
        logs = pm.rpc("eth_getLogs", [{"address": oo, "fromBlock": hex(block), "toBlock": hex(block)}])
        for lg in logs:
            if lg["topics"][0] != T_DISPUTE or lg["topics"][1].lower() != topic1:
                continue
            data = bytes.fromhex(lg["data"][2:])
            ok = (prefix is not None and prefix in data)
            if anc_hash is not None and not ok:
                ln_off = int.from_bytes(data[64:96], "big")
                ln = int.from_bytes(data[ln_off:ln_off + 32], "big")
                anc = data[ln_off + 32:ln_off + 32 + ln]
                # the DVM hash covers the oracle-stamped text: ancillary data + ",ooRequester:<requester>"
                stamped = anc + b",ooRequester:" + requester.lower().replace("0x", "").encode()
                ok = keccak256(stamped).hex() == anc_hash
            if ok:
                tx = lg["transactionHash"]
                reset = any(x["transactionHash"] == tx and x["topics"][0] == T_REQUEST and x["topics"][1].lower() == topic1
                            for x in logs)
                hit = (tx, oo, reset)
                break
        if hit:
            break
    json.dump(hit, open(key, "w"))
    return tuple(hit) if hit else (None, None, None)


def main():
    econ = [r for r in csv.DictReader(open(os.path.join(DATA, "capture_economics.csv"), encoding="utf-8")) if r.get("conditionId")]
    anc_by_key = {(tt, ak): v for (ident, tt, ak), v in pm.load_ancillary().items()}
    dmap = {}
    for r in csv.DictReader(open(os.path.join(DATA, "polygon_dispute_map.csv"), encoding="utf-8")):
        if r["childBlock"]:
            dmap.setdefault(r["requestTime"], []).append(r)
    out = []
    for i, r in enumerate(econ):
        t = int(r["requestTime"])
        anc = anc_by_key.get((t, r["ancKey"]))
        text = anc.decode("utf-8", "replace") if anc else ""
        m_req = re.search(r"(?:ooRequester|childRequester):([0-9a-fA-F]{40})", text)
        row = {"roundId": r["roundId"], "requestTime": t, "ancKey": r["ancKey"], "conditionId": r["conditionId"],
               "title": r["title"], "negRisk": r.get("negRisk")}
        h = re.search(r"ancillaryDataHash:([0-9a-f]{64}),childBlockNumber:(\d+)", text)
        if h:
            # hash era: the DVM text names the oracle (childRequester) and the escalation block; the requester (the
            # adapter) is recovered from the dispute map's matched text
            block = int(h.group(2))
            cands = [x for x in dmap.get(str(t), []) if x["hash"] == h.group(1)]
            mreq = re.search(r"childRequester:([0-9a-fA-F]{40})", text)
            # the adapter is the requester of the oracle request; scan the block's disputes for the matching hash
            tx, oo, reset = None, None, None
            for oo_addr in (OOV2, MOOV2):
                logs = pm.rpc("eth_getLogs", [{"address": oo_addr, "fromBlock": hex(block), "toBlock": hex(block)}])
                for lg in logs:
                    if lg["topics"][0] != T_DISPUTE:
                        continue
                    req = "0x" + lg["topics"][1][-40:]
                    data = bytes.fromhex(lg["data"][2:])
                    ln_off = int.from_bytes(data[64:96], "big")
                    ln = int.from_bytes(data[ln_off:ln_off + 32], "big")
                    a = data[ln_off + 32:ln_off + 32 + ln]
                    if keccak256(a + b",ooRequester:" + req[2:].encode()).hex() == h.group(1):
                        tx = lg["transactionHash"]
                        oo = oo_addr
                        reset = any(x["transactionHash"] == tx and x["topics"][0] == T_REQUEST and x["topics"][1] == lg["topics"][1]
                                    for x in logs)
                        break
                if tx:
                    break
            row.update({"era": "hash", "esc_block": block, "dispute_tx": tx, "oo": oo, "reset": reset})
        elif anc and m_req:
            block = escalation_block(t, anc)
            cut = anc.find(b",ooRequester:")
            prefix = anc[:cut] if cut > 0 else anc
            mo = re.search(r"ooRequester:([0-9a-fA-F]{40})", text)
            tx, oo, reset = dispute_tx(block, "0x" + mo.group(1), prefix=prefix) if (block and mo) else (None, None, None)
            row.update({"era": "text", "esc_block": block, "dispute_tx": tx, "oo": oo, "reset": reset})
        else:
            row.update({"era": "?", "esc_block": None, "dispute_tx": None, "oo": None, "reset": None})
        row["role"] = ("bond-only" if row["reset"] else "payout") if row["reset"] is not None else "unknown"
        out.append(row)
        print(f"{i+1}/{len(econ)} {row['title'][:44]:44s} {row['era']:5s} block {row['esc_block']} reset {row['reset']} -> {row['role']}", flush=True)
    keys = list(out[0].keys())
    with open(os.path.join(DATA, "request_roles.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(out)
    by_mr = defaultdict(list)
    for r in out:
        by_mr[(r["roundId"], r["conditionId"])].append(r)
    summ = {"requests": len(out), "payout": sum(1 for r in out if r["role"] == "payout"),
            "bond_only": sum(1 for r in out if r["role"] == "bond-only"), "unknown": sum(1 for r in out if r["role"] == "unknown"),
            "market_rounds": len(by_mr),
            "market_rounds_with_payout_vote": sum(1 for v in by_mr.values() if any(x["role"] == "payout" for x in v)),
            "market_rounds_bond_only": sum(1 for v in by_mr.values() if v and all(x["role"] == "bond-only" for x in v)),
            "market_rounds_unknown": sum(1 for v in by_mr.values() if any(x["role"] == "unknown" for x in v) and not any(x["role"] == "payout" for x in v))}
    json.dump(summ, open(os.path.join(DATA, "request_roles_summary.json"), "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
