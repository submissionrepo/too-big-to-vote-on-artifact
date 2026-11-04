"""Fixture for the fork replay of a blocking coalition (prototype/test/BlockToDeletion.fork.t.sol).

The most recent contested vote that decided a Polymarket payout with a Yes-or-No answer: "Will Donald Trump publicly
insult someone on June 21, 2026?" (round 10314, DVM time 1782107618; the two later contested payout votes were won by
"too early", which pays nothing, so blocking them would change nothing). The coalition is the four largest voters on
the request. In round 10314 they re-commit "Yes" (with their historical salts) and reveal it inside their historical
multicalls; everyone else's reveals are replayed as they were. In every later round until the DVM deletes the request,
the test constructs the same votes again: each voter of round 10314 commits and reveals the answer it revealed there
(the coalition "Yes"), from the same sender, with fresh salts. These later rounds are constructed, not replayed.

Also: the Polygon fork block (the block before the historical delivery of this request's price), the market's
questionID, conditionId and outcome positions, and an administrator of the adapter.
Writes prototype/fixtures/block_meta.json and prototype/fixtures/block/{in,dev}_<k>.bin.
"""
import glob
import json
import os

from abi_min import decode_log, event_topic, keccak256
from build_ceasefire_fixture import (EEP, PEP, ROUND_ID as _CF_ROUND, enc_commit, last_block_before, parse_reveal, rpc,
                                     subcalls, REVEAL_SEL)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FIX = os.path.join(HERE, "prototype", "fixtures")
TIME, ROUND_ID = 1782107618, 10314
CHILD_TUNNEL = "0xac60353a54873c446101216829a6a98cdbbc3f3d"
ADMIN = "0x3dce0a29139a851da1dfca56af8e8a6440b4d952"
YES = 10 ** 18


def main():
    t_vr = event_topic("VoteRevealed(address,address,uint32,bytes32,uint256,bytes,int256,uint128)")
    pad_t = format(TIME, "064x")
    rev, seen = [], set()
    for path in sorted(glob.glob(os.path.join(DATA, "raw", "votingv2_logs*.jsonl"))):
        for line in open(path, encoding="utf-8"):
            if pad_t not in line or t_vr not in line:
                continue
            lg = json.loads(line)
            if lg["topics"][0] != t_vr:
                continue
            _, f = decode_log(lg)
            if int(f["roundId"]) != ROUND_ID:
                continue
            uid = (lg["transactionHash"], lg["logIndex"])
            if uid in seen:
                continue
            seen.add(uid)
            rev.append({"tx": lg["transactionHash"], "block": int(lg["blockNumber"], 16), "logIndex": int(lg["logIndex"], 16),
                        "voter": f["voter"].lower(), "caller": f["caller"].lower(), "price": int(f["price"]),
                        "tokens": int(f["numTokens"]), "identifier": f["identifier"], "anc": f["ancillaryData"]})
    ancs = {r["anc"] for r in rev}
    assert len(ancs) == 1, f"{len(ancs)} requests share this time"
    rev.sort(key=lambda r: (r["block"], r["logIndex"]))
    anc = bytes.fromhex(rev[0]["anc"][2:])
    ident = bytes.fromhex(rev[0]["identifier"][2:])
    top = sorted(rev, key=lambda r: -r["tokens"])[:4]
    coalition = {r["voter"] for r in top}
    print("reveals", len(rev), "| four largest:", [(r["voter"][:10], r["tokens"] / 1e18, r["price"]) for r in top])
    txs, commits = [], []
    os.makedirs(os.path.join(FIX, "block"), exist_ok=True)
    for k, r in enumerate(rev):
        t = rpc(EEP, "eth_getTransactionByHash", [r["tx"]])
        blk = rpc(EEP, "eth_getBlockByNumber", [hex(r["block"]), False])
        inp = t["input"]
        dev = inp
        if r["voter"] in coalition:
            raw = bytearray(bytes.fromhex(inp[2:]))
            hits = 0
            for off, call in subcalls(inp):
                if call[:4] != REVEAL_SEL:
                    continue
                i_, t_, p_, a_, s_ = parse_reveal(call)
                if i_ == ident and t_ == TIME and a_ == anc:
                    raw[off + 4 + 64: off + 4 + 96] = YES.to_bytes(32, "big")
                    h = keccak256(YES.to_bytes(32, "big", signed=True) + s_.to_bytes(32, "big", signed=True)
                                  + bytes.fromhex(r["voter"][2:]) + TIME.to_bytes(32, "big") + anc
                                  + ROUND_ID.to_bytes(32, "big") + ident)
                    commits.append({"sender": t["from"].lower(), "voter": r["voter"], "input": enc_commit(ident, TIME, anc, h)})
                    hits += 1
            assert hits == 1, (r["tx"], hits)
            dev = "0x" + bytes(raw).hex()
        open(os.path.join(FIX, "block", f"in_{k}.bin"), "wb").write(bytes.fromhex(inp[2:]))
        open(os.path.join(FIX, "block", f"dev_{k}.bin"), "wb").write(bytes.fromhex(dev[2:]))
        txs.append({"from": t["from"].lower(), "to": t["to"].lower(), "block": r["block"], "ts": int(blk["timestamp"], 16)})
    reveal_start = (ROUND_ID * 2 + 1) * 86_400
    eth_fork = last_block_before(EEP, reveal_start, txs[0]["block"] - 20_000, txs[0]["block"])
    # Polygon: the child tunnel log that delivered this request's price after the round
    round_end = (ROUND_ID + 1) * 172_800
    pb0 = int(rpc(PEP, "eth_blockNumber", []), 16)
    ts_p = lambda b: int(rpc(PEP, "eth_getBlockByNumber", [hex(b), False])["timestamp"], 16)  # noqa: E731
    lo, hi = 85_700_000, pb0
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ts_p(mid) < round_end:
            lo = mid
        else:
            hi = mid
    h_anc = anc.decode().split("ancillaryDataHash:")[1][:64]
    delivered = None
    for b0 in range(hi, hi + 20_000, 2000):
        for lg in rpc(PEP, "eth_getLogs", [{"address": CHILD_TUNNEL, "fromBlock": hex(b0), "toBlock": hex(b0 + 1999)}]):
            if h_anc in lg["data"] or h_anc.encode().hex() in lg["data"]:
                delivered = int(lg["blockNumber"], 16)
                break
        if delivered:
            break
    assert delivered, "price delivery not found"
    econ = [r for r in json.load(open(os.path.join(DATA, "capture_economics_summary.json")))["top"]]  # noqa: F841
    cond = next(r["conditionId"] for r in __import__("csv").DictReader(open(os.path.join(DATA, "capture_economics.csv"), encoding="utf-8"))
                if r["roundId"] == str(ROUND_ID) and r["requestTime"] == str(TIME))
    gm = json.load(open(glob.glob(os.path.join(DATA, "raw", "pm_cache", f"gamma_{cond[:24]}.json"))[0], encoding="utf-8"))[0]
    toks = json.loads(gm["clobTokenIds"])
    # every voter of round 10314 on this request, with the answer to vote again in later rounds (coalition: Yes)
    voters = {}
    for r in rev:
        voters[r["voter"]] = {"caller": r["caller"], "price": str(YES if r["voter"] in coalition else r["price"])}
    meta = {"ethForkBlock": eth_fork, "polygonForkBlock": delivered - 1, "roundId": ROUND_ID, "time": TIME,
            "identifier": "0x" + ident.hex(), "ancillaryData": "0x" + anc.hex(), "roundEnd": round_end, "maxRolls": 4,
            "n": len(txs), "froms": [t["from"] for t in txs], "tos": [t["to"] for t in txs],
            "blocks": [t["block"] for t in txs], "timestamps": [t["ts"] for t in txs],
            "commitSenders": [c["sender"] for c in commits], "commitInputs": [c["input"] for c in commits],
            "coalitionVoters": [c["voter"] for c in commits],
            "allVoters": list(voters), "allCallers": [v["caller"] for v in voters.values()],
            "allPrices": [v["price"] for v in voters.values()],
            "questionID": gm["questionID"], "conditionId": cond, "yesPosition": toks[0], "noPosition": toks[1],
            "admin": ADMIN, "title": gm.get("question")}
    json.dump(meta, open(os.path.join(FIX, "block_meta.json"), "w"), indent=1)
    print("eth fork", eth_fork, "| polygon fork", delivered - 1, "| voters", len(voters), "| coalition commits", len(commits))


if __name__ == "__main__":
    main()
