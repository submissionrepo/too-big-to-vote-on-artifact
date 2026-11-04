"""How much does a visible manipulation of a protocol's own vote cost its governance token?

Event set: the captures and attempted captures of a vote listed in Table 1 of Feichtinger, Fritsch, Heimbach,
Vonlanthen and Wattenhofer, "SoK: Attacks on DAOs" (arXiv:2406.15071v2), whose date is public and whose governance
token has daily prices for the MIN_HISTORY = 365 days before the event, plus two later captures of the same kind
(Compound's proposal 289, UMA's March 2025 vote). Dates are the day the capture took place or became public, from the
SoK and the reports cited in EVENTS. Events with a shorter price history are computed and written to the CSV with
included = False, and enter no summary: Beanstalk (208 days; BEAN is the protocol's stablecoin, its votes were Stalk)
and Venus's VIP-42 (342 days). Incidents without any token price history (True Seigniorage Dollar, Yuan Finance,
Genesis Alpha, The DAO) are left out; Temple DAO and ForceDAO were contract exploits that did not go through a vote.

Prices: DefiLlama's coins API (CoinGecko identifiers), one price per day stamped near 00:00 UTC, for the token, ETH and
BTC. Day 0 is the event date; the k-day abnormal log return is ln P(d+k)/P(d) for the token minus the same for ETH
(and, as a check, BTC), for k = 1, 3, 7. Its standard deviation is that of overlapping k-day abnormal returns over the
365 days before the event, and z = CAR / sd.

Pooled test on the captures that took nothing from the protocol: the mean weekly abnormal log return, its standard
error from each token's own weekly noise (events treated as independent), and the smallest mean loss a two-sided 5%
test detects with 80% power, 1 - exp(-(1.96 + 0.84) se); the 50%-power value 1 - exp(-1.96 se) is kept for reference.
The mean is also reported without Indexed, whose token tripled against ETH in the week of the vote. The one-sided
95% upper confidence bound on the mean weekly loss uses the spread across events (t with n - 1 degrees of freedom),
with and without Indexed. At the 80%-power loss, the contested market-rounds beyond delta (1 - 2 mu) V are also
checked against the shares a coalition could have bought from the market's trades (executable_profit.csv, windows
one and two: the net purchases of the wallets that bought the losing side on net before the decisive reveal).

Outputs data/delta_event_study.csv (one row per event) and data/delta_event_study.json (summary, and the number of
contested UMA market-rounds that tally settlement with mu = 0.2 leaves unprotected at the measured losses).
"""
import csv
import json
import math
import os
import statistics as st
import time

import requests
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "raw", "llama_cache")
os.makedirs(CACHE, exist_ok=True)
DAY = 86_400

# name, token id, event date (UTC), what was taken through the vote, kind, whether the capture drained or diluted the
# protocol itself (its treasury, collateral or token supply), source of the date. Build Finance's second proposal was
# created on 10 February 2022 and the token was minted and dumped the same day (the press reported it on 14 February).
EVENTS = [
    ("Steem", "steem", "2020-03-02", "exchange-held stake voted in a new set of witnesses", "stake vote", False, "Decrypt 2020; SoK"),
    ("Build Finance", "build-finance", "2022-02-10", "hidden proposal took the token contract; mint and liquidity drain", "proposal", True, "SoK; The Block 2022-02-14"),
    ("Beanstalk", "bean", "2022-04-17", "flash-loaned majority passed a proposal draining the protocol", "flash-loan vote", True, "SoK case study"),
    ("Audius", "audius", "2022-07-23", "initialization bug, then a proposal moving the community treasury", "proposal", True, "Decrypt 2022; SoK"),
    ("Mango Markets", "mango-markets", "2022-10-11", "oracle manipulation of MNGO drained the treasury", "oracle", True, "SEC LR-25623; SoK"),
    ("Tornado Cash", "tornado-cash", "2023-05-20", "disguised proposal replaced with code minting votes", "proposal", True, "SoK case study"),
    ("Synthetify", "synthetify-token", "2023-10-17", "hidden proposal withdrew the DAO's funds", "proposal", True, "SoK case study"),
    ("Curio", "curio-governance", "2024-03-23", "voting-power flaw used to mint governance tokens", "proposal", True, "The Block 2024-03-25; SoK"),
    ("Compound 289", "compound-governance-token", "2024-07-28", "whale coalition passed a transfer of 499,000 COMP to its vault", "stake vote", False, "Invezz 2024-07-29"),
    ("UMA", "uma", "2025-03-25", "three wallets carried a disputed Polymarket answer", "stake vote", False, "this paper, Section 4.4"),
    # attempts in the SoK that were stopped or reversed: visible manipulations of the vote that took nothing from the
    # protocol
    ("Maker flash vote", "maker", "2020-10-26", "flash-loaned MKR passed an executive vote (B.Protocol)", "flash-loan vote", False, "Decrypt 2020; The Block 2020; SoK"),
    ("Venus VIP-42", "venus", "2021-09-14", "proposal paying voters to install a new team; passed, then cancelled", "bribe", False, "Watcher.Guru 2021; SoK"),
    ("Curve, Mochi", "curve-dao-token", "2021-11-12", "gauge votes steered to Mochi's pool; gauge killed by the Emergency DAO", "gauge vote", False, "Curve newsletter 2021-11-12; BlockTempo 2021-11-12; SoK"),
    ("Compound TUSD", "compound-governance-token", "2022-02-04", "borrowed COMP routed through an exchange to propose TUSD collateral", "stake vote", False, "Forklog 2022; AMBCrypto 2022; SoK"),
    ("Yam", "yam-2", "2022-07-09", "proposal hiding a treasury transfer reached quorum; stopped", "proposal", False, "The Block 2022-07-10; Decrypt 2022; SoK"),
    ("Indexed", "indexed-finance", "2023-11-16", "bought NDX to pass a proposal taking the timelock; narrowly voted down", "stake vote", False, "SoK case study"),
]
# Left out: Kleros (December 2023; the governor attacked was Proof of Humanity's, so the token at stake is unclear),
# MakerDAO C (January 2022; no public date for the MKR borrowed to vote), BigCap and Binance's UNI delegation (no
# price history; an accident).
WINDOWS = (1, 3, 7)
MIN_HISTORY = 365
TICKER = {"steem": "STEEM", "build-finance": "BUILD", "bean": "BEAN", "audius": "AUDIO", "mango-markets": "MNGO",
          "tornado-cash": "TORN", "synthetify-token": "SNY", "curio-governance": "CGT",
          "compound-governance-token": "COMP", "uma": "UMA", "maker": "MKR", "venus": "XVS",
          "curve-dao-token": "CRV", "yam-2": "YAM", "indexed-finance": "NDX"}


def day_ts(date):
    return int(time.mktime(time.strptime(date + " 00:00:00", "%Y-%m-%d %H:%M:%S"))) - time.timezone


def chart(cid, start, span):
    path = os.path.join(CACHE, f"{cid}_{start}_{span}.json")
    if os.path.exists(path):
        return json.load(open(path))
    for attempt in range(5):
        try:
            r = requests.get(f"https://coins.llama.fi/chart/coingecko:{cid}", params={"start": start, "span": span, "period": "1d"}, timeout=60)
            j = r.json()
            prices = j["coins"][f"coingecko:{cid}"]["prices"]
            json.dump(prices, open(path, "w"))
            time.sleep(0.3)
            return prices
        except Exception:  # noqa: BLE001
            time.sleep(2 + 2 * attempt)
    raise RuntimeError(f"no prices for {cid}")


def daily(cid, t0, t1):
    """{UTC date: price} from t0 to t1, fetched in spans of 200 days."""
    out = {}
    t = t0
    while t < t1:
        span = min(200, (t1 - t) // DAY + 1)
        for p in chart(cid, t, span):
            out[time.strftime("%Y-%m-%d", time.gmtime(p["timestamp"] + 6 * 3600))] = p["price"]
        t += span * DAY
    return out


def main():
    rows = []
    for name, cid, date, what, kind, drained, src in EVENTS:
        d0 = day_ts(date)
        t0, t1 = d0 - 400 * DAY, d0 + 10 * DAY
        tok, eth, btc = daily(cid, t0, t1), daily("ethereum", t0, t1), daily("bitcoin", t0, t1)
        days = sorted(set(tok) & set(eth) & set(btc))
        idx = {dd: i for i, dd in enumerate(days)}
        if date not in idx:
            rows.append({"event": name, "status": "no price on the event day"})
            continue
        i0 = idx[date]
        lr = lambda s, a, b: math.log(s[days[b]] / s[days[a]])
        row = {"event": name, "token": cid, "ticker": TICKER[cid], "date": date, "kind": kind, "drained": drained,
               "what": what, "source": src, "price_before": tok[days[i0]], "history_days": i0,
               "included": i0 >= MIN_HISTORY}
        for k in WINDOWS:
            if i0 + k >= len(days):
                continue
            car_e = lr(tok, i0, i0 + k) - lr(eth, i0, i0 + k)
            car_b = lr(tok, i0, i0 + k) - lr(btc, i0, i0 + k)
            pre = [lr(tok, j, j + k) - lr(eth, j, j + k) for j in range(max(0, i0 - 365), i0 - k)]
            sd = st.pstdev(pre) if len(pre) > 30 else None
            row[f"car{k}_eth"] = car_e
            row[f"car{k}_btc"] = car_b
            row[f"sd{k}_eth"] = sd
            row[f"z{k}_eth"] = car_e / sd if sd else None
            row[f"loss{k}_eth"] = 1 - math.exp(car_e)
        rows.append(row)
        print(f"{name:14s} {date}  CAR7(ETH) {100*row.get('car7_eth', float('nan')):7.1f}%  z {row.get('z7_eth') or float('nan'):5.2f}  "
              f"CAR1 {100*row.get('car1_eth', float('nan')):6.1f}%  history {i0} d", flush=True)
    keys = sorted({k for r in rows for k in r}, key=lambda k: (k not in ("event", "token", "date", "kind"), k))
    with open(os.path.join(DATA, "delta_event_study.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    ok = [r for r in rows if "car1_eth" in r and r["included"]]
    left_out = {r["event"]: r["history_days"] for r in rows if "car1_eth" in r and not r["included"]}
    # the loss used for each event: the 7-day window, or the longest window the price series covers (Curio's token
    # was replaced the day after the exploit)
    for r in ok:
        k = max(k for k in WINDOWS if f"car{k}_eth" in r)
        r["window_used"] = k
        r["loss_used"] = r[f"loss{k}_eth"]
        r["z_used"] = r[f"z{k}_eth"]
    drained = [r for r in ok if r["drained"]]
    clean = [r for r in ok if not r["drained"]]
    ld = sorted(r["loss_used"] for r in drained)
    pooled = lambda cs: {
        "n": len(cs),
        "mean_car7": st.mean(r["car7_eth"] for r in cs),
        "se": math.sqrt(sum(r["sd7_eth"] ** 2 for r in cs)) / len(cs),
    }
    pc = [r for r in clean if r.get("car7_eth") is not None and r.get("sd7_eth")]
    summ = {
        "n_events": len(ok),
        "min_history_days": MIN_HISTORY,
        "left_out_short_history": left_out,
        "drained": {"n": len(drained), "loss_median": st.median(ld), "loss_min": ld[0], "loss_max": ld[-1],
                    "n_significant": sum(1 for r in drained if (r["z_used"] or 0) < -1.96)},
        "not_drained": {"n": len(clean), "events": {r["event"]: {"loss": r["loss_used"], "z": r["z_used"]} for r in clean},
                        "n_significant": sum(1 for r in clean if (r["z_used"] or 0) < -1.96)},
        # pooled test on the captures that took nothing from the protocol (see the docstring)
        "pooled_not_drained": pooled(pc),
        "pooled_not_drained_without_indexed": pooled([r for r in pc if r["event"] != "Indexed"]),
        "indexed_week_ratio_vs_eth": next(math.exp(r["car7_eth"]) for r in pc if r["event"] == "Indexed"),
        "by_event": {r["event"]: {k: r.get(k) for k in ("date", "kind", "drained", "window_used", "car1_eth", "car3_eth",
                                                        "car7_eth", "z1_eth", "z7_eth", "car7_btc", "loss_used", "z_used")} for r in ok},
    }
    # the limit at the measured losses: contested UMA market-rounds that need more than that delta (mu = 0.2)
    pts = list(csv.DictReader(open(os.path.join(DATA, "capture_economics_points.csv"), encoding="utf-8")))
    need = [float(p["oi"]) / (0.6 * float(p["S"]) * float(p["uma_price"])) for p in pts]
    pool = summ["pooled_not_drained"]
    pool["z"] = pool["mean_car7"] / pool["se"]
    pool["mean_loss"] = 1 - math.exp(pool["mean_car7"])
    pool["detectable_loss_50"] = 1 - math.exp(-1.96 * pool["se"])
    pool["detectable_loss"] = 1 - math.exp(-(1.96 + 0.8416) * pool["se"])   # 80% power
    wo = summ["pooled_not_drained_without_indexed"]
    wo["z"] = wo["mean_car7"] / wo["se"]

    def upper95_loss(cs):
        xs = [r["car7_eth"] for r in cs]
        se = st.stdev(xs) / math.sqrt(len(xs))
        return 1 - math.exp(min(0.0, st.mean(xs) - stats.t.ppf(0.95, len(xs) - 1) * se))
    summ["upper95_loss_crosssection"] = {"all": upper95_loss(pc),
                                         "without_indexed": upper95_loss([r for r in pc if r["event"] != "Indexed"])}
    for label, dl in (("drained_median", summ["drained"]["loss_median"]), ("drained_min", summ["drained"]["loss_min"]),
                      ("drained_max", summ["drained"]["loss_max"]), ("penalty", 0.001),
                      ("detectable", pool["detectable_loss"])):
        summ[f"unprotected_at_{label}"] = {"delta": dl, "n": sum(1 for x in need if x > dl), "of": len(need)}
    # the market-rounds beyond the limit at the 80%-power loss, against the shares a coalition could have bought
    ex = {(r["roundId"], r["conditionId"]): r for r in csv.DictReader(open(os.path.join(DATA, "executable_profit.csv"),
                                                                         encoding="utf-8")) if r["status"] == "ok"}
    det = pool["detectable_loss"]
    limit = lambda p: det * 0.6 * float(p["S"]) * float(p["uma_price"])
    beyond = [p for p in pts if float(p["oi"]) > limit(p)]
    bought = lambda p: (float(ex[(p["roundId"], p["conditionId"])]["w1_shares"] or 0)
                        + float(ex[(p["roundId"], p["conditionId"])]["w2_shares"] or 0))
    summ["buyable_at_detectable"] = {
        "beyond": len(beyond),
        "with_trades": sum(1 for p in beyond if (p["roundId"], p["conditionId"]) in ex),
        "buyable_above_limit": sum(1 for p in beyond if (p["roundId"], p["conditionId"]) in ex and bought(p) > limit(p))}
    json.dump(summ, open(os.path.join(DATA, "delta_event_study.json"), "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in summ.items() if k != "by_event"}, indent=1, default=str))


if __name__ == "__main__":
    main()
