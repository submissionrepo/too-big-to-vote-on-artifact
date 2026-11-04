"""Tally settlement R_mu replayed over every Polymarket vote that decided a payout (no market prices needed).

Only votes that decide a payout enter (payout_votes.py): a question's first dispute is voted on too, but the adapter
has already reset the question, so that vote only settles the dispute's bonds.

R_mu (Definition 1 of the paper): a disputed question is settled on the tally of its first DVM round, whether or not
the DVM resolves the request in that round. If the modal answer of that round is "too early", the question is asked
again, as today. Otherwise Yes is paid rho(f) and No 1 - rho(f), where f is the share of the votes cast for Yes, a vote
for one half counting half, and rho(f) = clip((f - mu)/(1 - 2 mu), 0, 1). A vote for "too early" counts against Yes:
a Polymarket question pays No unless Yes is established. mu = 0 is the proportional rule of Freeman, Lahaie and
Pennock (AAAI 2017).

The deployed rule pays the DVM's answer (Yes 1, No 0, one half 1/2) and asks again on "too early".

Outputs data/ramp_replay.json:
  - by mu: how many Polymarket resolutions R_mu pays differently from the deployed rule (all, 65% era), how the two
    rules disagree on asking again, the winner's payout on contested Yes/No resolutions (median, p10), the largest
    shift a tenth of the supply can cause, 0.1/(1 - 2 mu);
  - single-voter-pivotal Yes/No resolutions: how much the largest supporter moves the winner's payout under R_mu;
  - coalitions the size of today's largest staker and of the four largest, switching from the winner to the other
    side of each contested Yes/No resolution: what the deployed rule does (roll or flip) and how far R_mu moves the
    winner's payout; and switching from the winner to "too early" instead: in how many R_mu asks the question again
    that it would have paid as cast (the one lever for delay the rule keeps);
  - March 2025 as cast and without the three wallets;
  - the security condition OI <= delta (1 - 2 mu) V for the contested markets of capture_economics_points.csv: the
    delta each market needs, and the markets above the cap that the DVM's own penalty lambda = 0.1% would set; and
    the same condition applied to the summed open interest of the contested markets settled in one round, since a
    coalition's stake moves all of them and loses its value once.
"""
import csv
import json
import os
import statistics as st

import payout_votes
from reqkey import req_key

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SPAT_CHANGE_BLOCK = 22309220
MUS = (0.0, 0.10, 0.15, 0.20, 0.25, 0.30)
LAMBDA = 0.001          # the DVM's penalty per token on a resolved request
ANSWERS = ("p1", "p2", "p3", "p4")


def rho(f, mu):
    return min(1.0, max(0.0, (f - mu) / (1 - 2 * mu)))


def load(name):
    return list(csv.DictReader(open(os.path.join(DATA, name), encoding="utf-8")))


def today_yes(price):
    """The deployed rule's payout to a Yes share, or None when the question is asked again (or is not Yes/No)."""
    return {"p2": 1.0, "p1": 0.0, "p3": 0.5}.get(price)


def ramp_yes(t, mu):
    """R_mu's payout to a Yes share from a tally {answer: tokens}, or None when the question is asked again."""
    cast = sum(t.values())
    if cast <= 0:
        return None
    mode = max(t, key=t.get)
    if mode == "p4":
        return None
    return rho((t.get("p2", 0.0) + 0.5 * t.get("p3", 0.0)) / cast, mu)


def winner_pay(t, mu, winner):
    y = ramp_yes(t, mu)
    if y is None:
        return None
    return y if winner == "p2" else 1 - y


def first_tally(row):
    t = {p: float(row[f"first_{p}"]) for p in ANSWERS}
    t["other"] = max(0.0, float(row["first_other"]))
    return t


def q(xs, a):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(a * len(xs)))] if xs else None


def march_hf():
    """Honest support for Yes in the payout-deciding March request (index 827): Yes without the three wallets, as a
    share of the staked supply."""
    port = json.load(open(os.path.join(DATA, "dvm_port_results.json")))
    r = port["827"]
    yes = int(r["tally_wei"]["1000000000000000000"])
    return (yes - r["counterfactuals"]["whale_stake_actual"]) / port["S_wei"]


HF_MARCH = march_hf()


def main():
    reqs = {req_key(r): r for r in load("requests_summary.csv")}
    first = {req_key(r): r for r in load("first_round_tallies.csv")}
    cont = {req_key(c): c for c in load("contested_requests.csv")}
    roles = payout_votes.roles(list(reqs.values()))
    pm = [k for k, r in reqs.items() if r["isPolymarket"] == "True" and payout_votes.is_payout(r, roles)]
    eraB = {k for k in pm if int(reqs[k]["resolvedBlock"]) >= SPAT_CHANGE_BLOCK}
    sided = [k for k in pm if k in cont and reqs[k]["resolvedPrice"] in ("p1", "p2")]
    out = {"n_polymarket": len(pm), "n_polymarket_eraB": len(eraB), "n_contested_sided": len(sided),
           "n_rolled_polymarket": sum(1 for k in pm if first[k]["firstRoundId"] != first[k]["roundId"]),
           "by_mu": {}}

    # where the two rules disagree on asking again does not depend on mu
    both, ramp_only, today_only, neither = [], 0, 0, 0
    for k in pm:
        ty, ry = today_yes(reqs[k]["resolvedPrice"]), ramp_yes(first_tally(first[k]), 0.2)
        if ty is None and ry is None:
            neither += 1
        elif ry is None:
            ramp_only += 1
        elif ty is None:
            today_only += 1
        else:
            both.append(k)
    out["ask_again"] = {"both_rules": neither, "ramp_only": ramp_only, "deployed_only": today_only, "both_pay": len(both)}

    yn = [k for k in both if reqs[k]["resolvedPrice"] in ("p1", "p2")]
    half = [k for k in both if reqs[k]["resolvedPrice"] == "p3"]
    for mu in MUS:
        dev = {k: abs(ramp_yes(first_tally(first[k]), mu) - today_yes(reqs[k]["resolvedPrice"])) for k in both}
        diff = [k for k in both if dev[k] > 1e-9]
        cut = sorted(dev[k] for k in yn if dev[k] > 1e-9)          # what the winner of a Yes/No question loses
        hdev = sorted(dev[k] for k in half if dev[k] > 1e-9)
        pays = [winner_pay(first_tally(first[k]), mu, reqs[k]["resolvedPrice"]) for k in sided]
        pays_ok = sorted(p for p in pays if p is not None)
        out["by_mu"][str(mu)] = {
            "pays_differently_all": len(diff) / len(pm), "pays_differently_all_count": len(diff),
            "pays_differently_eraB": sum(1 for k in diff if k in eraB) / len(eraB),
            "pays_differently_eraB_count": sum(1 for k in diff if k in eraB),
            "yes_no_both_pay": len(yn), "yes_no_both_pay_eraB": sum(1 for k in yn if k in eraB),
            "yes_no_below_full": len(cut), "yes_no_below_full_eraB": sum(1 for k in yn if k in eraB and dev[k] > 1e-9),
            "yes_no_haircut_median": st.median(cut) if cut else 0.0, "yes_no_haircut_max": cut[-1] if cut else 0.0,
            "half_both_pay": len(half), "half_differ": len(hdev),
            "half_dev_median": st.median(hdev) if hdev else 0.0, "half_dev_max": hdev[-1] if hdev else 0.0,
            "contested_sided_paid": len(pays_ok), "contested_sided_asked_again": len(pays) - len(pays_ok),
            "winner_payout_median": st.median(pays_ok), "winner_payout_p10": pays_ok[len(pays_ok) // 10],
            "winner_full_dollar": sum(1 for p in pays_ok if p >= 1 - 1e-12),
            "max_shift_per_10pct_stake": 0.1 / (1 - 2 * mu),
            "one_dollar_capture_march": 1 - mu - HF_MARCH,
        }

    # single-voter-pivotal Yes/No resolutions: the largest supporter of the winner abstains in the first round
    piv = []
    for k in pm:
        c = cont.get(k)
        r = reqs[k]
        if not c or c["kSupportersWhoseRemovalRolls"] != "1" or r["resolvedPrice"] not in ("p1", "p2"):
            continue
        t = first_tally(first[k])
        s = float(c["top1SupporterShareOfStaked"]) * float(r["cumulativeStakeAtRound"])
        approx = first[k]["firstRoundId"] != first[k]["roundId"]
        if t[r["resolvedPrice"]] < s:
            piv.append({"key": k, "skipped": True})
            continue
        t2 = dict(t)
        t2[r["resolvedPrice"]] -= s
        row = {"key": k, "skipped": False, "approx_first_round": approx}
        for mu in MUS:
            a, b = winner_pay(t, mu, r["resolvedPrice"]), winner_pay(t2, mu, r["resolvedPrice"])
            row[str(mu)] = None if a is None or b is None else a - b
        piv.append(row)
    n_piv_all = sum(1 for k in pm if k in cont and cont[k]["kSupportersWhoseRemovalRolls"] == "1")
    used = [p for p in piv if not p["skipped"]]
    out["pivotal"] = {"n_polymarket_pivotal": n_piv_all,
                      "n_yes_no": len(piv), "n_used": len(used), "n_skipped": len(piv) - len(used),
                      "n_first_round_differs": sum(1 for p in used if p["approx_first_round"]),
                      "winner_counts": {w: sum(1 for k in pm if k in cont and cont[k]["kSupportersWhoseRemovalRolls"] == "1"
                                               and reqs[k]["resolvedPrice"] == w) for w in ANSWERS}}
    for mu in MUS:
        sh = [p[str(mu)] for p in used if p[str(mu)] is not None]
        out["pivotal"][str(mu)] = {"n": len(sh), "median_shift": st.median(sh) if sh else None,
                                   "max_shift": max(sh) if sh else None,
                                   "n_asked_again_either_way": sum(1 for p in used if p[str(mu)] is None)}

    # coalitions the size of today's largest staker(s) switch from the winner to the other side
    tal = {req_key(x): x for x in load("contested_answer_tallies.csv")}
    now = sorted((float(v["shareOfCumulative"]) for v in load("voters_current.csv")), reverse=True)
    top1, top4 = now[0], sum(now[:4])
    out["stakes_now"] = {"top1": top1, "top4": top4}
    coal = {}
    for name, alpha in (("top1", top1), ("top4", top4)):
        rows = []
        for k in sided:
            r, t = reqs[k], first_tally(first[k])
            w = r["resolvedPrice"]
            l = "p1" if w == "p2" else "p2"
            S = float(r["cumulativeStakeAtRound"])
            a = min(alpha * S, t[w])                 # the coalition can only move stake that voted for the winner
            t2 = dict(t)
            t2[w] -= a
            t2[l] += a
            theta = 0.5 if int(r["resolvedBlock"]) < SPAT_CHANGE_BLOCK else 0.65
            ws, ls = float(tal[k][w]), float(tal[k][l])   # resolving round, shares of the staked supply
            # deployed rule on the resolving round's staked shares: winner loses alpha, the other side gains it
            dep = "flip" if ls + alpha > theta else ("roll" if ws - alpha <= theta else "stands")
            a0, b0 = winner_pay(t, 0.2, w), winner_pay(t2, 0.2, w)
            t3 = dict(t)                             # the same stake switches to "too early" instead
            t3[w] -= a
            t3["p4"] += a
            rows.append({"eraB": k in eraB, "deployed": dep,
                         "shift_mu_0.2": None if a0 is None or b0 is None else a0 - b0,
                         "ask_again": a0 is not None and ramp_yes(t3, 0.2) is None})
        res = {}
        for era, sel in (("all", lambda x: True), ("eraB", lambda x: x["eraB"])):
            sub = [x for x in rows if sel(x)]
            sh = [x["shift_mu_0.2"] for x in sub if x["shift_mu_0.2"] is not None]
            res[era] = {"n": len(sub), "deployed_roll": sum(1 for x in sub if x["deployed"] == "roll"),
                        "deployed_flip": sum(1 for x in sub if x["deployed"] == "flip"),
                        "ramp_n": len(sh), "ramp_median_shift": st.median(sh) if sh else None,
                        "ramp_max_shift": max(sh) if sh else None,
                        "ramp_n_shift_ge_quarter": sum(1 for s in sh if s >= 0.25),
                        "ramp_ask_again": sum(1 for x in sub if x["ask_again"])}
        coal[name] = {"alpha": alpha, **res}
    out["coalition_switch"] = coal

    # March 2025 (round 10085, the payout-deciding second request, index 827): tallies in UMA from the port
    port = json.load(open(os.path.join(DATA, "dvm_port_results.json")))
    r828 = port["827"]
    lab = {"-57896044618658097711785492504343953926634992332820282019728792003956564819968": "p4", "0": "p1",
           "1000000000000000000": "p2", "500000000000000000": "p3"}
    t = {lab[p]: int(v) / 1e18 for p, v in r828["tally_wei"].items()}
    whale = r828["counterfactuals"]["whale_stake_actual"] / 1e18
    t_without = dict(t)
    t_without["p2"] -= whale
    out["march"] = {"tally": t, "f_with": (t["p2"] + 0.5 * t.get("p3", 0)) / sum(t.values()),
                    "mode_without": max(t_without, key=t_without.get),
                    "f_without": (t_without["p2"] + 0.5 * t_without.get("p3", 0)) / sum(t_without.values()),
                    **{f"mu={mu}": {"with": ramp_yes(t, mu), "without": ramp_yes(t_without, mu)} for mu in MUS}}

    # security condition under R_mu: OI <= delta (1 - 2 mu) V, V the market value of the whole staked supply
    pts = load("capture_economics_points.csv")
    sec = {}
    for mu in MUS:
        need = sorted(float(p["oi"]) / ((1 - 2 * mu) * float(p["S"]) * float(p["uma_price"])) for p in pts)
        sec[str(mu)] = {"n": len(need), "delta_needed_median": st.median(need),
                        "delta_needed_quantiles": {a: q(need, a) for a in (0.1, 0.25, 0.5, 0.75, 0.9)},
                        **{f"n_need_above_{d}": sum(1 for x in need if x > d) for d in (0.05, 0.1, 0.25, 1.0)},
                        "n_above_penalty_cap": sum(1 for x in need if x > LAMBDA)}
    # one round, several markets: the condition on the summed open interest of a round's contested markets
    rounds = {}
    for p in pts:
        r = rounds.setdefault(p["roundId"], {"oi": 0.0, "V": float(p["S"]) * float(p["uma_price"]), "n": 0})
        r["oi"] += float(p["oi"])
        r["n"] += 1
    for mu in MUS:
        need_r = {k: r["oi"] / ((1 - 2 * mu) * r["V"]) for k, r in rounds.items()}
        sec[str(mu)]["per_round"] = {
            "n_rounds": len(rounds), "n_rounds_several": sum(1 for r in rounds.values() if r["n"] > 1),
            **{f"n_market_rounds_in_rounds_above_{d}": sum(rounds[k]["n"] for k, x in need_r.items() if x > d)
               for d in (LAMBDA, 0.05, 0.1, 0.25, 1.0)},
            **{f"n_rounds_above_{d}": sum(1 for x in need_r.values() if x > d) for d in (LAMBDA, 0.05, 0.1, 0.25, 1.0)}}
    out["security_condition"] = sec
    out["lambda"] = LAMBDA
    json.dump(out, open(os.path.join(DATA, "ramp_replay.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("security_condition",)}, indent=1))


if __name__ == "__main__":
    main()
