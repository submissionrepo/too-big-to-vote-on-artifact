"""Could capture pay? Open interest of each contested Polymarket question at the end of its resolving round versus the
value of the stake needed to reverse the vote as cast.

Markets are matched exactly (pm_markets.py: questionID and conditionId derived from the oracle-stamped ancillary data
and confirmed on the CTF), with a Gamma title search only for neg-risk markets.

Open interest at the end of the resolving round = sum of PositionSplit amounts minus PositionsMerge amounts for the
conditionId (an indexed topic of both events) from the condition's preparation to the last Polygon block at or
before the round end; one full set pays one dollar, so this is the most either side can be paid.
Stake to reverse the vote as cast: an incumbent who voted with the winner (or abstained) and votes the runner-up
instead makes it resolve iff its stake exceeds theta - r, r the runner-up's share of the staked supply (Theorem 1
with h_F = r). Its value at the day's UMA close is V_flip; delta = OI / V_flip is the largest fraction of that stake's
value a capturer could lose and still break even when it holds the whole losing side at no cost (an upper bound).

Usage: python capture_economics.py [--test]
Writes data/capture_economics.csv; caches in data/raw/econ_cache/.
"""
import csv
import datetime as dt
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pm_markets as pm
from abi_min import event_topic
from replay_fallback import find_market, title_from_text
from reqkey import req_key, text_hash

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "raw", "econ_cache")
os.makedirs(CACHE, exist_ok=True)
CTF = pm.CTF
T_SPLIT = event_topic("PositionSplit(address,address,bytes32,bytes32,uint256[],uint256)")
T_MERGE = event_topic("PositionsMerge(address,address,bytes32,bytes32,uint256[],uint256)")
T_PREP = event_topic("ConditionPreparation(bytes32,address,bytes32,uint256)")
SPAN = 400_000
SPAT_CHANGE_BLOCK = 22309220
ROUND = 172_800
TS = {}
LOCK = threading.Lock()
TS_PATH = os.path.join(CACHE, "polygon_block_ts.json")
if os.path.exists(TS_PATH):
    TS.update({int(k): v for k, v in json.load(open(TS_PATH)).items()})


def block_ts(b):
    if b in TS:
        return TS[b]
    t = int(pm.rpc("eth_getBlockByNumber", [hex(b), False])["timestamp"], 16)
    with LOCK:
        TS[b] = t
    return t


def last_block_at_or_before(ts):
    """Exact: the last Polygon block whose timestamp is <= ts (bisection seeded by interpolation)."""
    if len(TS) < 2:
        latest = int(pm.rpc("eth_blockNumber", []), 16)
        block_ts(latest)
        block_ts(40_000_000)
    pts = sorted(TS.items())
    lo = max(((b, t) for b, t in pts if t <= ts), default=(40_000_000, block_ts(40_000_000)))
    hi = min(((b, t) for b, t in pts if t > ts), default=None)
    if hi is None:
        latest = int(pm.rpc("eth_blockNumber", []), 16)
        hi = (latest, block_ts(latest))
    (lb, lt), (hb, ht) = lo, hi
    while hb - lb > 1:
        if hb - lb > 64:
            g = lb + int((ts - lt) * (hb - lb) / max(1, ht - lt))
            g = min(max(g, lb + 1), hb - 1)
        else:
            g = (lb + hb) // 2
        t = block_ts(g)
        if t <= ts:
            lb, lt = g, t
        else:
            hb, ht = g, t
    return lb


def logs_by_cond(topic0, cond, fb, tb):
    key = os.path.join(CACHE, f"{topic0[:10]}_{cond[:18]}_{fb}_{tb}.json")
    if os.path.exists(key):
        return json.load(open(key))
    out, b, span = [], fb, SPAN
    while b <= tb:
        e = min(b + span - 1, tb)
        try:
            out += pm.rpc("eth_getLogs", [{"address": CTF, "topics": [topic0, None, None, cond], "fromBlock": hex(b), "toBlock": hex(e)}])
        except RuntimeError:
            if span > 20_000:
                span //= 4
                continue
            raise
        b = e + 1
    json.dump(out, open(key, "w"))
    return out


def preparation_block(cond, before):
    """ConditionPreparation (conditionId is topic 1), searched backwards in 1M-block windows."""
    key = os.path.join(CACHE, f"prep_{cond[:18]}.json")
    if os.path.exists(key):
        return json.load(open(key))["block"]
    tb = before
    for _ in range(40):
        fb = max(0, tb - 1_000_000)
        res = pm.rpc("eth_getLogs", [{"address": CTF, "topics": [T_PREP, cond], "fromBlock": hex(fb), "toBlock": hex(tb)}])
        if res:
            blk = int(res[0]["blockNumber"], 16)
            json.dump({"block": blk}, open(key, "w"))
            return blk
        if fb == 0:
            break
        tb = fb - 1
    return None


def amount_of(log):
    return int.from_bytes(bytes.fromhex(log["data"][2:])[64:96], "big")


def one(c, r, anc, titles, prices):
    base = {"roundId": c["roundId"], "requestTime": c["requestTime"], "ancKey": c["ancKey"], "resolvedBlock": r["resolvedBlock"],
            "winner": c["winner"], "runnerUp": r["runnerUpPrice"], "winnerShareOfStaked": c["winnerShareOfStaked"],
            "minorityShareOfVotes": c["minorityShareOfVotes"], "k": c["kSupportersWhoseRemovalRolls"],
            "top1SupporterShareOfStaked": c["top1SupporterShareOfStaked"]}
    a = anc.get((r["identifier"], int(c["requestTime"]), r["ancKey"]))
    if a is None:
        return {**base, "status": "no-ancillary"}
    title_hint = title_from_text(r["text"]) if r["text"].startswith("q:") else titles.get((r["roundId"], r["requestTime"], text_hash(r["text"])))
    m = pm.match(a, title_search=lambda _t: find_market(title_hint) if title_hint else None)
    if m["status"] != "ok":
        return {**base, "title": title_hint or m.get("title", ""), "status": m["status"]}
    cond = m["conditionId"]
    mk = m.get("market") or {}
    t_end = (int(c["roundId"]) + 1) * ROUND
    tb = last_block_at_or_before(t_end)
    fb = preparation_block(cond, tb)
    if fb is None:
        return {**base, "title": title_hint or m["title"], "conditionId": cond, "status": "no-preparation"}
    splits = logs_by_cond(T_SPLIT, cond, fb, tb)
    merges = logs_by_cond(T_MERGE, cond, fb, tb)
    oi = (sum(map(amount_of, splits)) - sum(map(amount_of, merges))) / 1e6
    S = float(r["cumulativeStakeAtRound"])
    theta = 0.5 if int(r["resolvedBlock"]) < SPAT_CHANGE_BLOCK else 0.65
    runner = float(r["runnerUpShareOfStaked"] or 0)
    winner = float(r["modeShareOfStaked"])
    top1 = float(c["top1SupporterShareOfStaked"] or 0)
    sigma_flip = max(0.0, theta - runner)
    sigma_top = max(0.0, theta - (winner - top1))  # what the winner's largest supporter needed (March reading)
    day = dt.datetime.fromtimestamp(t_end - 1, dt.timezone.utc).date()
    px = next((prices[str(day - dt.timedelta(days=k))] for k in range(5) if str(day - dt.timedelta(days=k)) in prices), None)
    v_flip = sigma_flip * S * px if px else None
    return {**base, "title": mk.get("question") or title_hint or m["title"], "status": "ok", "match": m["how"],
            "negRisk": mk.get("negRisk"), "conditionId": cond, "prep_block": fb, "round_end_block": tb,
            "n_splits": len(splits), "n_merges": len(merges), "oi_usdc": round(oi, 2), "theta": theta,
            "stakedSupply": round(S), "runnerUpShareOfStaked": round(runner, 5), "sigma_flip": round(sigma_flip, 5),
            "sigma_top": round(sigma_top, 5), "uma_price": px,
            "v_flip_usd": round(v_flip) if v_flip else None,
            "v_top_usd": round(sigma_top * S * px) if px else None,
            "v_top1_held_usd": round(top1 * S * px) if px else None,
            "delta_flip": round(oi / v_flip, 6) if v_flip else None}


def main():
    test = "--test" in sys.argv
    anc = pm.load_ancillary()
    reqs = {req_key(r): r for r in csv.DictReader(open(os.path.join(DATA, "requests_summary.csv"), encoding="utf-8"))}
    cont = [c for c in csv.DictReader(open(os.path.join(DATA, "contested_requests.csv"), encoding="utf-8")) if c["isPolymarket"] == "True"]
    titles = {}
    for row in csv.DictReader(open(os.path.join(DATA, "polygon_dispute_map.csv"), encoding="utf-8")):
        if row["title"]:
            titles[(row["roundId"], row["requestTime"], row["hash"])] = row["title"]
    prices = {r["date"]: float(r["close"]) for r in csv.DictReader(open(os.path.join(DATA, "uma_usd_daily_coinbase.csv")))}
    if test:
        cont = [c for c in cont if c["requestTime"] in ("1742680702", "1742684664")]
    rows = [None] * len(cont)

    def work(i):
        c = cont[i]
        try:
            rows[i] = one(c, reqs[req_key(c)], anc, titles, prices)
        except Exception as e:  # noqa: BLE001
            rows[i] = {"roundId": c["roundId"], "requestTime": c["requestTime"], "ancKey": c["ancKey"], "status": f"error: {e}"[:200]}
        x = rows[i]
        print(f"{i+1}/{len(cont)} [{x.get('match', x['status'])}] {str(x.get('title', ''))[:46]:46s} "
              f"OI {x.get('oi_usdc') or 0:>12,.0f}  V_flip ${x.get('v_flip_usd') or 0:>11,.0f}", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=1 if test else 4) as ex:
        list(ex.map(work, range(len(cont))))
    json.dump({str(k): v for k, v in TS.items()}, open(TS_PATH, "w"))
    print(f"done in {time.time()-t0:.0f}s")
    out_csv = os.path.join(DATA, "capture_economics_test.csv" if test else "capture_economics.csv")
    keys = sorted({k for r in rows for k in r})
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
