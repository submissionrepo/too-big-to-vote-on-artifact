"""Participation in the first DVM round of every request, the round on which tally settlement pays (2026-10-08).

pi_first = (all first-round votes on the request) / (the round's frozen staked supply). The first-round tallies come
from first_round_tallies.csv (UMA); a round's staked supply is the cumulativeStakeAtRound that requests_summary.csv
records for any request resolved in that round (the contract freezes it per round, so all of them agree).
Writes data/first_round_participation.csv keyed by (roundId, requestTime, ancKey) of the resolving round.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def load(name):
    return list(csv.DictReader(open(os.path.join(DATA, name), encoding="utf-8")))


stake = {}
for r in load("requests_summary.csv"):
    x = float(r["cumulativeStakeAtRound"])
    if r["roundId"] in stake:
        assert abs(stake[r["roundId"]] - x) <= 1e-6 * x, (r["roundId"], stake[r["roundId"]], x)
    stake[r["roundId"]] = x

rows, missing = [], 0
for t in load("first_round_tallies.csv"):
    first = t["firstRoundId"]
    if first not in stake:
        missing += 1
        continue
    votes = sum(float(t[k] or 0) for k in ("first_p1", "first_p2", "first_p3", "first_p4", "first_other"))
    rows.append({"roundId": t["roundId"], "requestTime": t["requestTime"], "ancKey": t["ancKey"], "firstRoundId": first,
                 "votes_first": f"{votes:.6f}", "stake_first": f"{stake[first]:.6f}", "pi_first": f"{votes / stake[first]:.8f}"})
with open(os.path.join(DATA, "first_round_participation.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(f"{len(rows)} requests written, {missing} without a staked supply for their first round")
