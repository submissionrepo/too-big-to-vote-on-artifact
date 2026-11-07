"""Derive every number quoted in paper.tex from the probe outputs and write numbers.tex (LaTeX macros) + numbers.json.

Sources (all under research_ideas/probes/oracle_capture/data/):
  requests_summary.csv, contested_requests.csv, rolls.csv, analysis.json, concentration.json, voters_current.csv,
  dvm_port_results.json, redemptions_summary.json, capture_probe_results.json, tally_rules_probe_results.json,
  fallback_probe_results.json, replay_fallback_summary.json, pm_prices_YES.csv, uma_usd_daily_coinbase.csv,
  quick_tally_2025-03-20_000000_2025-03-28_000000.json
Rerun after any data refresh; paper.tex only ever quotes macros from numbers.tex.
"""
from datetime import datetime, timezone
import csv
import datetime as dt
import sys
import json
import math
import os
import re
from fractions import Fraction as Fr

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "probes", "oracle_capture", "data"))
sys.path.insert(0, os.path.dirname(DATA))
import payout_votes  # noqa: E402  which Polymarket votes decide a payout (the first dispute's only settles bonds)
SPAT_CHANGE_BLOCK = 22309220
WAD = 10**18

M = {}  # macro name -> string


def put(name, value):
    assert re.fullmatch(r"[A-Za-z]+", name), name
    M[name] = str(value)


def thousands(x):
    return f"{int(round(x)):,}"


def pct(x, d=1):
    return f"{100 * x:.{d}f}"


def load_csv(name):
    return list(csv.DictReader(open(os.path.join(DATA, name), encoding="utf-8")))


def main():
    reqs = load_csv("requests_summary.csv")
    cont = load_csv("contested_requests.csv")
    rolls = load_csv("rolls.csv")
    analysis = json.load(open(os.path.join(DATA, "analysis.json")))
    conc = json.load(open(os.path.join(DATA, "concentration.json")))
    port = json.load(open(os.path.join(DATA, "dvm_port_results.json")))
    red = json.load(open(os.path.join(DATA, "redemptions_summary.json")))
    cap = json.load(open(os.path.join(DATA, "capture_probe_results.json")))
    tally = json.load(open(os.path.join(DATA, "tally_rules_probe_results.json")))
    fb = json.load(open(os.path.join(DATA, "fallback_probe_results.json")))
    replay = json.load(open(os.path.join(DATA, "replay_fallback_summary.json")))

    # ---- census
    era_a = [r for r in reqs if int(r["resolvedBlock"]) < SPAT_CHANGE_BLOCK]
    era_b = [r for r in reqs if int(r["resolvedBlock"]) >= SPAT_CHANGE_BLOCK]
    put("nResolved", thousands(len(reqs)))
    put("nVotes", thousands(sum(1 for _ in open(os.path.join(DATA, "votes_long.csv"), encoding="utf-8")) - 1)
        if os.path.exists(os.path.join(DATA, "votes_long.csv")) else thousands(json.load(open(os.path.join(DATA, "vote_counts.json")))["revealed_votes_resolving_rounds"]))
    vcount = json.load(open(os.path.join(DATA, "vote_counts.json")))
    put("nVotesAll", thousands(vcount["revealed_votes_all_rounds"]))
    put("nPolymarket", thousands(sum(1 for r in reqs if r["isPolymarket"] == "True")))
    put("nGovernance", thousands(sum(1 for r in reqs if r["isGovernance"] == "True")))
    put("nEraA", thousands(len(era_a)))
    put("nEraB", thousands(len(era_b)))
    put("nEraAPolymarket", thousands(sum(1 for r in era_a if r["isPolymarket"] == "True")))
    put("nEraBPolymarket", thousands(sum(1 for r in era_b if r["isPolymarket"] == "True")))
    put("nContested", str(len(cont)))
    put("nContestedEraA", str(analysis["spat50"]["n_contested"]))
    put("nContestedEraB", str(analysis["spat65"]["n_contested"]))
    put("nPivotal", str(analysis["n_contested_single_voter_pivotal"]))
    put("nPivotalEraA", str(analysis["spat50"]["n_contested_single_voter_pivotal"]))
    put("nPivotalEraB", str(analysis["spat65"]["n_contested_single_voter_pivotal"]))
    put("nKleThreeEraB", str(analysis["spat65"]["n_contested_k_le_3"]))
    put("nTooEarlyWinsContested", str(analysis["spat50"]["n_contested_winner_p4"] + analysis["spat65"]["n_contested_winner_p4"]))
    qa, qb = analysis["spat50"]["modeShareOfStaked_quantiles"], analysis["spat65"]["modeShareOfStaked_quantiles"]
    put("winMinEraA", f"{qa['min']:.3f}")
    put("winMinEraB", f"{qb['min']:.3f}")
    put("winMedEraA", f"{qa['p50']:.3f}")
    put("winMedEraB", f"{qb['p50']:.3f}")
    put("winPTenEraA", f"{qa['p10']:.3f}")
    put("winPTenEraB", f"{qb['p10']:.3f}")
    put("nEraAUnderSixtyFive", str(analysis["spat50"]["n_mode_share_le_65pct"]))
    wb = [float(r["modeShareOfStaked"]) for r in era_b if r["modeShareOfStaked"]]
    put("nEraBWithinTwo", str(sum(1 for x in wb if 0.65 < x <= 0.67)))
    put("nEraBWithinTen", str(sum(1 for x in wb if 0.65 < x <= 0.75)))
    piv = [c for c in cont if c["kSupportersWhoseRemovalRolls"] == "1"]
    put("nPivotalYesNo", str(sum(1 for c in piv if c["winner"] in ("p1", "p2"))))
    put("nPivotalTooEarly", str(sum(1 for c in piv if c["winner"] == "p4")))
    put("partMedEraA", f"{analysis['spat50']['participation_median']:.3f}")
    put("partMedEraB", f"{analysis['spat65']['participation_median']:.3f}")
    pi_med = analysis["spat65"]["participation_median"]
    put("partMedEraBPct", f"{100 * pi_med:.1f}")
    assert 1 / pi_med - 1 < 0.04  # the text: honest abstention at the median raises the bounds by less than four percent
    nv_a = sorted(int(r["nVoters"]) for r in era_a)
    nv_b = sorted(int(r["nVoters"]) for r in era_b)
    put("votersMedEraA", str(nv_a[len(nv_a) // 2]))
    put("votersMedEraB", str(nv_b[len(nv_b) // 2]))
    # rolls
    rolled_a = {(r["identifier"], r["time"], r["ancKey"]) for r in rolls if r["event"] == "RequestRolled" and int(r["block"]) < SPAT_CHANGE_BLOCK}
    rolled_b = {(r["identifier"], r["time"], r["ancKey"]) for r in rolls if r["event"] == "RequestRolled" and int(r["block"]) >= SPAT_CHANGE_BLOCK}
    rep_a = sum(1 for r in rolls if r["event"] == "RequestRolled" and int(r["block"]) < SPAT_CHANGE_BLOCK and int(r["rollCount"]) >= 2)
    # counted by request: a request that rolls three times has two events with rollCount >= 2
    rep_b = len({(r["identifier"], r["time"], r["ancKey"]) for r in rolls if r["event"] == "RequestRolled" and int(r["block"]) >= SPAT_CHANGE_BLOCK and int(r["rollCount"]) >= 2})
    put("nRolledEraA", str(len(rolled_a)))
    put("nRolledEraB", str(len(rolled_b)))
    put("nRepeatRollsEraA", str(rep_a))
    put("nRepeatRollsEraB", str(rep_b))
    put("nDeleted", str(sum(1 for r in rolls if r["event"] == "RequestDeleted")))
    # cross-check with the SPAT-65 proposal (6 of 291 requests in 2025): resolutions in 2025 before the change
    B2025 = 21525891  # first block of 2025-01-01 UTC (state_reads.block_at)
    y25 = [r for r in era_a if int(r["resolvedBlock"]) >= B2025]
    put("nTwentyTwentyFiveBeforeChange", str(len(y25)))
    put("nTwentyTwentyFiveUnderSixtyFive", str(sum(1 for r in y25 if float(r["modeShareOfStaked"]) <= 0.65)))
    # contested distributions
    mino = sorted(float(c["minorityShareOfVotes"]) for c in cont)
    slack = sorted(float(c["slackShareOfStaked"]) for c in cont if c["slackShareOfStaked"])
    top1 = sorted(float(c["top1SupporterShareOfStaked"]) for c in cont if c["top1SupporterShareOfStaked"])
    put("minorityPTwentyFive", f"{mino[len(mino)//4]:.3f}")
    put("minorityMedian", f"{mino[len(mino)//2]:.3f}")
    put("minorityPSeventyFive", f"{mino[3*len(mino)//4]:.3f}")
    put("slackPTen", f"{slack[len(slack)//10]:.3f}")
    put("slackMedian", f"{slack[len(slack)//2]:.3f}")
    put("topSupporterMedian", f"{top1[len(top1)//2]:.3f}")
    put("topSupporterMax", f"{top1[-1]:.3f}")
    # concentration now
    put("stakeNow", thousands(conc["cumulativeStake"]))
    put("topOnePct", pct(conc["top1"]))
    put("topFourPct", pct(sum(float(r["shareOfCumulative"]) for r in load_csv("voters_current.csv")[:4]), 2))
    put("topTenPct", pct(conc["top10"]))
    put("kStall", str(conc["smallest_k_reaching_35pct"]))
    put("kSixtyFive", str(conc["smallest_k_reaching_65pct"]))
    put("maxSingleEver", pct(analysis["stall_top1_max"]))

    # ---- votes that decide a payout (payout_votes.py; checked against the chain for every contested match)
    roles = payout_votes.roles(reqs)
    agree, nchk = payout_votes.check()
    assert agree == nchk
    put("nRoleChecked", str(nchk))
    # requests on the managed oracle, whose settle() only a resolver role may call (contract 0x2c0367...)
    managed = [r for r in load_csv("request_roles.csv") if r["oo"].lower().startswith("0x2c0367")]
    put("nManagedPayout", str(sum(1 for r in managed if r["role"] == "payout")))
    put("managedSince", datetime.fromtimestamp(min(int(r["requestTime"]) for r in managed), timezone.utc).strftime("%B %Y"))
    pmreq = [r for r in reqs if r["isPolymarket"] == "True"]
    payr = [r for r in pmreq if payout_votes.is_payout(r, roles)]
    put("nPayoutVotes", thousands(len(payr)))
    put("nBondOnlyVotes", thousands(len(pmreq) - len(payr)))
    put("nPayoutVotesEraB", thousands(sum(1 for r in payr if int(r["resolvedBlock"]) >= SPAT_CHANGE_BLOCK)))
    put("payoutVotesPct", pct(len(payr) / len(pmreq), 0))
    qk = {}
    for r in pmreq:
        qk.setdefault(payout_votes.question_key(r["text"]), []).append(r)
    put("nPmQuestionsVoted", thousands(len(qk)))
    put("nPmQuestionsOneVote", thousands(sum(1 for g in qk.values() if len(g) == 1)))
    pcont = [c for c in cont if c["isPolymarket"] == "True" and payout_votes.is_payout(c, roles)]
    put("nContestedPm", str(sum(1 for c in cont if c["isPolymarket"] == "True")))
    put("nPayoutContested", str(len(pcont)))
    put("nPayoutContestedEraA", str(sum(1 for c in pcont if int(c["resolvedBlock"]) < SPAT_CHANGE_BLOCK)))
    put("nPayoutContestedEraB", str(sum(1 for c in pcont if int(c["resolvedBlock"]) >= SPAT_CHANGE_BLOCK)))
    ppiv = [c for c in pcont if c["kSupportersWhoseRemovalRolls"] == "1"]
    put("nPayoutPivotal", str(len(ppiv)))
    put("nPayoutPivotalEraA", str(sum(1 for c in ppiv if int(c["resolvedBlock"]) < SPAT_CHANGE_BLOCK)))
    put("nPayoutPivotalEraB", str(sum(1 for c in ppiv if int(c["resolvedBlock"]) >= SPAT_CHANGE_BLOCK)))
    put("nPayoutPivotalYesNo", str(sum(1 for c in ppiv if c["winner"] in ("p1", "p2"))))
    put("nPayoutPivotalTooEarly", str(sum(1 for c in ppiv if c["winner"] == "p4")))
    pb = [c for c in pcont if int(c["resolvedBlock"]) >= SPAT_CHANGE_BLOCK]
    put("nPayoutKleThreeEraB", str(sum(1 for c in pb if c["kSupportersWhoseRemovalRolls"] and int(c["kSupportersWhoseRemovalRolls"]) <= 3)))
    assert M["nPayoutKleThreeEraB"] == str(len(pb))  # the text: "in all ... since the change ... three supporters or fewer"
    put("nPayoutTooEarlyWins", str(sum(1 for c in pcont if c["winner"] == "p4")))
    pmino = sorted(float(c["minorityShareOfVotes"]) for c in pcont)
    pslack = sorted(float(c["slackShareOfStaked"]) for c in pcont if c["slackShareOfStaked"])
    ptop1 = sorted(float(c["top1SupporterShareOfStaked"]) for c in pcont if c["top1SupporterShareOfStaked"])
    put("payMinorityMedian", f"{pmino[len(pmino)//2]:.3f}")
    put("paySlackMedian", f"{pslack[len(pslack)//2]:.3f}")
    put("paySlackPTen", f"{pslack[len(pslack)//10]:.3f}")
    put("payTopSupporterMedian", f"{ptop1[len(ptop1)//2]:.3f}")
    put("payTopSupporterMax", f"{ptop1[-1]:.3f}")
    nonpm = [r for r in reqs if r["isPolymarket"] != "True"]
    ident = lambda r: bytes.fromhex(r["identifier"][2:]).rstrip(b"\0").decode("ascii", "replace")
    put("nNonPm", str(len(nonpm)))
    put("nNonPmGov", str(sum(1 for r in nonpm if r["isGovernance"] == "True")))
    put("nNonPmAcross", str(sum(1 for r in nonpm if r["isGovernance"] != "True" and ident(r) == "ACROSS-V2")))
    put("nNonPmYesNo", str(sum(1 for r in nonpm if r["isGovernance"] != "True" and ident(r) == "YES_OR_NO_QUERY")))
    put("nNonPmAssert", str(sum(1 for r in nonpm if r["isGovernance"] != "True" and ident(r) == "ASSERT_TRUTH")))
    put("nNonPmContested", str(sum(1 for c in cont if c["isPolymarket"] != "True")))

    # ---- March 2025
    S = port["S_wei"]
    r828 = port["827"]  # the payout-deciding request; port["828"] is the first dispute's, which settled only the bonds
    cf = r828["counterfactuals"]
    tallyw = r828["tally_wei"]
    yes = int(tallyw["1000000000000000000"])
    te = int(tallyw[str(-(1 << 255))])
    no = int(tallyw.get("0", 0))
    total = r828["total_votes_wei"]
    put("marchStake", thousands(S / WAD))
    put("marchYes", thousands(yes / WAD))
    put("marchTooEarly", thousands(te / WAD))
    put("marchNo", thousands(no / WAD))
    put("marchAbstain", thousands((S - total) / WAD))
    put("marchVoters", str(r828["n_voters"]))
    put("marchYesPct", pct(yes / S, 1))
    put("marchYesVotesPct", pct(yes / total, 1))
    put("marchYesVotesBps", str(int(yes * 10000 // total)))
    put("marchTooEarlyPct", pct(te / S, 1))
    put("marchAbstainPct", pct((S - total) / S, 1))
    put("marchParticipationPct", pct(total / S, 0))
    put("marchWhale", thousands(cf["whale_stake_actual"] / WAD))
    put("marchMargin", thousands(cf["margin_over_minAgreement"] / WAD))
    put("marchMarginPct", f"{100 * cf['margin_over_minAgreement'] / S:.2f}")
    hF = (yes - cf["whale_stake_actual"]) / S
    alpha = cf["whale_stake_actual"] / S
    put("marchHF", f"{100*hF:.2f}")
    put("marchAlpha", f"{100*alpha:.2f}")
    put("marchThetaMinusHF", f"{100*(0.5 - hF):.2f}")
    put("marchHT", f"{100*te/S:.2f}")
    put("marchYesMinusWhalePct", pct((yes - cf["whale_stake_actual"]) / S, 1))
    put("marchNeeded", thousands(cf["min_whale_stake_to_resolve_yes_50pct"] / WAD))
    put("marchNeededSixtyFive", thousands(cf["min_whale_stake_to_resolve_yes_65pct"] / WAD))
    put("marchShortSixtyFive", thousands(cf["whale_short_under_65pct"] / WAD))
    put("marchNeededVotesCast", thousands(cf["min_whale_stake_votescast_50pct"] / WAD))
    put("marchStallStakedFifty", thousands(cf["stall_coalition_staked_50pct"] / WAD))
    put("marchStallStakedSixtyFive", thousands(cf["stall_coalition_staked_65pct"] / WAD))
    put("marchStallVotesSixtyFive", thousands(cf["stall_coalition_votescast_65pct"] / WAD))
    put("marchPool", thousands(cf["totalSlashed_wei"] / WAD))
    put("marchWhaleGain", thousands(cf["whale_gain_wei"] / WAD))
    put("marchWhaleShareOfWinners", pct(cf["whale_stake_actual"] / yes, 1))
    # the first request of the round (index 828): created by the first dispute, detached from the market by the
    # adapter's reset, so its vote decided only that dispute's bonds
    r1 = port["828"]
    y1 = int(r1["tally_wei"]["1000000000000000000"])
    put("marchFirstYesPct", pct(y1 / S, 1))
    put("marchFirstMarginPct", f"{100 * r1['counterfactuals']['margin_over_minAgreement'] / S:.2f}")
    put("portEvents", str(r828["validation"]["events_found"]))
    put("portMatchedA", str(r1["validation"]["voters_matched"]))
    put("portMatchedB", str(port["827"]["validation"]["voters_matched"]))
    put("portMismatched", str(r1["validation"]["voters_mismatched"] + port["827"]["validation"]["voters_mismatched"]))
    # redemptions
    put("marchRedeemed", thousands(red["total_payout_usdc"]))
    put("marchRedeemedM", f"{red['total_payout_usdc']/1e6:.2f}")
    put("marchRedeemers", str(red["redeemers"]))
    put("marchRedemptions", thousands(red["hits"]))
    put("marchTopRedeemer", thousands(red["top_redeemers_usdc"][0][1]))
    put("marchTopFiveSharePct", pct(sum(v for _, v in red["top_redeemers_usdc"][:5]) / red["total_payout_usdc"]))
    put("marchUnredeemed", thousands(red["unredeemed_yes_shares_now"]))
    put("marchVolumeM", "7.08")
    # UMA price and stake value
    px = {r["date"]: float(r["close"]) for r in load_csv("uma_usd_daily_coinbase.csv")}
    p_mar = px["2025-03-24"]
    put("umaPriceMarch", f"{p_mar:.2f}")
    put("umaPriceNow", f"{px[max(px)]:.2f}")
    put("marchStakeUsdM", f"{S / WAD * p_mar / 1e6:.1f}")
    put("marchWhaleUsdM", f"{cf['whale_stake_actual'] / WAD * p_mar / 1e6:.1f}")
    put("stakeNowUsdM", f"{conc['cumulativeStake'] * px[max(px)] / 1e6:.1f}")
    # pre-dispute TWAP
    pts = [(int(r["ts"]), float(r["price"])) for r in load_csv("pm_prices_YES.csv")]
    first_req = 1742684664  # the payout-deciding request
    sel = [p for t, p in pts if first_req - 24 * 3600 <= t < first_req]
    put("marchTwap", f"{sum(sel)/len(sel):.2f}")
    # Yes purchases around the vote, from the data-api trade tape (march_trades.py)
    mt = json.load(open(os.path.join(DATA, "march_trades_summary.json")))
    pre, post = mt["request_to_last_reveal"], mt["last_reveal_to_end"]
    put("marchDisputeBuyShares", thousands(pre["shares"]))
    put("marchDisputeBuyCost", thousands(pre["cost"]))
    put("marchDisputeBuyWallets", str(pre["wallets"]))
    put("marchPostRevealShares", thousands(post["shares"]))
    put("marchPostRevealCost", thousands(post["cost"]))
    put("marchPostRevealWallets", str(post["wallets"]))
    first50 = post["ten_minute_steps"][:5]
    put("marchPostRevealLowCents", str(round(100 * min(s["min"] for s in first50))))
    put("marchPostRevealHighCents", str(round(100 * max(s["max"] for s in first50))))
    put("marchPostRevealMaxCents", str(round(100 * post["max_price"])))

    # ---- theory numbers
    e6 = cap["E6"]
    put("captureReqSixtyFiveMarch", f"{100*(0.65 - hF):.2f}")
    put("windowEmptyAt", f"{100*e6['window_empty_iff_hF_ge']['top4']:.2f}")
    put("topFourShareExact", f"{100*e6['top4_share']:.2f}")
    rc = tally["realistic_capture_pi096"]
    put("realizedCaptureVotes", f"{100*float(Fr(rc['closed_form_votes'])):.2f}")
    put("realizedCaptureStaked", f"{100*float(Fr(rc['closed_form_staked'])):.2f}")
    put("laplacianGridPoints", thousands(cap["E4"]["grid_points"]))
    # honest-electorate thresholds today (Theorem 4 and the window after it): block needs 1 - theta - hF, capture theta - hF
    top1_share = conc["top1"]
    top4_share = sum(float(r["shareOfCumulative"]) for r in load_csv("voters_current.csv")[:4])
    put("windowEmptyAtTopFour", f"{100*(0.5 - top4_share):.2f}")
    put("windowEmptyAtTopOne", f"{100*(0.5 - top1_share):.2f}")
    put("topOneBlockNeedsHF", f"{100*(1 - 0.65 - top1_share):.1f}")
    put("topOneCaptureNeedsHF", f"{100*(0.65 - top1_share):.1f}")
    pb_all = [r for r in payr if int(r["resolvedBlock"]) >= SPAT_CHANGE_BLOCK and r["modeShareOfStaked"]]
    put("nEraBBlockableByTopOne", str(sum(1 for r in pb_all if float(r["modeShareOfStaked"]) < 0.65 + top1_share)))
    put("nEraBContestedBlockableByTopOne", str(sum(1 for c in pb if float(c["winnerShareOfStaked"]) < 0.65 + top1_share)))
    # fallback table, trigger measured against votes cast (the rule the paper proposes)
    vc = fb["votes_cast"]
    for mu, key in (("Ten", "mu_1/10"), ("Fifteen", "mu_3/20"), ("Twenty", "mu_1/5"), ("TwentyFive", "mu_1/4"), ("Thirty", "mu_3/10")):
        row = vc[key]
        put(f"tapeAll{mu}", pct(row["trigger_all"]["rate"]))
        put(f"tapeEraA{mu}", pct(row["trigger_spat50"]["rate"]))
        put(f"tapeEraB{mu}", pct(row["trigger_spat65"]["rate"], 2))
        put(f"tapeEraBCount{mu}", str(row["trigger_spat65"]["paid_at_tape"]))
        put(f"tapeContested{mu}", str(row["contested_paid_at_tape"]["tape"]))
        put(f"tapePivotal{mu}", str(row["single_voter_pivotal_paid_at_tape"]["tape"]))
        put(f"tapeReq{mu}", f"{100*row['capture_req_march']:.2f}")
        put(f"tapeForceStakers{mu}", str(row["largest_stakers_to_force_tape_hF0"]))
    # staked trigger with 96% honest participation and hF = 0: 1 - (1 - mu)/pi (honest_electorate_probe.py)
    put("stakedTriggerForcePct", f"{100*(1 - 0.8/0.96):.1f}")
    # blocking stake at 96% honest participation, hF = 0 (honest_electorate_probe.py, exact grid): staked vs votes cast
    he = json.load(open(os.path.join(DATA, "honest_electorate_results.json")))
    put("stakedTriggerBlockPct", f"{100*float(Fr(he['pi=24/25 hF=0 rule=staked']['stall'])):.1f}")
    put("votesTriggerBlockPct", f"{100*float(Fr(he['pi=24/25 hF=0 rule=votes']['stall'])):.1f}")
    # replay, restricted to what the votes-cast trigger at mu = 0.2 moves (losing answers above 20% of the votes)
    rows = load_csv("replay_fallback.csv")
    moved = [r for r in rows if r.get("minorityShareOfVotes") and float(r["minorityShareOfVotes"]) > 0.2
             and payout_votes.is_payout(r, roles)]
    # a question disputed twice is voted on twice; the market is settled once, by its latest vote
    by_market = {}
    for r in moved:
        if r["status"] in ("ok", "no-prices"):
            c = r["conditionId"]
            if c not in by_market or int(r["requestTime"]) > int(by_market[c]["requestTime"]):
                by_market[c] = r
    ok = [r for r in by_market.values() if r["status"] == "ok"]
    sided = [r for r in ok if r["winner_side_price"] != ""]
    over = [r for r in sided if r["vote_overturned_market"] == "True"]
    put("replaySelected", str(len(moved)))
    put("replayUnmatched", str(sum(1 for r in moved if r["status"] not in ("ok", "no-prices"))))
    put("replayMarkets", str(len(by_market)))
    put("replayPrices", str(len(ok)))
    put("replayTooEarly", str(sum(1 for r in ok if r["resolvedPrice"] == "p4")))
    put("replaySided", str(len(sided)))
    put("replayOverturned", str(len(over)))
    if sided:
        put("replayOverturnedPct", pct(len(over) / len(sided), 0))
        ws = sorted(float(r["winner_side_price"]) for r in sided)
        put("replayWinnerPTen", f"{ws[len(ws)//10]:.2f}")
        put("replayWinnerMedian", f"{ws[len(ws)//2]:.2f}")
        put("replayWinnerPNinety", f"{ws[int(0.9*len(ws))]:.2f}")
    conf = sorted(float(r["winner_side_price"]) for r in sided if r["vote_overturned_market"] != "True")
    if conf:
        med = conf[len(conf) // 2] if len(conf) % 2 else (conf[len(conf) // 2 - 1] + conf[len(conf) // 2]) / 2
        put("replayConfirmedN", str(len(conf)))
        put("replayConfirmedMedian", f"{med:.2f}")
        put("replayConfirmedCostCents", str(int(round(100 * (1 - med)))))
    names = " ".join(r["title"] for r in over)
    put("replayHasVenezuela", "yes" if "Gonz" in names else "no")
    put("replayHasBlitz", "yes" if "Blitz" in names else "no")
    # ---- both sides of the budget (capture_economics.py, capture_economics_summary.py)
    ce = json.load(open(os.path.join(DATA, "capture_economics_summary.json")))
    cpts = load_csv("capture_economics_points.csv")
    put("nEconContested", str(ce["n_contested_polymarket"]))
    put("nEconMatched", str(ce["n_requests_ok"]))
    put("nEconDerived", str(ce["match_counts"].get("derived", 0)))
    put("nEconTitle", str(ce["match_counts"].get("title", 0)))
    put("nEconMarkets", str(ce["n_market_rounds"]))
    put("nEconAnyVoteMarkets", str(ce["n_market_rounds_any_vote"]))
    put("nEconPayoutRequests", str(ce["n_payout_requests_ok"]))
    put("nEconBondOnlyRequests", str(ce["n_bond_only_requests_ok"]))
    chk = ce["derived_api_check"]
    assert chk["different"] == 0  # the text says the API returns the same questionID for every listed market
    put("nDerivedApiListed", str(chk["same_questionID"]))
    put("nDerivedApiMissing", str(chk["not_listed"]))
    ois = sorted(float(p["oi"]) for p in cpts)
    vfs = sorted(float(p["V_F"]) for p in cpts)
    dls = sorted(float(p["delta_F"]) for p in cpts)
    med = lambda xs: xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2
    put("econOIMedian", thousands(round(med(ois), -3)))
    put("econVMedianM", f"{med(vfs) / 1e6:.1f}")
    put("econDeltaMedianPct", f"{100 * med(dls):.1f}")
    put("econDeltaPSeventyFivePct", f"{100 * dls[3 * len(dls) // 4]:.0f}")
    put("econDeltaGeTenth", str(sum(1 for d in dls if d >= 0.1)))
    put("econDeltaGeOne", str(sum(1 for d in dls if d >= 1)))
    for era, nm in (("A", "EraA"), ("B", "EraB")):
        sub = [p for p in cpts if p["era"] == era]
        put(f"econMarkets{nm}", str(len(sub)))
        put(f"econDeltaGeTenth{nm}", str(sum(1 for p in sub if float(p["delta_F"]) >= 0.1)))
        put(f"econDeltaGeOne{nm}", str(sum(1 for p in sub if float(p["delta_F"]) >= 1)))
    top = max(cpts, key=lambda p: float(p["delta_F"]))
    put("econTopOIM", f"{float(top['oi']) / 1e6:.1f}")
    put("econTopVM", f"{float(top['V_F']) / 1e6:.1f}")
    put("econTopStakeValueM", f"{float(top['S']) * float(top['uma_price']) / 1e6:.1f}")
    put("econTopDelta", f"{float(top['delta_F']):.0f}")
    put("econTopOverStake", f"{float(top['oi']) / (float(top['S']) * float(top['uma_price'])):.1f}")
    put("econNAboveAllStake", str(sum(1 for p in cpts if float(p["oi"]) > float(p["S"]) * float(p["uma_price"]))))
    put("econOITotalM", f"{sum(ois) / 1e6:.0f}")
    # who could have collected: coalitions the size of today's k largest stakers
    co = ce["coalitions_today"]
    put("econCapTopOne", str(co["1"]["n_capturable"]))
    put("econMaxDeltaTopOnePct", f"{100 * (co['1']['max_delta'] or 0):.1f}")  # none capturable on payout votes
    put("econCapTopFour", str(co["4"]["n_capturable"]))
    put("econMaxDeltaTopFour", f"{co['4']['max_delta']:.2f}")
    put("econMaxDeltaTopFourPct", f"{100 * co['4']['max_delta']:.0f}")
    put("econCapTopTen", str(co["10"]["n_capturable"]))
    smin = min(co["sigma_F_of_delta_ge_1"])
    put("econMinSigmaDeltaOnePct", f"{math.floor(1000 * smin) / 10:.1f}")  # rounded down: 'at least' must hold
    put("econRoundsSeveral", str(ce["rounds_with_several_markets"]))
    put("econMaxMarketsRound", str(ce["max_markets_in_a_round"]))
    mar = ce["march"]
    put("marchOI", thousands(mar["oi_round_end"]))
    put("marchOIM", f"{mar['oi_round_end'] / 1e6:.2f}")
    put("marchWhaleDeltaPct", f"{100 * mar['delta_whale']:.1f}")
    ev = ce["march_event"]["returns"]
    sd = ce["march_event"]["prior_year_sd_of_abnormal"]
    put("econUmaOne", f"{ev['1']['uma_pct']:.1f}")
    put("econEthOneAbs", f"{abs(ev['1']['eth_pct']):.1f}")
    put("econAbnEthOne", f"{ev['1']['abn_eth_lp']:.1f}")
    put("econAbnEthThree", f"{ev['3']['abn_eth_lp']:.1f}")
    put("econAbnEthSevenAbs", f"{abs(ev['7']['abn_eth_lp']):.1f}")
    put("econAbnBtcSevenAbs", f"{abs(ev['7']['abn_btc_lp']):.1f}")
    put("econUmaSevenAbs", f"{abs(ev['7']['uma_pct']):.1f}")
    put("econEthSevenAbs", f"{abs(ev['7']['eth_pct']):.1f}")
    put("econSdEthOne", f"{sd['1_eth']['sd_lp']:.1f}")
    put("econSdEthThree", f"{sd['3_eth']['sd_lp']:.1f}")
    put("econSdEthSeven", f"{sd['7_eth']['sd_lp']:.1f}")
    put("econSdBtcSeven", f"{sd['7_btc']['sd_lp']:.1f}")
    # stake history of the three wallets (march_stake_history.py)
    hist = json.load(open(os.path.join(DATA, "march_stake_history.json")))
    wa, wb = "0x8e349da0c6ec06e496f145e421424d2fdfe9c97a", "0xc60aa5a87d580b3181aef33a402d88bfe705fea0"
    vot = "0x004395edb43efca9885cedad51ec9faf93bd34ac"
    staked = [e for e in hist if e["name"] == "Staked"]
    rew = lambda w: sorted(e["time"] for e in staked if e["voter"].lower() == w and e["from"].lower() == vot)
    ra, rb = rew(wa), rew(wb)
    put("whaleRestakesA", str(len(ra)))
    put("whaleRestakesB", str(len(rb)))
    put("whaleRestakesPaired", str(sum(1 for t in ra if any(abs(t - u) <= 120 for u in rb))))
    fresh = sorted(e["time"] for e in staked if e["from"].lower() != vot)
    put("whaleFirstStakeHours", f"{(fresh[2] - fresh[0]) / 3600:.1f}")
    put("whaleFirstStakeDate", dt.datetime.fromtimestamp(fresh[0], dt.timezone.utc).strftime("%B %Y"))
    cut = 1742774400  # 2025-03-24 00:00 UTC, the start of the reveal day
    month = [e for e in staked if cut - 30 * 86400 <= e["time"] < cut]
    assert all(e["from"].lower() == vot for e in month)
    put("whaleMonthRewards", thousands(sum(int(e["amount"]) for e in month) / WAD))
    # mainnet-fork replay of the vote's end (build_march_fixture.py, MarchReplay.fork.t.sol)
    fx = json.load(open(os.path.join(os.path.dirname(DATA), "prototype", "fixtures", "march_reveals.json")))
    put("forkReplayBlock", thousands(fx["forkBlock"]))
    smallest = min(sum(int(x) for x in t["tokens"]) for t in fx["txs"] if t["whale"])
    put("marchWalletCPct", pct(smallest / S, 1))
    put("whaleFreshBeforeVote", str(sum(1 for t in fresh if t < cut)))
    # what a capturer could actually have bought (executable_profit.py)
    ex = json.load(open(os.path.join(DATA, "executable_profit_summary.json")))
    put("execN", str(ex["n"]))
    put("execMedian", thousands(round(ex["E_median"], -3)))
    put("execMaxM", f"{ex['E_max'] / 1e6:.1f}")
    put("execTotalM", f"{ex['E_total'] / 1e6:.0f}")
    put("execOverOIMedianPct", f"{100 * ex['E_over_OI_median']:.0f}")
    put("execGeTenth", str(ex["n_delta_exec_ge"]["0.1"]))
    put("execGeOne", str(ex["n_delta_exec_ge"]["1.0"]))
    put("execDeltaMedianPct", f"{100 * ex['delta_exec_quantiles']['0.5']:.2f}")
    for k, nm in ((1, "One"), (2, "Two"), (4, "Four"), (10, "Ten")):
        t = ex[f"top{k}"]
        put(f"execTop{nm}N", str(t["n_capturable"]))
        put(f"execTop{nm}MaxPct", f"{100 * (t['max_delta'] or 0):.1f}")
    # March 2025 was captured toward YES: the wallets' executable revenue on YES (executable_profit.py, March block)
    my = json.load(open(os.path.join(DATA, "executable_profit_march_yes.json")))
    parts = [round(my["windows"][k]["revenue_if_yes"], -2) for k in ("dispute_to_reveal_start", "reveal_start_to_last_whale", "after_last_whale")]
    assert abs(sum(parts) - round(my["total"], -2)) < 1  # the three windows, as printed, add up to the total
    put("execMarch", thousands(round(my["total"], -2)))
    put("execMarchDispute", thousands(parts[0]))
    put("execMarchReveal", thousands(parts[1]))
    put("execMarchAfter", thousands(parts[2]))
    put("execMarchWhalePct", f"{100 * my['total'] / (cf['whale_stake_actual'] / WAD * p_mar):.1f}")
    # tally settlement R_mu replayed from the first-round tallies (ramp_replay.py); mu = 0 is proportional settlement
    rr = json.load(open(os.path.join(DATA, "ramp_replay.json")))
    for mu, nm in (("0.0", "Zero"), ("0.1", "Ten"), ("0.15", "Fifteen"), ("0.2", "Twenty"), ("0.25", "TwentyFive"), ("0.3", "Thirty")):
        b = rr["by_mu"][mu]
        put(f"rampCut{nm}", thousands(b["yes_no_below_full"]))
        put(f"rampCutPct{nm}", pct(b["yes_no_below_full"] / b["yes_no_both_pay"], 1))
        put(f"rampCutEraB{nm}", thousands(b["yes_no_below_full_eraB"]))
        put(f"rampCutEraBPct{nm}", pct(b["yes_no_below_full_eraB"] / b["yes_no_both_pay_eraB"], 1))
        put(f"rampHaircut{nm}", f"{100 * b['yes_no_haircut_median']:.1f}")
        put(f"rampWinnerPTen{nm}", f"{b['winner_payout_p10']:.2f}")
        put(f"rampWinnerFull{nm}", str(b["winner_full_dollar"]))
        put(f"rampShiftTenPct{nm}", f"{100 * b['max_shift_per_10pct_stake']:.1f}")
        put(f"rampCaptureMarch{nm}", f"{100 * b['one_dollar_capture_march']:.2f}")
        put(f"rampMarchWith{nm}", f"{rr['march'][f'mu={mu}']['with']:.2f}")
    b20 = rr["by_mu"]["0.2"]
    put("rampYesNoBothPay", thousands(b20["yes_no_both_pay"]))
    put("rampYesNoBothPayEraB", thousands(b20["yes_no_both_pay_eraB"]))
    put("rampHaircutMaxTwenty", f"{100 * b20['yes_no_haircut_max']:.0f}")
    put("rampHalfN", str(b20["half_both_pay"]))
    put("rampHalfDevMedianCents", f"{100 * b20['half_dev_median']:.1f}")
    put("rampHalfDevMaxCents", f"{100 * b20['half_dev_max']:.0f}")
    put("rampContestedSidedN", str(rr["n_contested_sided"]))
    aa = rr["ask_again"]
    put("askAgainBoth", thousands(aa["both_rules"]))
    put("askAgainDisagree", str(aa["ramp_only"] + aa["deployed_only"]))
    pv = rr["pivotal"]["0.2"]
    put("rampPivotalN", str(pv["n"]))
    put("rampPivotalMedianCentsTwenty", f"{100 * pv['median_shift']:.1f}")
    put("rampPivotalMaxCentsTwenty", f"{100 * pv['max_shift']:.1f}")
    cs = rr["coalition_switch"]
    assert cs["top1"]["eraB"]["deployed_flip"] == 0 and cs["top4"]["eraB"]["deployed_flip"] == 0  # text: they roll, never flip
    put("coalEraBN", str(cs["top1"]["eraB"]["n"]))
    put("coalTopOneRoll", str(cs["top1"]["eraB"]["deployed_roll"]))
    put("coalTopOneMedianCents", f"{100 * cs['top1']['eraB']['ramp_median_shift']:.0f}")
    put("coalTopOneMaxCents", f"{100 * cs['top1']['eraB']['ramp_max_shift']:.0f}")
    put("coalTopFourRoll", str(cs["top4"]["eraB"]["deployed_roll"]))
    put("coalTopFourMedianCents", f"{100 * cs['top4']['eraB']['ramp_median_shift']:.0f}")
    put("coalTopFourMaxCents", f"{100 * cs['top4']['eraB']['ramp_max_shift']:.0f}")
    # the delay lever tally settlement keeps: the same stakes moved to "too early" have the question asked again
    put("coalTopOneAskAgain", str(cs["top1"]["eraB"]["ramp_ask_again"]))
    put("coalTopFourAskAgain", str(cs["top4"]["eraB"]["ramp_ask_again"]))
    put("rampMarchBps", thousands((int(M["marchYesVotesBps"]) - 2000) * 10000 // 6000))  # TallyAdapter.ramp at mu = 0.2
    assert rr["march"]["mode_without"] == "p4"  # text: without the wallets "too early" leads the first round
    put("rampMarchVotesPct", pct(rr["march"]["f_with"], 1))
    put("marchTooEarlyWithoutPct", pct(te / (total - cf["whale_stake_actual"]), 0))
    # single-voter-pivotal resolutions in which the largest supporter alone could have carried another answer
    tal = {(t["roundId"], t["requestTime"], t["ancKey"]): t for t in load_csv("contested_answer_tallies.csv")}
    flips = 0
    for c in cont:
        if c["kSupportersWhoseRemovalRolls"] != "1":
            continue
        t = tal[(c["roundId"], c["requestTime"], c["ancKey"])]
        th = 0.5 if int(c["resolvedBlock"]) < SPAT_CHANGE_BLOCK else 0.65
        others = [p for p in ("p1", "p2", "p3", "p4") if p != c["winner"]]
        flips += float(c["top1SupporterShareOfStaked"]) + max(float(t[p]) for p in others) > th
    put("nPivotalFlip", str(flips))
    pflips = 0
    for c in ppiv:
        t = tal[(c["roundId"], c["requestTime"], c["ancKey"])]
        th = 0.5 if int(c["resolvedBlock"]) < SPAT_CHANGE_BLOCK else 0.65
        others = [p for p in ("p1", "p2", "p3", "p4") if p != c["winner"]]
        pflips += float(c["top1SupporterShareOfStaked"]) + max(float(t[p]) for p in others) > th
    put("nPayoutPivotalFlip", str(pflips))
    words = {0: "none", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
    put("nPivotalFlipWord", words[flips])
    put("nPayoutPivotalFlipWord", words[pflips])
    put("nPayoutPivotalWord", words.get(len(ppiv), str(len(ppiv))) if len(ppiv) <= 10 else {11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen"}.get(len(ppiv), str(len(ppiv))))
    put("tapeForceStakersTwentyWord", words[int(M["tapeForceStakersTwenty"])])
    tens = {5: "fifty", 6: "sixty"}
    npv = int(M["nPivotal"])
    put("nPivotalWord", tens[npv // 10] + ("-" + words[npv % 10] if npv % 10 else ""))
    # the cap under R_mu: the loss of stake value delta each contested market needs, and the DVM's own penalty
    sc = rr["security_condition"]["0.2"]
    put("rampMarkets", str(sc["n"]))
    put("rampDeltaNeedMedianPct", f"{100 * sc['delta_needed_median']:.1f}")
    put("rampNeedTenth", str(sc["n_need_above_0.1"]))
    put("rampNeedQuarter", str(sc["n_need_above_0.25"]))
    put("rampNeedOne", str(sc["n_need_above_1.0"]))
    put("rampAbovePenaltyCap", str(sc["n_above_penalty_cap"]))
    assert sc["n_above_penalty_cap"] == sc["n"]  # the text: "every one of the contested markets was larger"
    # the same condition on the summed open interest of the contested markets a round settles
    pr = sc["per_round"]
    put("roundAbovePenaltyCap", str(pr["n_market_rounds_in_rounds_above_0.001"]))
    put("roundNeedTenth", str(pr["n_market_rounds_in_rounds_above_0.1"]))
    put("roundNeedOne", str(pr["n_market_rounds_in_rounds_above_1.0"]))
    # the oracle's own loss relative to voting with the winner is the penalty plus the forgone pool rate, at most
    # lambda/theta of the stake (Remark on the oracle's own penalty); the cap uses that upper end at theta = 0.65
    put("penaltyCapUsd", thousands(round(rr["lambda"] / 0.65 * (1 - 2 * 0.2) * conc["cumulativeStake"] * px[max(px)], -2)))
    # what a visible capture costs the token: event study of the captures of on-chain votes with a year of prices
    # (delta_event_study.py)
    de = json.load(open(os.path.join(DATA, "delta_event_study.json")))
    dr = de["drained"]
    put("deltaEvents", str(de["n_events"]))
    put("deltaDrainedN", str(dr["n"]))
    put("deltaDrainedSig", str(dr["n_significant"]))
    put("deltaDrainedMedianPct", f"{100 * dr['loss_median']:.0f}")
    assert 0.22 < dr["loss_median"] < 0.28  # the text: "a quarter of the stake's value, the median of the first group"
    put("deltaDrainedMinPct", f"{100 * dr['loss_min']:.0f}")
    put("deltaDrainedMaxPct", f"{100 * dr['loss_max']:.1f}")
    assert de["not_drained"]["n_significant"] == 0  # the text: within the token's ordinary noise
    put("deltaUnprotectedAtDrainedMedian", str(de["unprotected_at_drained_median"]["n"]))
    put("deltaUnprotectedAtDrainedMin", str(de["unprotected_at_drained_min"]["n"]))
    nd, pool = de["not_drained"], de["pooled_not_drained"]
    put("deltaCleanN", str(nd["n"]))
    clean_med = sorted(v["loss"] for v in nd["events"].values())
    put("deltaCleanMedianLossPct", f"{100 * (clean_med[len(clean_med) // 2] if len(clean_med) % 2 else (clean_med[len(clean_med) // 2 - 1] + clean_med[len(clean_med) // 2]) / 2):.1f}")
    assert pool["mean_car7"] > -1.96 * pool["se"]  # the text: pooled, no sign of a loss
    wo = de["pooled_not_drained_without_indexed"]
    assert wo["mean_car7"] > -1.96 * wo["se"]  # the text: also without Indexed
    assert 2.5 < de["indexed_week_ratio_vs_eth"] < 3.5  # the text: Indexed's token tripled against ETH that week
    put("deltaDetectablePct", f"{100 * pool['detectable_loss']:.0f}")  # 80% power
    put("deltaUnprotectedAtDetectable", str(de["unprotected_at_detectable"]["n"]))
    # one-sided 95% upper bounds on the mean weekly loss, on the spread across events
    ub = de["upper95_loss_crosssection"]
    put("deltaBoundAllPct", f"{100 * ub['all']:.0f}")
    put("deltaBoundWoPct", f"{100 * ub['without_indexed']:.0f}")
    assert ub["all"] < pool["detectable_loss"] and ub["without_indexed"] < pool["detectable_loss"]  # text: a scenario above both bounds
    # beyond the limit at the 80%-power loss, and the shares a coalition could have bought there
    bb = de["buyable_at_detectable"]
    assert bb["beyond"] == de["unprotected_at_detectable"]["n"] and bb["with_trades"] == bb["beyond"]
    put("deltaBuyableBeyond", str(bb["buyable_above_limit"]))
    # neg-risk market-rounds among the contested ones, and the 80%-power count without them
    negr = {r["conditionId"]: r["negRisk"] == "True" for r in load_csv("capture_economics.csv")}
    cpts_all = load_csv("capture_economics_points.csv")
    put("negRiskMarkets", str(sum(1 for p in cpts_all if negr.get(p["conditionId"]))))
    det = de["pooled_not_drained"]["detectable_loss"]
    need = lambda p: float(p["oi"]) / (0.6 * float(p["S"]) * float(p["uma_price"]))
    beyond = [p for p in cpts_all if need(p) > det]
    assert len(beyond) == de["unprotected_at_detectable"]["n"]
    put("deltaUnprotectedWoNegRisk", str(sum(1 for p in beyond if not negr.get(p["conditionId"]))))
    assert not any(negr.get(p["conditionId"]) for p in cpts_all if need(p) > 1.0)  # text: all of those beyond delta = 1 remain
    ev = [r for r in csv.DictReader(open(os.path.join(DATA, "delta_event_study.csv"), encoding="utf-8"))
          if r["included"] == "True"]
    assert len(ev) == de["n_events"]
    ev.sort(key=lambda r: (r["drained"] != "True", r["date"]))
    lines = []
    for i, r in enumerate(ev):
        if i and r["drained"] != ev[i - 1]["drained"]:
            lines.append("\\midrule")
        k = max(k for k in (1, 3, 7) if r.get(f"car{k}_eth"))
        ret = math.exp(float(r[f"car{k}_eth"])) - 1
        z = float(r[f"z{k}_eth"])
        mark = "$^{*}$" if k != 7 else ""
        lines.append(f"{r['event']} & {r['ticker']} & {r['date'][:7]} & {'yes' if r['drained'] == 'True' else 'no'} & "
                     f"${100 * ret:+.1f}$\\%{mark} & ${z:+.1f}$ \\\\")
    open(os.path.join(HERE, "tab_delta.tex"), "w", encoding="utf-8").write("\n".join(lines) + "\n\\bottomrule\n")
    # proportional settlement with fee-funded truthful payments (Freeman, Lahaie and Pennock): a pool R that pays a
    # truthful vote Delta/2 more per unit of pool share deters a coalition holding Q shares when R >= 2Q/(Delta(1 - 2mu));
    # Delta <= 1, so 2Q/(1 - 2mu) bounds the pool from below. Q: the Yes shares a coalition could have bought before
    # the wallets' reveals (executable_profit.py, March windows one and two)
    qpre = my["windows"]["dispute_to_reveal_start"]["net_yes_shares"] + my["windows"]["reveal_start_to_last_whale"]["net_yes_shares"]
    put("freemanQMarch", thousands(qpre))
    put("freemanPoolMarch", thousands(round(2 * qpre / (1 - 2 * 0.2), -3)))
    put("marchPoolUsd", thousands(round(cf["totalSlashed_wei"] / WAD * p_mar, -3)))
    # the vote publishes its answer before the round ends (reveal_leak.py)
    lk = json.load(open(os.path.join(DATA, "reveal_leak_summary.json")))
    put("leakMarkets", str(lk["n_market_rounds"]))
    put("leakLeadMedianH", f"{lk['lead_min_quantiles']['0.5'] / 60:.0f}")
    put("leakHigh", str(lk["n_market_rounds"] - lk["n_p_cross_le_0.9"]))
    put("leakLow", str(lk["n_p_cross_le_0.9"]))
    low = [r for r in load_csv("reveal_leak.csv") if r["status"] == "ok" and float(r["p_cross"]) <= 0.9]
    # the text names March 2025 (round 10085) as the one market below 90 cents when the outcome was fixed
    assert len(low) == 1 and low[0]["roundId"] == "10085" and float(low[0]["p_cross"]) < 0.20, low
    put("leakMarchCents", f"{100 * float(low[0]['p_cross']):.0f}")
    # noisy coordination game (capture_probe.py E7, floating point discovery)
    e7 = cap["E7"]
    def span(r):
        fp = [x for x in r["fixed_point_cutoffs"] if x > 0.05] or r["fixed_point_cutoffs"]
        return f"[{min(fp):.3f}, {max(fp):.3f}]"
    put("noisyA", span(e7[0]))
    put("noisyB", f"[0, {max(e7[1]['fixed_point_cutoffs']):.3f}]")
    put("noisyC", ", ".join(f"{x:.3f}" for x in e7[2]["fixed_point_cutoffs"]))
    # prototype
    put("gasRegister", "102,204")
    put("gasRegisterVotesCast", "61,304")  # MarginReaderVotesCast against a mock exposing the tally by answer (forge test -vv, 2026-10-07)
    # settle() by path: forge test --gas-report run per test of test/Fallback.t.sol (2026-10-07, after the F_mu^d flag)
    put("gasSettleMin", "113,560")          # resolved without a vote (test_optimistic_resolution_needs_no_margin)
    put("gasSettleUncontested", "119,208")  # vote, winner above 1 - mu: one-and-zero
    put("gasSettleVariantKeep", "134,856")  # F_mu^d, contested vote for the favorite: one-and-zero
    put("gasSettleDeleted", "138,852")      # deleted request: reference price
    put("gasSettleTape", "154,419")         # F_mu, contested vote: reference price
    put("gasSettleMax", "154,709")          # F_mu^d, contested vote against the favorite: reference price
    # TallyAdapter.settle by path (forge test --gas-report per test of test/Tally.t.sol, 2026-10-07, Yes-share rule;
    # the mock margin source stores share + 1 in one slot, as the child tunnel does)
    put("gasTallyOptimistic", "129,404")    # settled without a vote
    put("gasTallyFull", "135,819")          # Yes share at 1 - mu: one-and-zero (No paid in full: 135,359)
    put("gasTallyRamp", "155,719")          # contested vote paid by the ramp (March tallies)
    put("gasRelay", "88,434")               # TallyRootTunnel.relay, mock bridge delivering in the same transaction (-vvvv trace)
    put("gasReceive", "24,528")             # TallyChildTunnel.processMessageFromRoot inside that relay (-vvvv trace)
    put("gasRecord", "54,246")
    put("gasRecordFirst", "68,300")
    put("gasTwap", "9,937")
    put("forkMarginA", "5018")
    put("forkMarginB", "5380")
    # dates
    put("spatChangeDate", "April 20, 2025")
    put("deployDate", "February 24, 2023")
    put("censusEnd", "early October 2026")

    # ---- when the prize was minted (prize_growth.py): standard-adapter markets with a payout vote
    pg = json.load(open(os.path.join(DATA, "prize_growth_summary.json")))
    sd = pg["standard"]
    put("prizeN", str(sd["n"]))
    put("prizeNegRiskN", str(pg["all"]["n"] - sd["n"]))
    put("prizeEscM", f"{sd['oi_esc_total'] / 1e6:.1f}")
    put("prizeFirstM", f"{sd['oi_first_total'] / 1e6:.0f}")
    put("prizePreM", f"{sd['oi_pre_total'] / 1e6:.1f}")
    put("prizeAfterPct", pct(sd["share_after_esc_total"], 0))
    put("prizeAfterTopPct", pct(sd["share_after_esc_top20_median"], 0))
    put("prizePreGrowth", f"{sd['growth_pre_to_esc_top20_median']:.1f}")
    put("prizeVoteGrowth", f"{sd['growth_esc_to_first_top20_median']:.0f}")
    put("prizeVoteHours", f"{sd['vote_hours_median']:.0f}")
    put("prizeDeltaOneEsc", str(sd["deltaF_ge1_esc"]))
    put("prizeDeltaOneFirst", str(sd["deltaF_ge1_first"]))
    put("prizeDeltaTenthEsc", str(sd["deltaF_ge01_esc"]))
    put("prizeDeltaTenthFirst", str(sd["deltaF_ge01_first"]))
    put("prizeReqOneEsc", str(sd["dreq_ge1_esc"]))
    put("prizeReqOneFirst", str(sd["dreq_ge1_first"]))
    put("prizeReqDetEsc", str(sd["dreq_ge014_esc"]))
    put("prizeReqDetFirst", str(sd["dreq_ge014_first"]))
    put("prizeRolled", str(pg["rolled_first_ne_resolving"]))

    # ---- participation (2026-10-08): tally settlement's limit is delta (1 - 2 mu) pi V, pi the share of the staked
    # supply that votes in the first round, on which the rule pays (Theorems 1 and 2;
    # first_round_participation.py). The full-participation counts set above from the upstream summaries are
    # recomputed here with pi = 1 as a check of this code, then replaced by the counts with each round's pi.
    fpp = {(r["roundId"], r["requestTime"], r["ancKey"]): float(r["pi_first"])
           for r in load_csv("first_round_participation.csv")}
    p51 = load_csv("capture_economics_points.csv")
    pif = lambda p: fpp[(p["roundId"], p["requestTime"], p["ancKey"])]
    unit = lambda p: 1.0
    stakev = lambda p: float(p["S"]) * float(p["uma_price"])
    lam, det = rr["lambda"], de["pooled_not_drained"]["detectable_loss"]
    exr = {(r["roundId"], r["conditionId"]): r for r in load_csv("executable_profit.csv") if r["status"] == "ok"}
    bought_sh = lambda p: float(exr[(p["roundId"], p["conditionId"])]["w1_shares"] or 0) + float(exr[(p["roundId"], p["conditionId"])]["w2_shares"] or 0)

    def limit_counts(w):
        need = sorted(float(p["oi"]) / (0.6 * stakev(p) * w(p)) for p in p51)
        rd = {}
        for p in p51:
            g = rd.setdefault(p["roundId"], [0.0, stakev(p), 0])
            g[0] += float(p["oi"]) / w(p)
            g[2] += 1
        above = lambda d: sum(1 for x in need if x > d)
        rounds_above = lambda d: sum(g[2] for g in rd.values() if g[0] / (0.6 * g[1]) > d)
        beyond = [p for p in p51 if float(p["oi"]) > det * 0.6 * stakev(p) * w(p)]
        buy = sum(1 for p in beyond if (p["roundId"], p["conditionId"]) in exr and bought_sh(p) > det * 0.6 * stakev(p) * w(p))
        return need, above, rounds_above, beyond, buy

    need1, above1, rabove1, beyond1, buy1 = limit_counts(unit)
    assert abs(need1[len(need1) // 2] - sc["delta_needed_median"]) < 1e-12 and len(need1) % 2 == 1
    assert [above1(d) for d in (0.1, 0.25, 1.0, lam)] == [sc["n_need_above_0.1"], sc["n_need_above_0.25"], sc["n_need_above_1.0"], sc["n_above_penalty_cap"]]
    assert above1(lam / 0.65) == sc["n"]  # the text: every contested market-round held more than the lambda/theta cap
    assert [rabove1(d) for d in (0.1, 1.0, lam)] == [pr["n_market_rounds_in_rounds_above_0.1"], pr["n_market_rounds_in_rounds_above_1.0"], pr["n_market_rounds_in_rounds_above_0.001"]]
    assert [above1(dr["loss_median"]), above1(dr["loss_min"]), above1(det)] == [de["unprotected_at_drained_median"]["n"], de["unprotected_at_drained_min"]["n"], de["unprotected_at_detectable"]["n"]]
    assert buy1 == bb["buyable_above_limit"]
    need, above, rabove, beyond_pi, buy = limit_counts(pif)
    pis = sorted(pif(p) for p in p51)
    put("piFirstMinPct", pct(pis[0], 1))
    put("piFirstMedPct", pct(pis[len(pis) // 2], 1))
    put("piFirstMaxPct", pct(pis[-1], 1))
    put("piFirstMinCutPct", f"{100 * (1 - pis[0]):.0f}")
    put("rampDeltaNeedMedianPct", f"{100 * need[len(need) // 2]:.1f}")
    put("rampNeedTenth", str(above(0.1)))
    put("rampNeedQuarter", str(above(0.25)))
    put("rampNeedOne", str(above(1.0)))
    assert above(lam) == len(need)  # the text: every one of the contested markets was larger than the penalty's limit
    put("rampAbovePenaltyCap", str(above(lam)))
    put("roundAbovePenaltyCap", str(rabove(lam)))
    put("roundNeedTenth", str(rabove(0.1)))
    put("roundNeedOne", str(rabove(1.0)))
    put("deltaUnprotectedAtDrainedMedian", str(above(dr["loss_median"])))
    put("deltaUnprotectedAtDrainedMin", str(above(dr["loss_min"])))
    put("deltaUnprotectedAtDetectable", str(above(det)))
    assert len(beyond_pi) == above(det) and all((p["roundId"], p["conditionId"]) in exr for p in beyond_pi)
    put("deltaBuyableBeyond", str(buy))
    put("deltaUnprotectedWoNegRisk", str(sum(1 for p in beyond_pi if not negr.get(p["conditionId"]))))
    assert not any(negr.get(p["conditionId"]) for p in p51 if float(p["oi"]) / (0.6 * stakev(p) * pif(p)) > 1.0)  # text: all beyond delta = 1 remain
    # the text: a manipulation changes the coalition's pool take by at most lambda/theta of its stake, which moves the
    # counts at a tenth by at most one and the count at the 14% scenario by at most two, and no other count
    eps = lam / 0.65
    for d in (0.25, 1.0, dr["loss_median"], dr["loss_min"]):
        assert above(d - eps) == above(d) == above(d + eps), d
        assert rabove(d - eps) == rabove(d) == rabove(d + eps), d
    assert max(abs(above(0.1 + e) - above(0.1)) for e in (-eps, eps)) == 1
    assert max(abs(rabove(0.1 + e) - rabove(0.1)) for e in (-eps, eps)) <= 1
    assert max(abs(above(det + e) - above(det)) for e in (-eps, eps)) == 2
    put("deltaUnprotectedAtDetectableHi", str(above(det - eps)))
    # the prize at the dispute and at the end of the first round, against the limit with that round's pi
    prow = [r for r in load_csv("prize_growth.csv") if r["status"] == "ok" and r["negRisk"] not in ("True", "true", "1")]
    by_cid = {(p["roundId"], p["conditionId"]): p for p in p51}
    assert len(prow) == sd["n"] and all((r["roundId"], r["conditionId"]) in by_cid for r in prow)
    pir = lambda r: pif(by_cid[(r["roundId"], r["conditionId"])])
    for nm, col, d, w in (("prizeReqOneEsc", "dreq_esc", 1.0, "dreq_ge1_esc"), ("prizeReqOneFirst", "dreq_first", 1.0, "dreq_ge1_first"),
                          ("prizeReqDetEsc", "dreq_esc", 0.14, "dreq_ge014_esc"), ("prizeReqDetFirst", "dreq_first", 0.14, "dreq_ge014_first")):
        assert sum(1 for r in prow if float(r[col]) >= d) == sd[w], nm
        put(nm, str(sum(1 for r in prow if float(r[col]) / pir(r) >= d)))
    assert M["prizeReqOneEsc"] == "0"  # the text: below the stake's whole value for every market at the dispute
    # tally settlement's cost to contested winners (Section 6.3): those paid less than a dollar at mu = 0.2
    put("rampContestedCutTwenty", str(rr["n_contested_sided"] - int(M["rampWinnerFullTwenty"])))
    # the ceasefire instance (ceasefire_instance.py)
    ci = json.load(open(os.path.join(DATA, "ceasefire_instance.json")))
    v1 = ci["vote_to_reveal"]
    put("cfBuyers", thousands(v1["net_buyers"]))
    put("cfNoM", f"{v1['net_shares'] / 1e6:.1f}")
    put("cfNoCost", thousands(round(v1["cost"], -3)))
    put("cfLargestBuyerPct", pct(v1["largest_buyer_share"], 0))
    put("cfTickPct", pct(v1["no_bought_at_tick_share"], 0))
    put("cfYesM", f"{v1['yes_bought'] / 1e6:.1f}")
    put("cfYesCents", f"{100 * v1['yes_avg_price']:.2f}")
    put("cfMintPct", pct(v1["no_bought_in_mint_matches_share"], 0))
    put("cfNoTotalM", f"{ci['net_shares_total'] / 1e6:.1f}")
    put("cfCostTotal", thousands(round(ci["cost_total"], -3)))
    put("cfRevenueM", f"{ci['revenue_total'] / 1e6:.1f}")
    op = ci["oi_path"]
    put("cfOIEscM", f"{op['escalation'] / 1e6:.2f}")
    put("cfOIDayM", f"{op['escalation_plus_24h'] / 1e6:.1f}")
    put("cfOIRevealM", f"{op['reveal_start'] / 1e6:.1f}")
    put("cfOIEndM", f"{op['round_end'] / 1e6:.1f}")
    put("cfMintedPct", pct(1 - op["escalation"] / op["round_end"], 1))
    put("cfVoters", str(ci["voters"]))
    put("cfHNoPct", pct(ci["h_no"], 1))
    put("cfNeedPct", pct(ci["capture_needs"], 1))
    put("cfCoalitionK", str(ci["coalition_k"]))
    put("cfCoalitionPct", pct(ci["coalition_share"], 1))
    put("cfLargestVoterPct", pct(ci["largest_voter_share"], 1))
    put("cfCoalitionStakeM", f"{ci['coalition_stake_value'] / 1e6:.1f}")
    put("cfStakeM", f"{ci['stake_value'] / 1e6:.1f}")
    put("cfAllUmaM", f"{ci['all_uma_value'] / 1e6:.1f}")
    put("cfOverStake", f"{ci['revenue_over_stake_value']:.1f}")
    put("cfOverAllUma", f"{ci['revenue_over_all_uma']:.2f}")
    put("cfUmaPrice", f"{ci['uma_price']:.3f}")
    put("cfDreqEscPct", f"{100 * ci['oi_path']['escalation'] / (0.6 * ci['stake_value']):.0f}")
    put("cfDreqFirstPct", thousands(100 * ci["oi_path"]["round_end"] / (0.6 * ci["stake_value"])))
    # growth of the prize during the vote, and the counterfactual's margin: half the shares at ten times the cost
    put("cfGrowth", f"{ci['oi_path']['round_end'] / ci['oi_path']['escalation']:.0f}")
    put("cfHalfTenX", f"{(0.5 * ci['net_shares_total'] - 10 * ci['cost_total']) / ci['stake_value']:.1f}")
    # fork replays (prototype/test/*.fork.t.sol, forge test -vv; logs in data/raw/*fork*_log.txt)
    fkp = os.path.join(DATA, "fork_results.json")
    for k, v in (json.load(open(fkp)).items() if os.path.exists(fkp) else ()):
        if not k.startswith("_"):  # "_..." keys hold the statements recorded in the ledger
            put(k, v)
    # what the capture replay paid the vote's largest "No" buyers, against the value of every staked token
    # (data/raw is not in the repository; without the log, the rounded figure of fork_results.json is used)
    cap_path = os.path.join(DATA, "raw", "ceasefire_capture_fork_log.txt")
    paid = float(M["forkCfPaidM"]) * 1e6
    if os.path.exists(cap_path):
        cap_log = open(cap_path, encoding="utf-8").read()
        paid = float(re.search(r"USDC\.e paid to them on redemption: ([0-9.]+)", cap_log.split("capture: ", 1)[1]).group(1))
        assert abs(paid / 1e6 - float(M["forkCfPaidM"])) < 0.05, paid
    put("forkCfOverStake", f"{paid / ci['stake_value']:.1f}")

    # ---- appendix tables generated from the data
    def tex(s, n=None):
        s = re.sub(r"\s+", " ", s).strip()
        if n and len(s) > n:
            s = s[: n - 1].rstrip(" ,.;:") + "\u2026"
        s = s.replace("\u2026", "\\ldots{}")
        for a, b in (("\\ldots{}", "\x00"), ("&", "\\&"), ("%", "\\%"), ("$", "\\$"), ("#", "\\#"), ("_", "\\_"), ("\x00", "\\ldots{}")):
            s = s.replace(a, b)
        s = re.sub(r'"([^"]*)"', r"``\1''", s)  # straight double quotes to TeX quotes
        return s.replace("\u00e1", "\\'{a}").replace("\u00e9", "\\'{e}").replace("\u00ed", "\\'{i}").replace("\u00f3", "\\'{o}")
    ans = {"p1": "No", "p2": "Yes", "p3": "half", "p4": "too early"}
    # the month a vote closed: a round ends at midnight UTC, so step back one second
    closed = lambda rid: dt.datetime.fromtimestamp((int(rid) + 1) * 172800 - 1, dt.timezone.utc).strftime("%Y-%m")
    # replay: every sided case the votes-cast trigger at mu = 0.2 moves
    lines = []
    for r in sorted(sided, key=lambda r: int(r["requestTime"])):
        mark = "$\\times$" if r["vote_overturned_market"] == "True" else ""
        lines.append(f"{tex(r['title'], 84)} & {closed(r['roundId'])} & {ans[r['resolvedPrice']]} & "
                     f"{float(r['winner_side_price']):.2f} & {mark} \\\\")
    # the closing rule lives in the generated file: \bottomrule right after \input in a tabular is a misplaced \noalign
    open(os.path.join(HERE, "tab_replay.tex"), "w", encoding="utf-8").write("\n".join(lines) + "\n\\bottomrule\n")
    # budget: the market-rounds with the largest delta
    lines = []
    for p in sorted(cpts, key=lambda p: -float(p["delta_F"]))[:10]:
        lines.append(f"{tex(p['title'], 70)} & {closed(p['roundId'])} & {100 * float(p['theta']):.0f}\\% & {ans[p['winner']]} & "
                     f"{ans[p['F']]} & {100 * float(p['hF']):.1f}\\% & {float(p['oi']) / 1e6:.1f} & "
                     f"{float(p['V_F']) / 1e6:.1f} & {float(p['delta_F']):.2f} \\\\")
    open(os.path.join(HERE, "tab_budget.tex"), "w", encoding="utf-8").write("\n".join(lines) + "\n\\bottomrule\n")

    out = os.path.join(HERE, "numbers.tex")
    with open(out, "w", encoding="utf-8") as f:
        f.write("% generated by make_numbers.py; do not edit by hand\n")
        for k, v in M.items():
            f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
    json.dump(M, open(os.path.join(HERE, "numbers.json"), "w"), indent=1)
    print(f"wrote {len(M)} macros to {out}")
    for k in ("nResolved", "nContested", "nPivotal", "marchMargin", "marchThetaMinusHF", "marchAlpha", "topFourPct",
              "captureReqSixtyFiveMarch", "tapeEraBTwenty", "tapePivotalTwenty", "replayOverturned", "replaySided"):
        print(f"  {k} = {M.get(k)}")


if __name__ == "__main__":
    main()
