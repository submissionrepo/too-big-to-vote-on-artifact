"""Yes purchases on the March 2025 minerals-deal market around the vote, from the same trade tape as
executable_profit.py (data-api trades, cached in data/raw/trades_cache/).

Windows: from the request reaching the vote to the last of the three wallets' reveals, and from that reveal to the
round's end, when the outcome was fixed on-chain. Gross purchases (every BUY of the Yes token), the wallets that
bought, the price range, and the price path of the last hour in ten-minute steps.
Writes data/march_trades_summary.json.
"""
import glob
import json
import os

from executable_profit import trades

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
COND = "0x1663edea3eba0d1ae8f064276dd426cb0497a19bb5188dae48a2f8fa8ea34da8"
# the payout-deciding request (index 827, the second dispute's); the first settled only the first dispute's bonds
T_REQ, T_LAST, T_END = 1742684664, 1742857199, 1742860800


def main():
    gm = json.load(open(glob.glob(os.path.join(DATA, "raw", "pm_cache", f"gamma_{COND[:24]}.json"))[0], encoding="utf-8"))[0]
    yes = json.loads(gm["clobTokenIds"])[0]
    out = {}
    for name, (a, b) in (("request_to_last_reveal", (T_REQ, T_LAST)), ("last_reveal_to_end", (T_LAST, T_END))):
        buys = [t for t in trades(COND, a, b) if t.get("asset") == yes and t.get("side") == "BUY"]
        sh = sum(float(t["size"]) for t in buys)
        cost = sum(float(t["size"]) * float(t["price"]) for t in buys)
        px = sorted(float(t["price"]) for t in buys)
        out[name] = {"buys": len(buys), "shares": round(sh), "cost": round(cost), "avg_price": cost / sh if sh else None,
                     "min_price": px[0] if px else None, "max_price": px[-1] if px else None,
                     "wallets": len({t["proxyWallet"] for t in buys})}
        if name == "last_reveal_to_end":
            steps = []
            for k in range(6):
                sub = [float(t["price"]) for t in buys if T_LAST + 600 * k <= int(t["timestamp"]) < T_LAST + 600 * (k + 1)]
                steps.append({"minutes": [10 * k, 10 * (k + 1)], "n": len(sub), "min": min(sub) if sub else None,
                              "max": max(sub) if sub else None})
            out[name]["ten_minute_steps"] = steps
            # share of the hour's purchases (by shares) made at 35 cents or less
            out[name]["shares_le_35c"] = round(sum(float(t["size"]) for t in buys if float(t["price"]) <= 0.35))
    json.dump(out, open(os.path.join(DATA, "march_trades_summary.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
