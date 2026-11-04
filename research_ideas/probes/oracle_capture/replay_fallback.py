"""Historical replay of the tape fallback F_mu on every resolved Polymarket DVM request that it would have moved.

For each resolved request with winner share x* < 1 - mu (mu in {0.20, 0.25}):
  1. recover the question title (plain text for the pre-compression era, polygon_dispute_map.csv afterwards),
  2. find the Polymarket market with that exact question through the Gamma public-search endpoint,
  3. pull the hourly price history of the YES token for the 24 hours before the DVM request time (the dispute),
  4. compute the pre-dispute TWAP phat and compare it with the DVM's answer: did the vote confirm the market
     favourite (phat on the winner's side > 1/2) or overturn it?
Outputs data/replay_fallback.csv and data/replay_fallback_summary.json. Network calls are cached in data/raw/replay_cache/.
"""
import csv
import datetime as dt
import json
import os
import re
import time

import requests

import pm_markets as pm
from reqkey import text_hash

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "raw", "replay_cache")
os.makedirs(CACHE, exist_ok=True)
MUS = {"0.20": 0.80, "0.25": 0.75}
WINDOW = 24 * 3600


def cached_get(url, params, key):
    path = os.path.join(CACHE, key + ".json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=60)
            j = r.json()
            json.dump(j, open(path, "w", encoding="utf-8"))
            time.sleep(0.15)
            return j
        except Exception:  # noqa: BLE001
            time.sleep(1.5)
    return None


def title_from_text(text):
    m = re.search(r"q:\s*title:\s*(.*?),\s*description:", text, re.S)
    return m.group(1).strip() if m else None


def find_market(title):
    # the endpoint's firewall rejects some punctuation (a double quote with a dollar sign returns 403), so the query
    # keeps words only; the match below is still on the exact question text
    q = re.sub(r"\s+", " ", re.sub(r"[^\w\s.\-]", " ", title)).strip()
    j = cached_get("https://gamma-api.polymarket.com/public-search", {"q": q[:120], "limit_per_type": 10},
                   "search_" + re.sub(r"[^a-zA-Z0-9]+", "_", title)[:80])
    if not j:
        return None
    cands = []
    for ev in j.get("events", []) or []:
        for m in ev.get("markets", []) or []:
            cands.append(m)
    for m in j.get("markets", []) or []:
        cands.append(m)
    norm = lambda s: re.sub(r"\s+", " ", (s or "")).strip().lower()
    exact = [m for m in cands if norm(m.get("question")) == norm(title)]
    pick = exact[0] if exact else None
    if pick is None:
        return None
    toks = pick.get("clobTokenIds")
    if isinstance(toks, str):
        toks = json.loads(toks)
    outs = pick.get("outcomes")
    if isinstance(outs, str):
        outs = json.loads(outs)
    return {"id": pick.get("id"), "question": pick.get("question"), "conditionId": pick.get("conditionId"),
            "tokens": toks, "outcomes": outs, "volume": pick.get("volumeNum") or pick.get("volume")}


def twap_before(token, t_end):
    j = cached_get("https://clob.polymarket.com/prices-history",
                   {"market": token, "startTs": t_end - WINDOW - 3600, "endTs": t_end, "fidelity": 60},
                   f"px_{token[:24]}_{t_end}")
    if not j or "history" not in j:
        return None, 0
    pts = [x for x in j["history"] if t_end - WINDOW <= x["t"] <= t_end]
    if not pts:
        return None, 0
    return sum(x["p"] for x in pts) / len(pts), len(pts)


def main():
    reqs = list(csv.DictReader(open(os.path.join(DATA, "requests_summary.csv"), encoding="utf-8")))
    titles = {}
    mp = os.path.join(DATA, "polygon_dispute_map.csv")
    if os.path.exists(mp):
        for r in csv.DictReader(open(mp, encoding="utf-8")):
            if r["title"]:
                titles[(r["roundId"], r["requestTime"], r["hash"])] = r["title"]
    bar = max(MUS.values())   # the loosest mu (0.20, bar 0.80) selects every request the tighter one also moves
    sel = [r for r in reqs if r["isPolymarket"] == "True" and r["modeShareOfStaked"] and float(r["modeShareOfStaked"]) < bar]
    print("tape-triggered Polymarket requests at the loosest mu:", len(sel))
    anc = pm.load_ancillary()
    rows = []
    n_title = n_market = n_px = 0
    for k, r in enumerate(sel):
        title = title_from_text(r["text"]) if r["text"].startswith("q:") else titles.get((r["roundId"], r["requestTime"], text_hash(r["text"])))
        if not title:
            rows.append({**{kk: r[kk] for kk in ("roundId", "requestTime", "ancKey", "resolvedPrice", "modeShareOfStaked", "minorityShareOfVotes")},
                         "title": "", "status": "no-title"})
            continue
        n_title += 1
        # exact match first: conditionId derived from the oracle-stamped ancillary data (pm_markets.py); title search
        # only for neg-risk markets, whose conditionId is not derivable from the adapter's question
        a = anc.get((r["identifier"], int(r["requestTime"]), r["ancKey"]))
        mm = pm.match(a, title_search=lambda _t, _title=title: find_market(_title)) if a is not None else {"status": "no-ancillary"}
        m = mm.get("market") if mm["status"] == "ok" else None
        if m is not None:
            m["how"] = mm["how"]
        if not m or not m.get("tokens"):
            rows.append({**{kk: r[kk] for kk in ("roundId", "requestTime", "ancKey", "resolvedPrice", "modeShareOfStaked", "minorityShareOfVotes")},
                         "title": title, "status": "no-market"})
            continue
        n_market += 1
        yes_tok = m["tokens"][0]
        phat, npts = twap_before(yes_tok, int(r["requestTime"]))
        if phat is None:
            rows.append({**{kk: r[kk] for kk in ("roundId", "requestTime", "ancKey", "resolvedPrice", "modeShareOfStaked", "minorityShareOfVotes")},
                         "title": title, "status": "no-prices", "conditionId": m["conditionId"], "volume": m["volume"]})
            continue
        n_px += 1
        win = r["resolvedPrice"]
        # price of the DVM winner's side before the dispute (p4/too-early has no side)
        pw = phat if win == "p2" else (1 - phat if win == "p1" else None)
        rows.append({**{kk: r[kk] for kk in ("roundId", "requestTime", "ancKey", "resolvedPrice", "modeShareOfStaked", "minorityShareOfVotes")},
                     "title": title, "status": "ok", "conditionId": m["conditionId"], "volume": m["volume"], "match": m.get("how", ""),
                     "yes_twap_24h": round(phat, 4), "n_points": npts,
                     "winner_side_price": round(pw, 4) if pw is not None else "",
                     "vote_overturned_market": (pw is not None and pw < 0.5),
                     **{f"tape_mu_{mu}": float(r["modeShareOfStaked"]) < b for mu, b in MUS.items()}})
        if (k + 1) % 25 == 0:
            print(f"{k+1}/{len(sel)} processed; titles {n_title}, markets {n_market}, prices {n_px}", flush=True)
    keys = sorted({kk for row in rows for kk in row.keys()})
    with open(os.path.join(DATA, "replay_fallback.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    ok = [x for x in rows if x["status"] == "ok"]
    summary = {"n_selected": len(sel), "n_with_title": n_title, "n_market_found": n_market, "n_with_prices": n_px}
    for mu, b in MUS.items():
        sub = [x for x in ok if x.get(f"tape_mu_{mu}")]
        sided = [x for x in sub if x["winner_side_price"] != ""]
        over = [x for x in sided if x["vote_overturned_market"]]
        pw = sorted(x["winner_side_price"] for x in sided)
        summary[f"mu_{mu}"] = {"tape_cases_with_prices": len(sub), "with_a_side": len(sided),
                               "vote_overturned_market_favourite": len(over),
                               "winner_side_price_quantiles": {"p10": pw[len(pw) // 10] if pw else None,
                                                               "p50": pw[len(pw) // 2] if pw else None,
                                                               "p90": pw[int(0.9 * len(pw))] if pw else None},
                               "too_early_cases": sum(1 for x in sub if x["resolvedPrice"] == "p4")}
    json.dump(summary, open(os.path.join(DATA, "replay_fallback_summary.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
