"""Per-answer tallies (share of the staked supply) of every contested request in its resolving round, from
data/votes_long.csv. Answers: p1 = No (0), p2 = Yes (1e18), p3 = one half, p4 = too early.
Writes data/contested_answer_tallies.csv (used by capture_economics_summary.py to find the side the vote did not choose).
"""
import csv
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def main():
    cont = list(csv.DictReader(open(os.path.join(DATA, "contested_requests.csv"), encoding="utf-8")))
    keys = {(c["roundId"], c["requestTime"], c["ancKey"]) for c in cont}
    tal = defaultdict(lambda: defaultdict(float))
    with open(os.path.join(DATA, "votes_long.csv"), encoding="utf-8") as f:
        rd = csv.reader(f)
        h = next(rd)
        iR, iT, iP, iS, iA = (h.index(x) for x in ("roundId", "requestTime", "price", "shareOfStaked", "ancKey"))
        for row in rd:
            k = (row[iR], row[iT], row[iA])
            if k in keys:
                tal[k][row[iP]] += float(row[iS])
    out = []
    for c in cont:
        t = tal[(c["roundId"], c["requestTime"], c["ancKey"])]
        out.append({"roundId": c["roundId"], "requestTime": c["requestTime"], "ancKey": c["ancKey"],
                    **{p: round(t.get(p, 0.0), 6) for p in ("p1", "p2", "p3", "p4")},
                    "other": round(sum(v for p, v in t.items() if p not in ("p1", "p2", "p3", "p4")), 6)})
    with open(os.path.join(DATA, "contested_answer_tallies.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(len(out), "contested requests tallied")


if __name__ == "__main__":
    main()
