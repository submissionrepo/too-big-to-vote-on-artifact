"""Kill test for the free roll: does the market reprice when a DVM vote rolls?

A roll costs no one anything (Proposition 1), and a committed voter can withhold its reveal after seeing the others'.
If a roll moves the market, a pivotal staker who holds the side the roll helps profits without changing any answer.
For every RequestRolled event of a Polymarket request: the rolled round is the one that ended just before the event;
its leading answer is the answer with the most revealed stake in that round (votes_long.csv). The market is matched
exactly (pm_markets.py). We read the leading answer's price by the minute around the round's end, when the roll
becomes certain: one hour before, at the end, and 1, 6 and 24 hours after.
Writes data/roll_prices.csv and data/roll_prices_summary.json; caches in data/raw/leak_cache/ (shared with reveal_leak.py).
"""
import csv
import glob
import json
import os
import statistics as st
from collections import defaultdict

import pm_markets as pm
from abi_min import decode_log, event_topic
from replay_fallback import find_market, title_from_text
from reveal_leak import eth_block_time, minute_prices

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ROUND = 172_800


def main():
    reqs = {(r["identifier"], r["requestTime"]): r for r in csv.DictReader(open(os.path.join(DATA, "requests_summary.csv"), encoding="utf-8"))}
    rolls = [r for r in csv.DictReader(open(os.path.join(DATA, "rolls.csv"), encoding="utf-8")) if r["event"] == "RequestRolled"]
    rolls = [r for r in rolls if (r["identifier"], r["time"]) in reqs and reqs[(r["identifier"], r["time"])]["isPolymarket"] == "True"]
    titles = {(row["roundId"], row["requestTime"]): row["title"] for row in csv.DictReader(open(os.path.join(DATA, "polygon_dispute_map.csv"), encoding="utf-8")) if row["title"]}
    anc = pm.load_ancillary()
    # rolled rounds and their tallies
    want = {}
    for r in rolls:
        t_ev = eth_block_time(int(r["block"]))
        rnd = t_ev // ROUND - 1          # the round that ended at the last boundary before the event
        want[(r["time"], str(rnd))] = (r, t_ev, rnd)
    # votes_long.csv keeps only the resolving round, so the rolled rounds' reveals are decoded from the raw logs;
    # shares use the staked supply of the resolving round (rounds are two days apart)
    tally = defaultdict(lambda: defaultdict(float))
    keys = {(k[0], k[1]) for k in want}
    padded = {format(int(t), "064x") for t, _ in keys}
    t_vr = event_topic("VoteRevealed(address,address,uint32,bytes32,uint256,bytes,int256,uint128)")
    seen = set()
    S_of = {r["time"]: float(reqs[(r["identifier"], r["time"])]["cumulativeStakeAtRound"]) for r in rolls}
    label = {str(10**18): "p2", "0": "p1", str(5 * 10**17): "p3", str(-(1 << 255)): "p4"}
    for path in sorted(glob.glob(os.path.join(DATA, "raw", "votingv2_logs*.jsonl"))):
        for line in open(path, encoding="utf-8"):
            if t_vr not in line:
                continue
            lg = json.loads(line)
            if lg["topics"][0] != t_vr or lg["data"][2 + 64:2 + 128] not in padded:
                continue
            uid = (lg["transactionHash"], lg["logIndex"])
            if uid in seen:
                continue
            seen.add(uid)
            name, f = decode_log(lg)
            k = (str(f["time"]), str(f["roundId"]))
            if k in keys:
                tally[k][label.get(str(f["price"]), str(f["price"]))] += int(f["numTokens"]) / 1e18 / S_of[str(f["time"])]
    rows = []
    for (rt, rnd), (r, t_ev, rnd_i) in sorted(want.items(), key=lambda kv: int(kv[0][0])):
        q = reqs[(r["identifier"], r["time"])]
        tl = tally[(rt, rnd)]
        base = {"requestTime": rt, "rolledRound": rnd, "rollCount": r["rollCount"]}
        if not tl:
            rows.append({**base, "status": "no-votes-in-round"})
            continue
        lead = max(tl, key=tl.get)
        lead_share = tl[lead]
        second = max((v for p, v in tl.items() if p != lead), default=0.0)
        title_hint = title_from_text(q["text"]) if q["text"].startswith("q:") else titles.get((q["roundId"], q["requestTime"]))
        a = anc.get((r["identifier"], int(rt)))
        m = pm.match(a, title_search=lambda _t, _h=title_hint: find_market(_h) if _h else None) if a is not None else {"status": "no-ancillary"}
        mk = (m.get("market") or {}) if m["status"] == "ok" else {}
        toks = mk.get("tokens")
        base.update({"title": mk.get("question") or title_hint or "", "lead": lead, "lead_share_staked": round(lead_share, 4),
                     "second_share_staked": round(second, 4)})
        if lead not in ("p1", "p2") or not toks:
            rows.append({**base, "status": "leader-not-a-side" if lead not in ("p1", "p2") else "no-market"})
            continue
        tok = toks[0] if lead == "p2" else toks[1]
        t_end = (rnd_i + 1) * ROUND
        hist = minute_prices(tok, t_end - 6 * 3600, t_end + 26 * 3600)
        if not hist:
            rows.append({**base, "status": "no-prices"})
            continue
        def at(t):
            before = [p for tt, p in hist if tt <= t]
            return before[-1] if before else None
        p = {k: at(t_end + dt) for k, dt in (("m60", -3600), ("end", 0), ("p60", 3600), ("p6h", 6 * 3600), ("p24h", 24 * 3600))}
        rows.append({**base, "status": "ok", **{f"price_{k}": v for k, v in p.items()},
                     "drop_1h": (p["end"] - p["p60"]) if p["end"] is not None and p["p60"] is not None else None,
                     "drop_24h": (p["end"] - p["p24h"]) if p["end"] is not None and p["p24h"] is not None else None})
        x = rows[-1]
        print(f"{x['title'][:46]:46s} lead {lead} {lead_share:.3f}  end {p['end']}  +1h {p['p60']}  +24h {p['p24h']}", flush=True)
    keys_out = sorted({k for r in rows for k in r})
    with open(os.path.join(DATA, "roll_prices.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys_out)
        w.writeheader()
        w.writerows(rows)
    ok = [r for r in rows if r["status"] == "ok" and r["drop_1h"] is not None]
    d1 = sorted(r["drop_1h"] for r in ok)
    d24 = sorted(r["drop_24h"] for r in ok if r["drop_24h"] is not None)
    summ = {"n_roll_events": len(rows), "status_counts": {s: sum(1 for r in rows if r["status"] == s) for s in sorted({r["status"] for r in rows})},
            "n_ok": len(ok), "drop_1h_median": st.median(d1) if d1 else None, "drop_24h_median": st.median(d24) if d24 else None,
            "n_drop_1h_ge_0.05": sum(1 for d in d1 if d >= 0.05), "n_drop_1h_ge_0.10": sum(1 for d in d1 if d >= 0.10),
            "n_drop_24h_ge_0.10": sum(1 for d in d24 if d >= 0.10), "price_end_median": st.median(r["price_end"] for r in ok) if ok else None}
    json.dump(summ, open(os.path.join(DATA, "roll_prices_summary.json"), "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
