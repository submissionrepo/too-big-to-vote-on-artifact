"""Which Polymarket DVM requests decide what a market pays.

Polymarket's adapter resets a question on its first dispute (priceDisputed -> _reset) and sets questionData.reset,
which is never cleared; every later dispute only sets the refund flag. Every dispute is escalated to the DVM. So the
first DVM request of a question only decides who keeps that dispute's bonds, and every later request of the same
question is the one the adapter pays on. A question is identified by its oracle-stamped ancillary text (text era) or
by the hash of that text (hash era, since mid-2025): the text is the same for all of a question's requests.

The rule is checked against the chain: for all 162 contested Polymarket requests matched to a market,
request_roles.py looks for a RequestPrice log of the oracle (the reset) in the transaction of the escalating dispute,
and the two classifications agree in every case (check() below; data/request_roles.csv).
"""
import csv
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def question_key(text):
    m = re.search(r"ancillaryDataHash:([0-9a-f]{64})", text or "")
    if m:
        return "h:" + m.group(1)
    c = (text or "").find(",ooRequester:")
    return "t:" + ((text or "")[:c] if c > 0 else (text or ""))


def roles(reqs=None):
    """(requestTime, ancKey) -> 'payout' or 'bond-only' for every Polymarket request of requests_summary.csv."""
    if reqs is None:
        reqs = list(csv.DictReader(open(os.path.join(DATA, "requests_summary.csv"), encoding="utf-8")))
    groups = defaultdict(list)
    for q in reqs:
        if q["isPolymarket"] == "True":
            groups[question_key(q["text"])].append(q)
    out = {}
    for g in groups.values():
        g.sort(key=lambda q: int(q["requestTime"]))
        for i, q in enumerate(g):
            out[(str(q["requestTime"]), q["ancKey"])] = "bond-only" if i == 0 else "payout"
    return out


def is_payout(row, rl):
    return rl.get((str(row["requestTime"]), row["ancKey"])) == "payout"


def check():
    rl = roles()
    chain = list(csv.DictReader(open(os.path.join(DATA, "request_roles.csv"), encoding="utf-8")))
    agree = sum(1 for r in chain if rl.get((str(r["requestTime"]), r["ancKey"])) == r["role"])
    return agree, len(chain)


if __name__ == "__main__":
    rl = roles()
    print("Polymarket requests", len(rl), "payout", sum(1 for v in rl.values() if v == "payout"),
          "bond-only", sum(1 for v in rl.values() if v == "bond-only"))
    print("agreement with the chain (request_roles.csv):", check())
