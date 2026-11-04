"""Fixture for the two-chain fork replay of the ceasefire capture (prototype/test/CeasefireCapture.fork.t.sol).

Round 10281 settled "Israel x Hezbollah ceasefire by April 18, 2026?" (DVM time 1776364190, payout-deciding request).
We take every reveal transaction of that round that revealed this request (each is a VotingV2 multicall over the
round's requests, or a single revealVote), with sender, calldata, block and timestamp. The coalition is the
`--k` largest voters on this request. For each coalition member we prepare
  * a commitVote call for "No" on this request with the member's own historical salt, to be sent from the member's
    historical sender (voter or delegate) before the commit phase ends;
  * its historical reveal calldata with this request's price word changed from Yes to No (every other request in the
    multicall is revealed as it was).
Ethereum fork block: the last block before the reveal phase. Polygon fork block: the last block before the
historical delivery of the DVM price to the child tunnel. Also lists the market's largest "No" holders at that block,
whose redemptions show the money moving.

Writes prototype/fixtures/ceasefire_capture.json.
"""
import argparse
import glob
import json
import os
import time

import requests

from abi_min import decode_log, event_topic, keccak256

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "prototype", "fixtures", "ceasefire_capture.json")
EEP = ["https://mainnet.gateway.tenderly.co", "https://eth.drpc.org", "https://rpc.mevblocker.io"]
PEP = ["https://polygon.gateway.tenderly.co", "https://polygon.drpc.org"]
VOTING = "0x004395edb43efca9885cedad51ec9faf93bd34ac"
TIME, ROUND_ID = 1776364190, 10281
ANC_HASH = "26be2a26b9ff40c9e9fa1a24d8ce031b08573b01e43fa9ae49018a96cb822012"
COND = "0x9823d715687a0a82d2a03731792e83bf58a0409f10def1379e00e4d67a95ba69"
CHILD_TUNNEL = "0xac60353a54873c446101216829a6a98cdbbc3f3d"
REVEAL_SEL = keccak256(b"revealVote(bytes32,uint256,int256,bytes,int256)")[:4]
MULTI_SEL = keccak256(b"multicall(bytes[])")[:4]
COMMIT_SEL = keccak256(b"commitVote(bytes32,uint256,bytes,bytes32)")[:4]


FCACHE = os.path.join(DATA, "raw", "fixture_cache")
os.makedirs(FCACHE, exist_ok=True)


def rpc(eps, method, params):
    cacheable = method in ("eth_getTransactionByHash", "eth_getBlockByNumber")
    key = os.path.join(FCACHE, f"{'e' if eps is EEP else 'p'}_{method}_{str(params[0])[:66]}.json") if cacheable else None
    if key and os.path.exists(key):
        return json.load(open(key))
    res = _rpc(eps, method, params)
    if key:
        json.dump(res, open(key, "w"))
    return res


def _rpc(eps, method, params):
    last = None
    for attempt in range(8):
        try:
            j = requests.post(eps[attempt % len(eps)], json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                              timeout=90).json()
            if "result" in j and j["result"] is not None:
                return j["result"]
            last = j.get("error")
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(1 + attempt)
    raise RuntimeError(f"{method}: {last}")


def last_block_before(eps, t, lo, hi):
    """Last block with timestamp < t, by bisection between known blocks lo (before) and hi (at or after)."""
    ts = lambda b: int(rpc(eps, "eth_getBlockByNumber", [hex(b), False])["timestamp"], 16)  # noqa: E731
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ts(mid) < t:
            lo = mid
        else:
            hi = mid
    return lo


def subcalls(inp):
    """(offset, bytes) of each revealVote call inside a multicall or a single revealVote calldata."""
    b = bytes.fromhex(inp[2:])
    if b[:4] == REVEAL_SEL:
        return [(0, b)]
    assert b[:4] == MULTI_SEL, inp[:10]
    body = b[4:]
    arr = int.from_bytes(body[0:32], "big")
    n = int.from_bytes(body[arr:arr + 32], "big")
    out = []
    for i in range(n):
        off = int.from_bytes(body[arr + 32 + 32 * i: arr + 64 + 32 * i], "big")
        start = arr + 32 + off
        ln = int.from_bytes(body[start:start + 32], "big")
        out.append((4 + start + 32, body[start + 32:start + 32 + ln]))
    return out


def parse_reveal(call):
    assert call[:4] == REVEAL_SEL
    a = call[4:]
    ident, t, price = a[0:32], int.from_bytes(a[32:64], "big"), int.from_bytes(a[64:96], "big", signed=True)
    off = int.from_bytes(a[96:128], "big")
    salt = int.from_bytes(a[128:160], "big", signed=True)
    ln = int.from_bytes(a[off:off + 32], "big")
    return ident, t, price, a[off + 32:off + 32 + ln], salt


def enc_commit(ident, t, anc, h):
    pad = lambda x: x + b"\x00" * ((32 - len(x) % 32) % 32)  # noqa: E731
    head = ident + t.to_bytes(32, "big") + (128).to_bytes(32, "big") + h
    return "0x" + (COMMIT_SEL + head + len(anc).to_bytes(32, "big") + pad(anc)).hex()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=19)
    ap.add_argument("--holders", type=int, default=12)
    args = ap.parse_args()
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
            if int(f["roundId"]) != ROUND_ID or ANC_HASH.encode().hex() not in f["ancillaryData"]:
                continue
            uid = (lg["transactionHash"], lg["logIndex"])
            if uid in seen:
                continue
            seen.add(uid)
            rev.append({"tx": lg["transactionHash"], "block": int(lg["blockNumber"], 16), "logIndex": int(lg["logIndex"], 16),
                        "voter": f["voter"].lower(), "caller": f["caller"].lower(), "price": int(f["price"]),
                        "tokens": int(f["numTokens"]), "identifier": f["identifier"], "anc": f["ancillaryData"]})
    rev.sort(key=lambda r: (r["block"], r["logIndex"]))
    anc = bytes.fromhex(rev[0]["anc"][2:])
    ident = bytes.fromhex(rev[0]["identifier"][2:])
    by_tokens = sorted(rev, key=lambda r: -r["tokens"])
    coalition = {r["voter"] for r in by_tokens[:args.k]}
    print(f"reveals {len(rev)}; coalition of {args.k} holds {sum(r['tokens'] for r in by_tokens[:args.k]) / 1e18:,.0f} UMA; "
          f"all revealed {sum(r['tokens'] for r in rev) / 1e18:,.0f}; by price "
          f"{ {p: round(sum(r['tokens'] for r in rev if r['price'] == p) / 1e18) for p in {r['price'] for r in rev}} }")
    txs, commits = [], []
    for r in rev:
        t = rpc(EEP, "eth_getTransactionByHash", [r["tx"]])
        blk = rpc(EEP, "eth_getBlockByNumber", [hex(r["block"]), False])
        inp = t["input"]
        dev = inp
        if r["voter"] in coalition:
            raw = bytearray(bytes.fromhex(inp[2:]))
            hits = 0
            for off, call in subcalls(inp):
                if call[:4] != REVEAL_SEL:
                    continue  # multicalls also carry other calls (e.g. reward claims)
                i_, t_, p_, a_, s_ = parse_reveal(call)
                if i_ == ident and t_ == TIME and a_ == anc:
                    assert p_ == r["price"]
                    # overwrite the price word (bytes 4+64 .. 4+96 of the subcall) with 0, i.e. "No"
                    raw[off + 4 + 64: off + 4 + 96] = (0).to_bytes(32, "big")
                    h = keccak256((0).to_bytes(32, "big", signed=True) + s_.to_bytes(32, "big", signed=True)
                                  + bytes.fromhex(r["voter"][2:]) + TIME.to_bytes(32, "big") + anc
                                  + ROUND_ID.to_bytes(32, "big") + ident)
                    commits.append({"sender": t["from"].lower(), "voter": r["voter"], "input": enc_commit(ident, TIME, anc, h),
                                    "tokens": str(r["tokens"])})
                    hits += 1
            assert hits == 1, (r["tx"], hits)
            dev = "0x" + bytes(raw).hex()
        txs.append({"hash": r["tx"], "from": t["from"].lower(), "to": t["to"].lower(), "input": inp, "inputDev": dev,
                    "block": r["block"], "ts": int(blk["timestamp"], 16), "voter": r["voter"], "price": str(r["price"]),
                    "tokens": str(r["tokens"]), "coalition": r["voter"] in coalition})
    reveal_start = (ROUND_ID * 2 + 1) * 86_400
    eth_fork = last_block_before(EEP, reveal_start, txs[0]["block"] - 20_000, txs[0]["block"])
    # Polygon: the child tunnel log that carries this request's resolved price (the hash appears in its data)
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
    delivered = None
    for b0 in range(hi, hi + 6 * 1800, 2000):
        for lg in rpc(PEP, "eth_getLogs", [{"address": CHILD_TUNNEL, "fromBlock": hex(b0), "toBlock": hex(b0 + 1999)}]):
            if ANC_HASH in lg["data"] or ANC_HASH.encode().hex() in lg["data"]:
                delivered = int(lg["blockNumber"], 16)
                break
        if delivered:
            break
    assert delivered, "price delivery not found"
    # largest net "No" buyers during the vote (executable_profit.py windows), as holders whose redemption we replay
    gm = json.load(open(glob.glob(os.path.join(DATA, "raw", "pm_cache", f"gamma_{COND[:24]}.json"))[0], encoding="utf-8"))[0]
    toks = json.loads(gm["clobTokenIds"])
    net = {}
    for f in glob.glob(os.path.join(DATA, "raw", "trades_cache", f"{COND[:18]}_*.json")):
        j = json.load(open(f))
        if not isinstance(j, list):
            continue
        for tr in j:
            if tr.get("asset") == toks[1]:
                net[tr["proxyWallet"].lower()] = net.get(tr["proxyWallet"].lower(), 0) + (1 if tr["side"] == "BUY" else -1) * float(tr["size"])
    holders = [w for w, _ in sorted(net.items(), key=lambda kv: -kv[1])[:args.holders]]
    out = {"ethForkBlock": eth_fork, "polygonForkBlock": delivered - 1, "polygonDeliveryBlock": delivered,
           "roundId": ROUND_ID, "time": TIME, "identifier": "0x" + ident.hex(), "ancillaryData": "0x" + anc.hex(),
           "roundEnd": round_end, "revealStart": reveal_start, "questionID": gm["questionID"], "conditionId": COND,
           "yesPosition": toks[0], "noPosition": toks[1], "k": args.k,
           "froms": [t["from"] for t in txs], "tos": [t["to"] for t in txs], "inputs": [t["input"] for t in txs],
           "inputsDev": [t["inputDev"] for t in txs], "blocks": [t["block"] for t in txs], "timestamps": [t["ts"] for t in txs],
           "coalitionFlags": [t["coalition"] for t in txs], "voters": [t["voter"] for t in txs],
           "commitSenders": [c["sender"] for c in commits], "commitInputs": [c["input"] for c in commits],
           "coalitionVoters": [c["voter"] for c in commits], "noHolders": holders}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1)
    print("eth fork block", eth_fork, "| polygon fork block", delivered - 1, "| coalition commits", len(commits),
          "| reveal txs", len(txs), "| holders", len(holders))


def split(path=OUT):
    """Foundry holds a cheatcode-read file in EVM memory, so the 27 MB fixture is split: one binary calldata file per
    replayed transaction (baseline and capture variants), and a small JSON with everything else."""
    j = json.load(open(path))
    d = os.path.join(os.path.dirname(path), "ceasefire")
    os.makedirs(d, exist_ok=True)
    for k, (a, b) in enumerate(zip(j["inputs"], j["inputsDev"])):
        open(os.path.join(d, f"in_{k}.bin"), "wb").write(bytes.fromhex(a[2:]))
        open(os.path.join(d, f"dev_{k}.bin"), "wb").write(bytes.fromhex(b[2:]))
    meta = {k: v for k, v in j.items() if k not in ("inputs", "inputsDev")}
    meta["n"] = len(j["inputs"])
    json.dump(meta, open(os.path.join(os.path.dirname(path), "ceasefire_meta.json"), "w"), indent=1)
    print("split into", meta["n"], "transactions")


def find_reveal(inp, ident, t, anc):
    """The request's revealVote call embedded anywhere in a transaction input: returns the standalone call bytes."""
    raw = bytes.fromhex(inp[2:])
    pat = REVEAL_SEL + ident + t.to_bytes(32, "big")
    i = raw.find(pat)
    while i >= 0:
        head = raw[i + 4: i + 4 + 160]
        off = int.from_bytes(head[96:128], "big")
        ln = int.from_bytes(raw[i + 4 + off: i + 4 + off + 32], "big")
        if raw[i + 4 + off + 32: i + 4 + off + 32 + ln] == anc:
            end = i + 4 + off + 32 + ((ln + 31) // 32) * 32
            return raw[i:end]
        i = raw.find(pat, i + 1)
    return None


def split_single(path=OUT):
    """For each replayed transaction, the request's own revealVote call alone (baseline and capture price) and the
    direct caller of VotingV2, so that a transaction which fails on the fork for an unrelated reason (a wrapper or
    another call in the same batch) can still deliver this request's vote."""
    import csv
    j = json.load(open(path))
    d = os.path.join(os.path.dirname(path), "ceasefire")
    ident = bytes.fromhex(j["identifier"][2:])
    anc = bytes.fromhex(j["ancillaryData"][2:])
    caller = {}
    with open(os.path.join(DATA, "votes_long.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["roundId"] == str(ROUND_ID) and r["requestTime"] == str(TIME):
                caller[r["voter"].lower()] = r["caller"].lower()
    callers, wrapped = [], 0
    for k, (a, b, v) in enumerate(zip(j["inputs"], j["inputsDev"], j["voters"])):
        base = find_reveal(a, ident, TIME, anc)
        assert base is not None, k
        dev = find_reveal(b, ident, TIME, anc)
        if dev is None:
            dev = base
        if j["coalitionFlags"][k]:
            dev = bytearray(base)
            dev[4 + 64: 4 + 96] = (0).to_bytes(32, "big")
            dev = bytes(dev)
        open(os.path.join(d, f"cf_{k}.bin"), "wb").write(base)
        open(os.path.join(d, f"cfdev_{k}.bin"), "wb").write(dev)
        callers.append(caller[v])
        wrapped += a[:10] not in ("0x" + MULTI_SEL.hex(), "0x" + REVEAL_SEL.hex())
    meta_p = os.path.join(os.path.dirname(path), "ceasefire_meta.json")
    meta = json.load(open(meta_p))
    meta["callers"] = callers
    json.dump(meta, open(meta_p, "w"), indent=1)
    print("single reveals written for", len(callers), "transactions;", wrapped, "wrapped in another call")


if __name__ == "__main__":
    import sys
    if "--split" in sys.argv:
        split()
        split_single()
    else:
        main()
        split()
