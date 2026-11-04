"""Exact on-chain matching of DVM requests to Polymarket markets (shared by capture_economics.py and replay_fallback.py).

Polymarket's UmaCtfAdapter registers a question as
    questionID  = keccak256(ancillary data as initialized)
    conditionId = keccak256(adapter address || questionID || uint256(2))      (Gnosis CTF getConditionId)
and the oracle stamps ",ooRequester:<adapter>" onto the ancillary data it forwards to the DVM. So the DVM's ancillary
data, cut at the last ",ooRequester:", hashes to the questionID. Requests bridged after mid-2023 carry only
"ancillaryDataHash:<h>,childBlockNumber:<b>"; the stamped text is in the Polygon child tunnel's log at block b, and its
keccak equals h. A derived conditionId is accepted only if the CTF reports two outcome slots for it on Polygon.
Neg-risk markets are prepared by the NegRiskAdapter with a different questionId, so derivation fails for them and
the caller falls back to Gamma.
"""
import json
import os
import re
import time

import requests

from abi_min import decode_data, decode_log, encode_call, keccak256
from reqkey import anc_key

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "raw", "pm_cache")
os.makedirs(CACHE, exist_ok=True)
CTF = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
CHILD_TUNNEL = "0xac60353a54873c446101216829a6a98cdbbc3f3d"
LOG_EP = "https://polygon.gateway.tenderly.co"
STATE_EP = "https://polygon-bor-rpc.publicnode.com"


def rpc(method, params, ep=None, tries=8):
    last = None
    for attempt in range(tries):
        url = ep or (LOG_EP if method in ("eth_getLogs", "eth_getBlockByNumber", "eth_blockNumber") else STATE_EP)
        try:
            j = requests.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=120).json()
            if "error" in j:
                last = j["error"]
                time.sleep(1 + attempt)
                continue
            return j["result"]
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1 + attempt)
    raise RuntimeError(f"{method} failed: {last}")


def load_ancillary():
    """(identifier, time, ancKey) -> ancillary bytes, from every RequestResolved event of VotingV2.
    identifier and time alone are shared by requests of one event, so the key includes ancKey (reqkey.py)."""
    out = {}
    for line in open(os.path.join(DATA, "raw", "request_resolved_logs.jsonl"), encoding="utf-8"):
        name, f = decode_log(json.loads(line))
        if name == "RequestResolved":
            out[(f["identifier"], int(f["time"]), anc_key(f["ancillaryData"]))] = bytes.fromhex(f["ancillaryData"][2:])
    return out


def stamped(anc):
    """The oracle-stamped ancillary text: the DVM's own text, or the preimage recovered from the child tunnel."""
    text = anc.decode("utf-8", "replace")
    m = re.match(r"ancillaryDataHash:([0-9a-f]{64}),childBlockNumber:(\d+)", text)
    if not m:
        return anc
    h, blk = m.group(1), int(m.group(2))
    path = os.path.join(CACHE, f"stamped_{h[:24]}.bin")
    if os.path.exists(path):
        return open(path, "rb").read()
    res = rpc("eth_getLogs", [{"address": CHILD_TUNNEL, "fromBlock": hex(blk), "toBlock": hex(blk)}])
    for lg in res:
        data = bytes.fromhex(lg["data"][2:])
        # the stamped bytes sit word-aligned in the log data, preceded by their length word
        for p in range(32, len(data), 32):
            ln = int.from_bytes(data[p - 32:p], "big")
            if 0 < ln <= len(data) - p and keccak256(data[p:p + ln]).hex() == h:
                open(path, "wb").write(data[p:p + ln])
                return data[p:p + ln]
    return None


def derive_condition(st):
    i = st.rfind(b",ooRequester:")
    if i < 0:
        return None, None, None
    base = st[:i]
    oo = st[i + 13:i + 13 + 40].decode()
    qid = keccak256(base)
    cond = "0x" + keccak256(bytes.fromhex(oo) + qid + (2).to_bytes(32, "big")).hex()
    return cond, "0x" + qid.hex(), "0x" + oo


def slot_count(cond):
    path = os.path.join(CACHE, f"slots_{cond[:24]}.json")
    if os.path.exists(path):
        return json.load(open(path))["slots"]
    res = rpc("eth_call", [{"to": CTF, "data": encode_call("getOutcomeSlotCount(bytes32)", [int(cond, 16)])}, "latest"])
    n = decode_data(["uint256"], res)[0]
    json.dump({"slots": n}, open(path, "w"))
    return n


def gamma_by_condition(cond):
    path = os.path.join(CACHE, f"gamma_{cond[:24]}.json")
    if os.path.exists(path):
        j = json.load(open(path, encoding="utf-8"))
    else:
        j = None
        for attempt in range(4):
            try:
                j = requests.get("https://gamma-api.polymarket.com/markets",
                                 params={"condition_ids": cond, "closed": "true"}, timeout=60).json()
                break
            except Exception:  # noqa: BLE001
                time.sleep(1.5)
        if j is None:
            return None
        json.dump(j, open(path, "w", encoding="utf-8"))
    if not j:
        return None
    m = j[0]
    toks = m.get("clobTokenIds")
    toks = json.loads(toks) if isinstance(toks, str) else toks
    outs = m.get("outcomes")
    outs = json.loads(outs) if isinstance(outs, str) else outs
    return {"id": m.get("id"), "question": m.get("question"), "conditionId": m.get("conditionId"), "tokens": toks,
            "outcomes": outs, "negRisk": m.get("negRisk"), "questionID": m.get("questionID"),
            "volume": m.get("volumeNum") or m.get("volume"), "createdAt": m.get("createdAt")}


def title_of(st):
    m = re.search(rb"q:\s*title:\s*(.*?),\s*description:", st, re.S)
    return m.group(1).decode("utf-8", "replace").strip() if m else None


def match(anc, title_search=None):
    """-> dict(status, how, conditionId, title, market) for one request's ancillary bytes."""
    st = stamped(anc)
    if st is None:
        return {"status": "hash-unresolved"}
    title = title_of(st) or ""
    cond, qid, oo = derive_condition(st)
    if cond and slot_count(cond) == 2:
        mk = gamma_by_condition(cond)
        return {"status": "ok", "how": "derived", "conditionId": cond, "questionID": qid, "adapter": oo, "title": title,
                "market": mk}
    if title_search and title:
        mk = title_search(title)
        if mk and mk.get("conditionId"):
            full = gamma_by_condition(mk["conditionId"]) or mk
            return {"status": "ok", "how": "title", "conditionId": mk["conditionId"], "title": title, "market": full}
    return {"status": "no-market", "title": title}
