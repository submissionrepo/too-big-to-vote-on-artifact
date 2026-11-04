"""From exposure to an executable strategy: what a capturer could actually have bought.

For each contested Polymarket market-round of capture_economics_points.csv, F is the side the vote did not choose.
A coalition that intends to carry F buys F shares while they are cheap and before its own reveal. We take the market's
actual trades and assume the coalition replaces the wallets that ended each window holding more F than they started
with: a share bought and resold inside the window counts once, at the net buyer's average purchase price. Its
executable revenue if F is paid one dollar is
    E = sum over net buyers of net shares * (1 - average purchase price).
Windows: W1 from the request reaching the vote (requestTime) to the start of the reveal phase, when no vote is
visible; W2 from the start of the reveal phase to the historical decisive reveal (reveal_leak.csv) or, when there was
none, to one hour before the round's end. Trades come from Polymarket's public data API (takerOnly=false, so both
sides of each fill are listed; purchases are the records with side BUY), paged within each window.

Outputs data/executable_profit.csv and data/executable_profit_summary.json; caches pages in data/raw/trades_cache/.
"""
import csv
import glob
import json
import os
import statistics as st
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "raw", "trades_cache")
os.makedirs(CACHE, exist_ok=True)
ROUND = 172_800
API = "https://data-api.polymarket.com/trades"


def page(cond, t0, t1, offset):
    path = os.path.join(CACHE, f"{cond[:18]}_{t0}_{t1}_{offset}.json")
    if os.path.exists(path):
        return json.load(open(path))
    for attempt in range(6):
        try:
            r = requests.get(API, params={"market": cond, "start": t0, "end": t1, "limit": 500, "offset": offset,
                                          "takerOnly": "false"}, timeout=60)
            j = r.json()
            if isinstance(j, dict) and "error" in j:
                return {"error": j["error"]}
            json.dump(j, open(path, "w"))
            time.sleep(0.15)
            return j
        except Exception:  # noqa: BLE001
            time.sleep(1.5 + attempt)
    return {"error": "request failed"}


def trades(cond, t0, t1):
    """All trades in [t0, t1]; windows that hit the API's offset cap are split in two."""
    out, off = [], 0
    while True:
        j = page(cond, t0, t1, off)
        if isinstance(j, dict):
            if t1 - t0 < 60:
                return out
            mid = (t0 + t1) // 2
            return trades(cond, t0, mid) + trades(cond, mid + 1, t1)
        out += j
        if len(j) < 500:
            return out
        off += 500
        if off >= 10_000:
            mid = (t0 + t1) // 2
            return trades(cond, t0, mid) + trades(cond, mid + 1, t1)


def march_yes():
    """March 2025 was captured toward YES. Executable revenue on YES for the three wallets, in three windows: from the
    request reaching the vote to the reveal phase, from there to their last reveal, and from their last reveal to the
    round's end (when the outcome was fixed on-chain and the market still sold YES cheaply)."""
    cond = "0x1663edea3eba0d1ae8f064276dd426cb0497a19bb5188dae48a2f8fa8ea34da8"
    gm = json.load(open(glob.glob(os.path.join(DATA, "raw", "pm_cache", f"gamma_{cond[:24]}.json"))[0], encoding="utf-8"))[0]
    yes = json.loads(gm["clobTokenIds"])[0]
    # the payout-deciding request (the second dispute's, index 827); the first request settled only the first dispute's bonds
    t_req, t_end, t_last = 1742684664, 1742860800, 1742857199
    out = {}
    for name, (a, b) in (("dispute_to_reveal_start", (t_req, t_end - 86_400)),
                         ("reveal_start_to_last_whale", (t_end - 86_400, t_last)), ("after_last_whale", (t_last, t_end))):
        net, bought, paid = defaultdict(float), defaultdict(float), defaultdict(float)
        tr = trades(cond, a, b)
        for t in tr:
            if t.get("asset") != yes:
                continue
            w_, sz, pr = t.get("proxyWallet"), float(t["size"]), float(t["price"])
            if t.get("side") == "BUY":
                net[w_] += sz
                bought[w_] += sz
                paid[w_] += sz * pr
            else:
                net[w_] -= sz
        n = sum(v for v in net.values() if v > 0)
        c = sum(v * paid[w_] / bought[w_] for w_, v in net.items() if v > 0 and bought[w_] > 0)
        out[name] = {"trades": len(tr), "net_yes_shares": round(n), "cost": round(c), "revenue_if_yes": round(n - c)}
    tot = sum(v["revenue_if_yes"] for v in out.values())
    whale_value = 5083491.385946123 * 1.409   # the three wallets' stake at the close of March 24, 2025
    res = {"windows": out, "total": tot, "whale_stake_value": whale_value, "break_even": tot / whale_value}
    json.dump(res, open(os.path.join(DATA, "executable_profit_march_yes.json"), "w"), indent=1)
    return res


def main():
    pts = list(csv.DictReader(open(os.path.join(DATA, "capture_economics_points.csv"), encoding="utf-8")))
    leak = {}
    for r in csv.DictReader(open(os.path.join(DATA, "reveal_leak.csv"), encoding="utf-8")):
        if r["status"] == "ok":
            k = (r["roundId"], r["conditionId"])
            leak[k] = min(int(r["t_cross"]), leak.get(k, 1 << 62))
    shares = [float(v["shareOfCumulative"]) for v in csv.DictReader(open(os.path.join(DATA, "voters_current.csv"), encoding="utf-8"))]
    rows = [None] * len(pts)

    def one(i):
        p = pts[i]
        g = glob.glob(os.path.join(DATA, "raw", "pm_cache", f"gamma_{p['conditionId'][:24]}.json"))
        gm = json.load(open(g[0], encoding="utf-8")) if g else []
        toks = gm[0].get("clobTokenIds") if gm else None
        toks = json.loads(toks) if isinstance(toks, str) else toks
        if not toks:
            rows[i] = {"roundId": p["roundId"], "conditionId": p["conditionId"], "status": "no-token"}
            return
        tokF = toks[0] if p["F"] == "p2" else toks[1]
        t_req = int(p["requestTime"])
        t_end = (int(p["roundId"]) + 1) * ROUND
        t_rev = t_end - 86_400
        t_cut = leak.get((p["roundId"], p["conditionId"]), t_end - 3600)
        res = {}
        for name, (a, b) in (("w1", (t_req, t_rev)), ("w2", (t_rev, max(t_rev, t_cut)))):
            tr = trades(p["conditionId"], a, b) if b > a else []
            # a share bought and resold inside the window is one share: count each wallet's net purchase of F,
            # priced at that wallet's average purchase price (the coalition takes the place of the net buyers)
            net, bought, paid = defaultdict(float), defaultdict(float), defaultdict(float)
            for t in tr:
                if t.get("asset") != tokF:
                    continue
                w_, sz, pr = t.get("proxyWallet"), float(t["size"]), float(t["price"])
                if t.get("side") == "BUY":
                    net[w_] += sz
                    bought[w_] += sz
                    paid[w_] += sz * pr
                else:
                    net[w_] -= sz
            n = sum(v for v in net.values() if v > 0)
            c = sum(v * paid[w_] / bought[w_] for w_, v in net.items() if v > 0 and bought[w_] > 0)
            gross = sum(float(t["size"]) for t in tr if t.get("asset") == tokF and t.get("side") == "BUY")
            res[name] = {"n_trades": len(tr), "shares": n, "cost": c, "revenue": n - c, "gross_bought": gross}
        S, px = float(p["S"]), float(p["uma_price"])
        E = res["w1"]["revenue"] + res["w2"]["revenue"]
        row = {"roundId": p["roundId"], "conditionId": p["conditionId"], "title": p["title"], "F": p["F"], "era": p["era"],
               "sigma_F": float(p["sigma_F"]), "oi": float(p["oi"]), "V_F": float(p["V_F"]), "status": "ok",
               "w1_shares": round(res["w1"]["shares"]), "w1_revenue": round(res["w1"]["revenue"]),
               "w2_shares": round(res["w2"]["shares"]), "w2_revenue": round(res["w2"]["revenue"]),
               "gross_bought": round(res["w1"]["gross_bought"] + res["w2"]["gross_bought"]),
               "E": round(E), "E_over_OI": E / float(p["oi"]) if float(p["oi"]) > 0 else None,
               "delta_exec": E / float(p["V_F"]) if float(p["V_F"]) > 0 else None,
               "stake_value_total": S * px}
        for k in (1, 2, 4, 10):
            sk = sum(shares[:k])
            row[f"delta_top{k}"] = (E / (sk * S * px)) if float(p["sigma_F"]) <= sk else None
        rows[i] = row
        print(f"{i+1}/{len(pts)} {p['title'][:44]:44s} E ${E:>12,.0f}  OI ${float(p['oi']):>12,.0f}  delta_exec {row['delta_exec']:.4f}", flush=True)

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(one, range(len(pts))))
    keys = sorted({k for r in rows for k in r})
    with open(os.path.join(DATA, "executable_profit.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    ok = [r for r in rows if r["status"] == "ok"]
    de = sorted(r["delta_exec"] for r in ok if r["delta_exec"] is not None)
    eo = sorted(r["E_over_OI"] for r in ok if r["E_over_OI"] is not None)
    summ = {"n": len(ok), "E_total": round(sum(r["E"] for r in ok)), "E_median": st.median(r["E"] for r in ok),
            "E_max": max(r["E"] for r in ok), "E_over_OI_median": st.median(eo),
            "delta_exec_quantiles": {q: de[int(q * (len(de) - 1))] for q in (0.5, 0.9)}, "delta_exec_max": de[-1],
            "n_delta_exec_ge": {str(c): sum(1 for d in de if d >= c) for c in (0.01, 0.05, 0.1, 0.25, 1.0)},
            "top": sorted(({k: r[k] for k in ("title", "roundId", "E", "oi", "V_F", "delta_exec", "sigma_F")} for r in ok),
                          key=lambda r: -r["delta_exec"])[:8]}
    for k in (1, 2, 4, 10):
        vals = [r[f"delta_top{k}"] for r in ok if r[f"delta_top{k}"] is not None]
        summ[f"top{k}"] = {"n_capturable": len(vals), "max_delta": max(vals) if vals else None,
                           "n_ge_0.01": sum(1 for v in vals if v >= 0.01)}
    mar = [r for r in ok if r["roundId"] == "10085"]  # the payout request (capture_economics_summary.py keeps it)
    summ["march"] = mar[0] if mar else None
    json.dump(summ, open(os.path.join(DATA, "executable_profit_summary.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in summ.items() if k != "top"}, indent=1))
    for t in summ["top"]:
        print(t)
    print("March, YES side:", march_yes())


if __name__ == "__main__":
    main()
