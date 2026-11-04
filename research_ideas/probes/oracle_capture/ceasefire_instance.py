"""The ceasefire instance, in one ledger: "Israel x Hezbollah ceasefire by April 18, 2026?" (round 10281, the
payout-deciding request, DVM time 1776364190).

  * who sold the false side: net "No" buyers during the vote (executable_profit.py windows), the price distribution
    of their purchases, the "Yes" purchases on the other side, and how much of it was minted (a "No" purchase in the
    same transaction as a "Yes" purchase is a mint match);
  * when the prize was minted: open interest at the escalating dispute, a day later, at the start of the reveal phase,
    at the decisive reveal and at the end of the round (cached PositionSplit / PositionsMerge logs);
  * who could have voted it: the round's voters on the request by stake, and the smallest set of largest voters that
    carries "No" given the honest "No" votes;
  * what it would have cost: the coalition's stake, the whole staked supply and every UMA token, at the UMA close of
    the day the round ended.
Writes data/ceasefire_instance.json.
"""
import csv
import glob
import json
import os
from collections import defaultdict

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
COND = "0x9823d715687a0a82d2a03731792e83bf58a0409f10def1379e00e4d67a95ba69"
ROUND_ID, TIME = 10281, 1776364190
ESC_BLOCK = 85623719
W1 = [(1776364190, 1776503695), (1776503696, 1776643200)]
W2 = [(1776643200, 1776695159)]
UMA = "0x04Fa0d235C4abf4BcF4787aF4CF447DE572eF828"


def window(t0, t1):
    out = []
    for f in sorted(glob.glob(os.path.join(DATA, "raw", "trades_cache", f"{COND[:18]}_{t0}_{t1}_*.json"))):
        j = json.load(open(f))
        if isinstance(j, list):
            out += j
    return out


def main():
    gm = json.load(open(glob.glob(os.path.join(DATA, "raw", "pm_cache", f"gamma_{COND[:24]}.json"))[0], encoding="utf-8"))[0]
    yes, no = json.loads(gm["clobTokenIds"])
    res = {"fees_enabled": gm.get("feesEnabled"), "tick": gm.get("orderPriceMinTickSize"), "negRisk": gm.get("negRisk")}
    for name, wins in (("vote_to_reveal", W1), ("reveal_to_decisive", W2)):
        tr = [t for a, b in wins for t in window(a, b)]
        net, bought, paid = defaultdict(float), defaultdict(float), defaultdict(float)
        no_buy = yes_buy = yes_cost = at_tick = 0.0
        no_tx, yes_tx = defaultdict(float), set()
        for t in tr:
            w, sz, pr = t["proxyWallet"].lower(), float(t["size"]), float(t["price"])
            if t["asset"] == no:
                if t["side"] == "BUY":
                    net[w] += sz
                    bought[w] += sz
                    paid[w] += sz * pr
                    no_buy += sz
                    at_tick += sz if pr <= 0.001 + 1e-12 else 0.0
                    no_tx[t["transactionHash"]] += sz
                else:
                    net[w] -= sz
            elif t["asset"] == yes and t["side"] == "BUY":
                yes_buy += sz
                yes_cost += sz * pr
                yes_tx.add(t["transactionHash"])
        pos = sorted(((v, w) for w, v in net.items() if v > 0), reverse=True)
        shares = sum(v for v, _ in pos)
        cost = sum(v * paid[w] / bought[w] for v, w in pos if bought[w] > 0)
        res[name] = {"net_buyers": len(pos), "net_shares": shares, "cost": cost, "revenue": shares - cost,
                     "largest_buyer_share": pos[0][0] / shares if pos else None,
                     "no_bought_gross": no_buy, "no_bought_at_tick_share": at_tick / no_buy if no_buy else None,
                     "yes_bought": yes_buy, "yes_avg_price": yes_cost / yes_buy if yes_buy else None,
                     "no_bought_in_mint_matches_share": sum(v for h, v in no_tx.items() if h in yes_tx) / no_buy if no_buy else None}
    res["net_shares_total"] = res["vote_to_reveal"]["net_shares"] + res["reveal_to_decisive"]["net_shares"]
    res["cost_total"] = res["vote_to_reveal"]["cost"] + res["reveal_to_decisive"]["cost"]
    res["revenue_total"] = res["net_shares_total"] - res["cost_total"]
    # open interest path (split minus merge), blocks from prize_growth.py's cache and the round's phases
    ev = []
    for topic, sign in (("0x2e6bb91f", 1), ("0x6f13ca62", -1)):
        p = glob.glob(os.path.join(DATA, "raw", "econ_cache", f"{topic}_{COND[:18]}_*.json"))[0]
        for lg in json.load(open(p)):
            ev.append((int(lg["blockNumber"], 16), sign * int.from_bytes(bytes.fromhex(lg["data"][2:])[64:96], "big") / 1e6))
    ts = json.load(open(os.path.join(DATA, "raw", "prize_cache", "block_ts.json")))
    pts = sorted((int(k), v) for k, v in ts.items())

    def block_at(t):
        lo = max(p for p in pts if p[1] <= t)
        hi = min(p for p in pts if p[1] > t)
        return int(lo[0] + (t - lo[1]) * (hi[0] - lo[0]) / (hi[1] - lo[1]))
    t_esc = next(v for k, v in pts if k == ESC_BLOCK) if any(k == ESC_BLOCK for k, _ in pts) else None
    marks = {"escalation": ESC_BLOCK, "escalation_plus_24h": block_at((t_esc or TIME) + 86_400),
             "commit_start": block_at(ROUND_ID * 172_800), "reveal_start": block_at(ROUND_ID * 172_800 + 86_400),
             "decisive_reveal": block_at(1776695159), "round_end": block_at((ROUND_ID + 1) * 172_800 - 1)}
    res["oi_path"] = {k: sum(a for b, a in ev if b <= blk) for k, blk in marks.items()}
    res["t_escalation"] = t_esc
    # the round's voters on this request (votes_long.csv), and the coalition that carries No
    vot, by_price = {}, defaultdict(float)
    with open(os.path.join(DATA, "votes_long.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["roundId"] == str(ROUND_ID) and r["requestTime"] == str(TIME):
                vot[r["voter"].lower()] = (float(r["shareOfStaked"]), r["price"])
                by_price[r["price"]] += float(r["shareOfStaked"])
    h_no = by_price.get("p1", 0.0)
    need = 0.65 - h_no
    shares = sorted(((s, v, p) for v, (s, p) in vot.items() if p != "p1"), reverse=True)
    cum, k = 0.0, 0
    for s, v, p in shares:
        cum += s
        k += 1
        if cum > need:
            break
    res["voters"] = len(vot)
    res["votes_by_answer_share_of_staked"] = dict(by_price)
    res["h_no"] = h_no
    res["capture_needs"] = need
    res["coalition_k"] = k
    res["coalition_share"] = cum
    res["largest_voter_share"] = shares[0][0]
    pts_csv = {r["conditionId"]: r for r in csv.DictReader(open(os.path.join(DATA, "capture_economics_points.csv"), encoding="utf-8"))}
    pt = pts_csv[COND]
    S, px = float(pt["S"]), float(pt["uma_price"])
    supply = int(requests.post("https://ethereum-rpc.publicnode.com", json={"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                                "params": [{"to": UMA, "data": "0x18160ddd"}, "latest"]}, timeout=60).json()["result"], 16) / 1e18
    res.update({"staked_supply": S, "uma_price": px, "stake_value": S * px, "coalition_stake_value": cum * S * px,
                "capture_stake_value": float(pt["V_F"]), "uma_total_supply_now": supply, "all_uma_value": supply * px,
                "revenue_over_stake_value": res["revenue_total"] / (S * px),
                "revenue_over_all_uma": res["revenue_total"] / (supply * px)})
    json.dump(res, open(os.path.join(DATA, "ceasefire_instance.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
