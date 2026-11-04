"""Decode the raw VotingV2 dumps and build the tables used in the paper's evaluation.

Inputs : data/raw/votingv2_logs_*.jsonl (from fetch_votingv2_logs.py)
Outputs: data/requests_summary.csv   one row per resolved price request (tally in the resolving round)
         data/votes_long.csv         one row per revealed vote in a resolving round
         data/voters_current.csv     current stake per voter (eth_call voterStakes), delegate, share
         data/delegates_current.csv  stake controlled per delegate address
         data/concentration.json     top-k shares now and the stall / capture thresholds
         data/rolls.csv              roll and delete events

         data/first_round_tallies.csv  per resolved request: tallies by answer in its first voting round and in the
                                       resolving round (tally settlement pays on the first round)
         data/vote_counts.json       revealed votes in all rounds and in resolving rounds

Every table carries ancKey, a short hash of the request's ancillary data: identifier, time and round do not
identify a request (Polymarket requests of one event share them), so joins use (roundId, requestTime, ancKey).

Stake shares are computed against cumulativeStakeAtRound (frozen at the first reveal of the round), which is
exactly what the contract compares the SPAT agreement requirement against.

Usage: python summarize_votes.py [--tables-only]   (--tables-only skips the current-stake snapshot)
"""
import csv
import glob
import hashlib
import json
import os
import sys
from collections import defaultdict

from abi_min import ancillary_to_text, decode_log
from rpc import Rpc, VOTING_V2
from state_reads import read_round, read_voter

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data", "raw")
DATA = os.path.join(HERE, "data")

P1, P2, P3 = 0, 10**18, 5 * 10**17
TOO_EARLY = -(1 << 255)
WAD = 10**18


def anc_key(ancillary_hex):
    """Short stable key for a request's ancillary data (0x-prefixed hex as decoded from the logs)."""
    return hashlib.sha1(ancillary_hex.lower().encode()).hexdigest()[:16]


def label(price):
    return {P1: "p1", P2: "p2", P3: "p3", TOO_EARLY: "p4"}.get(price, str(price))


def load_logs():
    seen = set()
    rows = []
    bad = 0
    for path in sorted(glob.glob(os.path.join(RAW, "votingv2_logs_*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    lg = json.loads(line)
                except ValueError:  # a line still being written by a running fetcher
                    bad += 1
                    continue
                k = (lg["transactionHash"], lg["logIndex"])
                if k in seen:
                    continue
                seen.add(k)
                name, fields = decode_log(lg)
                if name:
                    fields["event"] = name
                    rows.append(fields)
    rows.sort(key=lambda r: (r["blockNumber"], r["logIndex"]))
    if bad:
        print("skipped unparsable lines:", bad)
    return rows


def main():
    rows = load_logs()
    print("decoded events:", len(rows))
    by_event = defaultdict(list)
    for r in rows:
        by_event[r["event"]].append(r)
    for k, v in sorted(by_event.items()):
        print(f"  {k:24s} {len(v)}")

    rpc = Rpc()
    key = lambda r: (r["identifier"], r["time"], r["ancillaryData"])

    added = {key(r): r for r in by_event["RequestAdded"]}
    resolved = {key(r): r for r in by_event["RequestResolved"]}
    rolled = defaultdict(list)
    for r in by_event["RequestRolled"]:
        rolled[key(r)].append(r["rollCount"])
    deleted = {key(r): r for r in by_event["RequestDeleted"]}

    votes_by_req_round = defaultdict(list)
    for v in by_event["VoteRevealed"]:
        votes_by_req_round[(key(v), v["roundId"])].append(v)

    # a round's frozen record never changes once the round has passed, so it is cached on disk
    rounds_path = os.path.join(RAW, "rounds_cache.json")
    rounds_cache = {int(k): v for k, v in json.load(open(rounds_path)).items()} if os.path.exists(rounds_path) else {}

    def round_info(rid):
        if rid not in rounds_cache:
            rounds_cache[rid] = read_round(rpc, rid)
        return rounds_cache[rid]

    # ---- per resolved request
    req_rows = []
    vote_rows = []
    first_rows = []
    for k, res in sorted(resolved.items(), key=lambda kv: kv[1]["blockNumber"]):
        rid = res["roundId"]
        votes = votes_by_req_round.get((k, rid), [])
        text = ancillary_to_text(k[2])
        rd = round_info(rid)
        cs = rd["cumulativeStakeAtRound"]
        by_price = defaultdict(int)
        by_voter = defaultdict(int)
        for v in votes:
            by_price[v["price"]] += v["numTokens"]
            by_voter[v["voter"]] += v["numTokens"]
        total = sum(by_price.values())
        ranked = sorted(by_price.items(), key=lambda kv: -kv[1])
        mode_p, mode_n = ranked[0] if ranked else (None, 0)
        run_p, run_n = ranked[1] if len(ranked) > 1 else (None, 0)
        top = sorted(by_voter.values(), reverse=True)
        is_pm = ("childChainId:137" in text) or ("polymarket" in text.lower())
        req_rows.append({
            "resolvedBlock": res["blockNumber"], "roundId": rid, "requestTime": k[1], "identifier": k[0],
            "isGovernance": added.get(k, {}).get("isGovernance", ""), "isPolymarket": is_pm,
            "rollCount": max(rolled.get(k, [0])) if k in rolled else 0,
            "resolvedPrice": label(res["price"]), "resolvedPriceRaw": res["price"],
            "cumulativeStakeAtRound": cs / WAD, "minParticipation": rd["minParticipationRequirement"] / WAD,
            "minAgreement": rd["minAgreementRequirement"] / WAD,
            "totalVotes": total / WAD, "participation": total / cs if cs else "",
            "nVoters": len(by_voter),
            "modePrice": label(mode_p) if mode_p is not None else "", "modeVotes": mode_n / WAD,
            "modeShareOfVotes": mode_n / total if total else "", "modeShareOfStaked": mode_n / cs if cs else "",
            "runnerUpPrice": label(run_p) if run_p is not None else "", "runnerUpVotes": run_n / WAD,
            "runnerUpShareOfStaked": run_n / cs if cs else "",
            "minorityShareOfVotes": (total - mode_n) / total if total else "",
            "top1ShareOfVotes": top[0] / total if top and total else "",
            "top5ShareOfVotes": sum(top[:5]) / total if top and total else "",
            "top10ShareOfVotes": sum(top[:10]) / total if top and total else "",
            "text": text[:160].replace("\n", " "), "ancKey": anc_key(k[2]),
        })
        for v in votes:
            vote_rows.append({
                "roundId": rid, "requestTime": k[1], "identifier": k[0], "voter": v["voter"], "caller": v["caller"],
                "price": label(v["price"]), "priceRaw": v["price"], "numTokens": v["numTokens"] / WAD,
                "shareOfStaked": v["numTokens"] / cs if cs else "", "block": v["blockNumber"],
                "resolvedPrice": label(res["price"]), "isPolymarket": is_pm, "ancKey": anc_key(k[2]),
            })
        # tallies by answer in the first round in which the request drew votes, and in the resolving round
        vote_rounds = sorted(r_ for (kk, r_) in votes_by_req_round if kk == k) if rolled.get(k) else [rid]
        first = vote_rounds[0] if vote_rounds else rid
        tally = lambda vs: {lab: sum(v["numTokens"] for v in vs if label(v["price"]) == lab) / WAD for lab in ("p1", "p2", "p3", "p4")}
        t_first, t_res = tally(votes_by_req_round.get((k, first), [])), tally(votes)
        first_rows.append({
            "roundId": rid, "requestTime": k[1], "identifier": k[0], "ancKey": anc_key(k[2]),
            "isPolymarket": is_pm, "rollCount": req_rows[-1]["rollCount"], "resolvedPrice": label(res["price"]),
            "firstRoundId": first, "nRoundsWithVotes": len(vote_rounds),
            **{f"first_{lab}": x for lab, x in t_first.items()},
            "first_other": sum(v["numTokens"] for v in votes_by_req_round.get((k, first), [])) / WAD - sum(t_first.values()),
            **{f"res_{lab}": x for lab, x in t_res.items()},
            "res_other": total / WAD - sum(t_res.values()),
        })

    def write_csv(path, rows_):
        if not rows_:
            print("no rows for", path)
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_[0].keys()))
            w.writeheader()
            w.writerows(rows_)
        print("wrote", path, len(rows_))

    json.dump({str(k): v for k, v in rounds_cache.items()}, open(rounds_path, "w"))
    write_csv(os.path.join(DATA, "requests_summary.csv"), req_rows)
    write_csv(os.path.join(DATA, "votes_long.csv"), vote_rows)
    write_csv(os.path.join(DATA, "first_round_tallies.csv"), first_rows)
    json.dump({"revealed_votes_all_rounds": len(by_event["VoteRevealed"]), "revealed_votes_resolving_rounds": len(vote_rows)},
              open(os.path.join(DATA, "vote_counts.json"), "w"), indent=1)

    roll_rows = [{"event": r["event"], "block": r["blockNumber"], "identifier": r["identifier"], "time": r["time"],
                  "rollCount": r["rollCount"], "text": ancillary_to_text(r["ancillaryData"])[:120].replace("\n", " "),
                  "ancKey": anc_key(r["ancillaryData"])}
                 for r in by_event["RequestRolled"] + by_event["RequestDeleted"]]
    roll_rows.sort(key=lambda r: r["block"])
    write_csv(os.path.join(DATA, "rolls.csv"), roll_rows)
    if "--tables-only" in sys.argv:
        return

    # ---- current stakes: every address that ever staked, read voterStakes() now
    voters = set(r["voter"] for r in by_event["Staked"])
    last_known = {}
    for r in rows:
        if r["event"] in ("Staked", "RequestedUnstake", "ExecutedUnstake"):
            last_known[r["voter"]] = r["voterStake"]
        elif r["event"] == "VoterSlashApplied":
            last_known[r["voter"]] = r["postStake"]
    delegate_of = {}
    for r in by_event["DelegateSet"]:
        delegate_of[r["delegator"]] = r["delegate"]
    print("distinct stakers ever:", len(voters), "; with nonzero last-known stake:",
          sum(1 for v in voters if last_known.get(v, 0) > 0))
    cur = {}
    cap = int(os.environ.get("MAX_VOTER_CALLS", "100000"))  # MAX_VOTER_CALLS=20 for a dry run
    min_call = int(float(os.environ.get("MIN_STAKE_FOR_CALL_UMA", "1000"))) * WAD  # below this, trust the events
    ncalls = 0
    for i, v in enumerate(sorted(voters, key=lambda a: -last_known.get(a, 0))):
        if (last_known.get(v, 0) < min_call and i > 400) or i >= cap:
            cur[v] = {"stake": last_known.get(v, 0), "delegate": delegate_of.get(v, "")}
            continue
        ncalls += 1
        try:
            vs = read_voter(rpc, v)
            cur[v] = {"stake": vs["stake"], "pendingUnstake": vs["pendingUnstake"], "unappliedSlash": vs["unappliedSlash"],
                      "delegate": vs["delegate"] if int(vs["delegate"], 16) else ""}
        except Exception as e:
            cur[v] = {"stake": last_known.get(v, 0), "delegate": delegate_of.get(v, ""), "err": str(e)[:60]}
    total_now = sum(c["stake"] for c in cur.values())
    chain_total = read_round  # placeholder to keep linters quiet
    from abi_min import decode_data, encode_call
    chain_cum = decode_data(["uint128"], rpc.eth_call(VOTING_V2, encode_call("cumulativeStake()")))[0]
    print(f"sum of voter stakes now {total_now/WAD:,.0f} vs cumulativeStake() {chain_cum/WAD:,.0f}")

    voter_rows = []
    for v, c in sorted(cur.items(), key=lambda kv: -kv[1]["stake"]):
        voter_rows.append({"voter": v, "stake": c["stake"] / WAD, "shareOfCumulative": c["stake"] / chain_cum,
                           "pendingUnstake": c.get("pendingUnstake", 0) / WAD,
                           "unappliedSlash": c.get("unappliedSlash", 0) / WAD, "delegate": c.get("delegate", "")})
    write_csv(os.path.join(DATA, "voters_current.csv"), voter_rows)

    per_delegate = defaultdict(float)
    for r in voter_rows:
        if r["delegate"]:
            per_delegate[r["delegate"]] += r["stake"]
    del_rows = [{"delegate": d, "stakeControlled": s, "shareOfCumulative": s * WAD / chain_cum}
                for d, s in sorted(per_delegate.items(), key=lambda kv: -kv[1])]
    write_csv(os.path.join(DATA, "delegates_current.csv"), del_rows)

    shares = [r["shareOfCumulative"] for r in voter_rows]
    conc = {
        "cumulativeStake": chain_cum / WAD,
        "top1": shares[0] if shares else None,
        "top2": sum(shares[:2]), "top3": sum(shares[:3]), "top5": sum(shares[:5]), "top10": sum(shares[:10]),
        "nStakersNonzero": sum(1 for s in shares if s > 0),
        "stallThreshold_1_minus_spat": 0.35,
        "smallest_k_reaching_35pct": next((k for k in range(1, len(shares) + 1) if sum(shares[:k]) >= 0.35), None),
        "smallest_k_reaching_65pct": next((k for k in range(1, len(shares) + 1) if sum(shares[:k]) >= 0.65), None),
        "delegates_top5": del_rows[:5],
    }
    json.dump(conc, open(os.path.join(DATA, "concentration.json"), "w"), indent=1)
    print(json.dumps(conc, indent=1))


if __name__ == "__main__":
    main()
