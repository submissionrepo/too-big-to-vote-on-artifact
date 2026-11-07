"""Figures for the settlement-capture paper, house style hz_figstyle (grayscale, serif).

fig_march_timeline.pdf   (a) cumulative revealed stake on 2025-03-24 for YES and too-early with the three whale reveals,
                         (b) YES price per minute from 18:00 to 01:00 UTC with the reveal and the round end.
fig_winner_share.pdf     ECDF of the winner's share of staked tokens, SPAT-50 era versus SPAT-65 era.
fig_fallback.pdf         tape-fallback trigger rate (SPAT-65 era) and coverage of single-voter-pivotal resolutions by mu.
fig_budget.pdf           open interest against the value of the capture stake, and the loss each round needs.
"""
import csv
import datetime as dt
import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
import hz_figstyle as hz  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "probes", "oracle_capture", "data"))
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)
SPAT_CHANGE_BLOCK = 22309220
WAD = 1e18
MID, LIGHT = "0.42", "0.68"
hz.apply()


def block_to_time(b):
    # anchors from the reveal window of round 10085 (block timestamps read from chain)
    b0, t0 = 22113051, dt.datetime(2025, 3, 24, 0, 3, 23)
    b1, t1 = 22119987, dt.datetime(2025, 3, 24, 23, 16, 47)
    return t0 + (t1 - t0) * (b - b0) / (b1 - b0)


def fig_march():
    # the request that decided the market's payout (the second dispute's); the first settled only that dispute's bonds
    d = json.load(open(os.path.join(DATA, "quick_tally_2025-03-20_000000_2025-03-28_000000.json")))
    S = 22845748.882117637
    votes = sorted([x for x in d if x["event"] == "VoteRevealed" and x["time"] == 1742684664], key=lambda x: (x["blockNumber"], x["logIndex"]))
    whale = {"0x8e349da0c6ec06e496f145e421424d2fdfe9c97a", "0xc60aa5a87d580b3181aef33a402d88bfe705fea0", "0xfc204fcfd2a579157898a212ea25ac98de2b1e1c"}
    t_yes, y_yes, t_te, y_te, cum_y, cum_t = [], [], [], [], 0.0, 0.0
    whale_pts = []
    for v in votes:
        t = block_to_time(v["blockNumber"])
        s = int(v["numTokens"]) / WAD / S
        if int(v["price"]) == 10**18:
            cum_y += s
            t_yes.append(t); y_yes.append(cum_y)
            if v["voter"] in whale:
                whale_pts.append((t, cum_y))
        elif int(v["price"]) == -(1 << 255):
            cum_t += s
            t_te.append(t); y_te.append(cum_t)
    fig, (a, b) = plt.subplots(1, 2, figsize=hz.DOUBLE, gridspec_kw={"width_ratios": [1.15, 1]})
    a.step(t_yes, y_yes, where="post", color=hz.INK, lw=1.2, label="YES")
    a.step(t_te, y_te, where="post", color=MID, lw=1.2, ls="--", label="too early")
    a.axhline(0.5, color=hz.GUIDE, lw=0.8, ls=":")
    a.annotate(r"$\theta$ = 50% of staked (March 2025)", xy=(dt.datetime(2025, 3, 24, 9, 0), 0.507), fontsize=7.5, color="0.3", va="bottom")
    for t, y in whale_pts:
        a.plot([t], [y], marker="o", ms=4, mfc="white", mec=hz.INK, mew=1.0)
    a.annotate("three wallets reveal\n22:58 to 23:00 UTC", xy=(whale_pts[-1][0], whale_pts[-1][1]), xytext=(dt.datetime(2025, 3, 24, 12, 30), 0.40),
               fontsize=7.5, color="0.2", arrowprops=dict(arrowstyle="-", color="0.4", lw=0.6))
    a.set_ylim(0, 0.56)
    a.set_xlim(dt.datetime(2025, 3, 24, 0, 0), dt.datetime(2025, 3, 25, 0, 0))
    a.set_ylabel("cumulative revealed stake / total staked")
    a.set_xlabel("reveal phase, March 24, 2025 (UTC)")
    a.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%H:%M"))
    a.legend(frameon=False, loc="upper left", fontsize=8)
    hz.tag(a, "(a) the vote")
    hz.style_ticklabels(a)

    rows = list(csv.DictReader(open(os.path.join(DATA, "pm_prices_YES_minute_20250324.csv"))))
    ts = [dt.datetime.utcfromtimestamp(int(r["ts"])) for r in rows]
    ps = [float(r["price"]) for r in rows]
    b.plot(ts, ps, color=hz.INK, lw=1.0)
    b.axvline(dt.datetime(2025, 3, 24, 22, 59, 59), color=hz.GUIDE, lw=0.8, ls="--")
    b.axvline(dt.datetime(2025, 3, 25, 0, 0), color=hz.GUIDE, lw=0.8, ls=":")
    b.annotate("last reveal", xy=(dt.datetime(2025, 3, 24, 22, 59), 0.62), fontsize=7.5, color="0.3", ha="right")
    b.annotate("round ends", xy=(dt.datetime(2025, 3, 24, 23, 58), 0.86), fontsize=7.5, color="0.3", ha="right")
    b.set_ylim(0, 1.02)
    b.set_xlim(dt.datetime(2025, 3, 24, 18, 0), dt.datetime(2025, 3, 25, 1, 0))
    b.set_ylabel("price of a YES share (USDC)")
    b.set_xlabel("March 24 to 25, 2025 (UTC)")
    b.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%H:%M"))
    hz.tag(b, "(b) the market")
    hz.style_ticklabels(b)
    fig.tight_layout(w_pad=1.5)
    hz.save(fig, os.path.join(FIG, "fig_march_timeline.pdf"))


def fig_winner_share():
    reqs = list(csv.DictReader(open(os.path.join(DATA, "requests_summary.csv"), encoding="utf-8")))
    a = sorted(float(r["modeShareOfStaked"]) for r in reqs if r["modeShareOfStaked"] and int(r["resolvedBlock"]) < SPAT_CHANGE_BLOCK)
    b = sorted(float(r["modeShareOfStaked"]) for r in reqs if r["modeShareOfStaked"] and int(r["resolvedBlock"]) >= SPAT_CHANGE_BLOCK)
    fig, ax = plt.subplots(figsize=(3.45, 2.35))
    for data, lab, col, ls in ((a, rf"$\theta$ = 50% era (n = {len(a):,})", MID, "--"), (b, rf"$\theta$ = 65% era (n = {len(b):,})", hz.INK, "-")):
        xs = np.array(data)
        ys = np.arange(1, len(xs) + 1) / len(xs)
        ax.step(xs, ys, where="post", color=col, lw=1.2, ls=ls, label=lab)
    for x, lab in ((0.5, "50%"), (0.65, "65%")):
        ax.axvline(x, color=hz.GUIDE, lw=0.8, ls=":")
        ax.annotate(lab, xy=(x + 0.006, 0.55), fontsize=7, color="0.3", rotation=90, va="bottom")
    ax.set_xlim(0.45, 1.0)
    ax.set_ylim(0, 1)
    ax.set_xlabel("winner's share of the staked supply")
    ax.set_ylabel("share of resolutions")
    ax.legend(frameon=False, loc="upper left", fontsize=7)
    hz.style_ticklabels(ax)
    hz.save(fig, os.path.join(FIG, "fig_winner_share.pdf"))


def fig_fallback():
    fb = json.load(open(os.path.join(DATA, "fallback_probe_results.json")))["votes_cast"]
    mus = [("mu_1/10", 0.10), ("mu_3/20", 0.15), ("mu_1/5", 0.20), ("mu_1/4", 0.25), ("mu_3/10", 0.30)]
    x = [m for _, m in mus]
    trig = [100 * fb[k]["trigger_spat65"]["rate"] for k, _ in mus]
    cov = [fb[k]["single_voter_pivotal_paid_at_tape"]["tape"] for k, _ in mus]
    req = [100 * fb[k]["capture_req_march"] for k, _ in mus]
    fig, ax = plt.subplots(figsize=(3.45, 2.2))
    ax.bar(x, trig, width=0.03, color=LIGHT, edgecolor=hz.INK, lw=0.6, label="paid at the tape, 65% era (%, left)")
    for xi, t in zip(x, trig):
        ax.annotate(f"{t:.2f}%", xy=(xi, t), xytext=(0, 2), textcoords="offset points", ha="center", fontsize=6.5, color="0.2")
    ax2 = ax.twinx()
    ax2.plot(x, cov, color=hz.INK, lw=1.2, marker="s", ms=4, mfc="white", label="pivotal cases covered, of 56 (right)")
    ax2.plot(x, req, color=MID, lw=1.2, marker="o", ms=4, mfc="white", ls="--", label="stake for a 0/1 capture, March-like (%, right)")
    ax2.set_ylim(0, 70)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color("0.35")
    ax2.grid(False)
    ax.set_ylim(0, 3.2)
    ax.set_xlabel(r"$\mu$")
    ax.set_ylabel("paid at the tape (%)")
    ax2.set_ylabel("count, or % of staked")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=1, fontsize=7)
    hz.style_ticklabels(ax)
    hz.style_ticklabels(ax2)
    hz.save(fig, os.path.join(FIG, "fig_fallback.pdf"))


def fig_budget():
    """(a) open interest at the round's end against the value of the stake that captures the other side;
    (b) their ratio by the date the vote closed. One point per market and round (capture_economics_summary.py)."""
    pts = list(csv.DictReader(open(os.path.join(DATA, "capture_economics_points.csv"), encoding="utf-8")))
    floor, dfloor = 1e4, 1e-5
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.9, 2.4), gridspec_kw={"width_ratios": [1, 1.25]})
    for era, fc, lab in (("A", "white", "50% era"), ("B", hz.INK, "65% era")):
        sel = [p for p in pts if p["era"] == era]
        a.scatter([max(floor, float(p["oi"])) for p in sel], [float(p["V_F"]) for p in sel], s=11, marker="o",
                  facecolors=fc, edgecolors=hz.INK, linewidths=0.6, label=lab, zorder=3)
        for low in (False, True):
            ss = [p for p in sel if (float(p["delta_F"]) < 1.3 * dfloor) == low]
            b.scatter([dt.datetime.utcfromtimestamp((int(p["roundId"]) + 1) * 172800) for p in ss],
                      [max(1.3 * dfloor, float(p["delta_F"])) for p in ss], s=11, marker="v" if low else "o",
                      facecolors=fc, edgecolors=hz.INK, linewidths=0.6, zorder=3)
    xs = np.array([floor, 2e8])
    for k, lab in ((1, r"$r=1$"), (0.1, r"$0.1$"), (0.01, r"$0.01$")):
        a.plot(xs, xs / k, color=hz.GUIDE, lw=0.7, ls=":", zorder=1)
        a.annotate(lab, xy=(0.55e8 * k, 0.62e8), fontsize=7, color="0.3", ha="right")
    a.set_xscale("log")
    a.set_yscale("log")
    a.set_xlim(floor, 2e8)
    a.set_ylim(1e6, 1e8)
    a.set_xlabel("open interest at the round's end (USDC)")
    a.set_ylabel("value of the capture stake (USD)")
    a.legend(frameon=False, loc="lower right", fontsize=7)
    hz.tag(a, "(a) the two sides")
    hz.style_ticklabels(a)
    # (b) per voting round: the loss of stake value a vote must impose before the tally rule's guarantee covers the
    # round's markets, OI / ((1 - 2 mu) V), when each market's payout vote was called (hollow) and when the round
    # ended (filled); standard-adapter markets with a payout vote (prize_growth.py)
    rows = [r for r in csv.DictReader(open(os.path.join(DATA, "prize_growth.csv"), encoding="utf-8"))
            if r["status"] == "ok" and r["negRisk"] not in ("True", "true", "1")]
    # each market's open interest over the participation pi of its first round (first_round_participation.py), so the
    # round's sum is the loss the limit delta (1 - 2 mu) pi V of Theorems 1 and 2 needs
    fpp = {(r["roundId"], r["requestTime"], r["ancKey"]): float(r["pi_first"])
           for r in csv.DictReader(open(os.path.join(DATA, "first_round_participation.csv"), encoding="utf-8"))}
    key = {(p["roundId"], p["conditionId"]): (p["roundId"], p["requestTime"], p["ancKey"]) for p in pts}
    rounds = {}
    for r in rows:
        w = fpp[key[(r["roundId"], r["conditionId"])]]
        g = rounds.setdefault(r["firstRound"], {"esc": 0.0, "end": 0.0, "V": float(r["V"]), "titles": []})
        g["esc"] += float(r["oi_esc"]) / w
        g["end"] += float(r["oi_first_end"]) / w
        g["titles"].append(r["title"])
    mu = 0.2
    lo = 1e-4
    for rid, g in sorted(rounds.items(), key=lambda kv: int(kv[0])):
        x = dt.datetime.utcfromtimestamp((int(rid) + 1) * 172800)
        y0, y1 = max(lo, g["esc"] / ((1 - 2 * mu) * g["V"])), max(lo, g["end"] / ((1 - 2 * mu) * g["V"]))
        b.plot([x, x], [y0, y1], color="0.55", lw=0.6, zorder=2)
        b.scatter([x], [y0], s=10, marker="o", facecolors="white", edgecolors=hz.INK, linewidths=0.6, zorder=3)
        b.scatter([x], [y1], s=11, marker="o", facecolors=hz.INK, edgecolors=hz.INK, linewidths=0.6, zorder=3)
    for y, lab in ((1.0, "the stake's whole value"), (0.14, "a 14% loss (scenario)"), (0.001, "the 0.1% penalty")):
        b.axhline(y, color=hz.GUIDE, lw=0.7, ls=":")
        b.annotate(lab, xy=(dt.datetime(2023, 8, 15), y * 1.12), fontsize=6.6, color="0.3", va="bottom")
    b.axvline(dt.datetime(2025, 4, 20), color=hz.GUIDE, lw=0.7, ls="--")
    cf = max(rounds.values(), key=lambda g: g["end"] / g["V"])
    cf_rid = next(k for k, g in rounds.items() if g is cf)
    b.annotate("Israel x Hezbollah ceasefire", xy=(dt.datetime.utcfromtimestamp((int(cf_rid) + 1) * 172800), cf["end"] / ((1 - 2 * mu) * cf["V"])),
               xytext=(dt.datetime(2025, 9, 1), 9.0), fontsize=6.8, color="0.2", ha="right", va="center",
               arrowprops=dict(arrowstyle="-", color="0.4", lw=0.6))
    b.set_yscale("log")
    b.set_ylim(lo, 40)
    b.set_xlim(dt.datetime(2023, 8, 1), dt.datetime(2026, 10, 15))
    b.set_ylabel(r"loss needed, $OI/((1-2\mu)\pi V)$")
    b.set_xlabel("voting round ended")
    b.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%Y"))
    b.xaxis.set_major_locator(plt.matplotlib.dates.YearLocator())
    hz.tag(b, "(b) vote called (o) and round ended (\u25cf)")
    hz.style_ticklabels(b)
    fig.tight_layout(w_pad=1.2)
    hz.save(fig, os.path.join(FIG, "fig_budget.pdf"))


def fig_ramp():
    """Tally settlement R_mu by mu: what it costs (share of 65%-era resolutions paid fractionally, bars) and what it
    protects (the payout a 10% stake can move, and the March 2025 YES payout with and without the three wallets)."""
    reqs = list(csv.DictReader(open(os.path.join(DATA, "requests_summary.csv"), encoding="utf-8")))
    era_b = [r for r in reqs if int(r["resolvedBlock"]) >= SPAT_CHANGE_BLOCK]
    rp = json.load(open(os.path.join(DATA, "ramp_replay.json")))
    f_with, f_without = rp["march"]["f_with"], rp["march"]["f_without"]
    rho = lambda f, mu: min(1.0, max(0.0, (f - mu) / (1 - 2 * mu)))
    mus = np.round(np.arange(0.05, 0.351, 0.05), 2)
    frac = [100 * sum(1 for r in era_b if float(r["modeShareOfVotes"]) < 1 - m) / len(era_b) for m in mus]
    shift = [100 * 0.1 / (1 - 2 * m) for m in mus]
    mw = [100 * rho(f_with, m) for m in mus]
    mwo = [100 * rho(f_without, m) for m in mus]
    fig, ax = plt.subplots(figsize=(3.45, 2.3))
    ax.bar(mus, frac, width=0.03, color=LIGHT, edgecolor=hz.INK, lw=0.6, label="resolutions paid less than in full, 65% era (%, left)")
    ax2 = ax.twinx()
    ax2.plot(mus, shift, color=hz.INK, lw=1.2, marker="s", ms=3.6, mfc="white", label="most a 10% stake moves a payout (cents)")
    ax2.plot(mus, mw, color=MID, lw=1.1, marker="o", ms=3.6, mfc="white", label="March YES payout, as voted (cents)")
    ax2.plot(mus, mwo, color=MID, lw=1.1, ls="--", marker="o", ms=3.6, mfc=MID, label="... without the three wallets")
    ax2.set_ylim(0, 100)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color("0.35")
    ax2.grid(False)
    ax.set_ylim(0, max(frac) * 1.35)
    ax.set_xlabel(r"$\mu$")
    ax.set_ylabel("paid less than in full (%)")
    ax2.set_ylabel("cents per share")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=1, fontsize=6.6)
    hz.style_ticklabels(ax)
    hz.style_ticklabels(ax2)
    hz.save(fig, os.path.join(FIG, "fig_ramp.pdf"))


def fig_rule():
    """What a disputed question pays YES holders as a function of YES's share of the votes cast (two answers, full
    participation): the deployed rule (theta = 0.5 in March 2025: a step, nothing is settled while the request rolls),
    proportional settlement (mu = 0) and tally settlement with mu = 0.2, with the March 2025 vote as cast. Without the
    three wallets the first round's modal answer was "too early", and tally settlement would have asked again."""
    rp = json.load(open(os.path.join(DATA, "ramp_replay.json")))
    f_with = rp["march"]["f_with"]
    mu = 0.2
    rho = lambda f: min(1.0, max(0.0, (f - mu) / (1 - 2 * mu)))
    fig, ax = plt.subplots(figsize=(3.45, 2.25))
    xs = np.linspace(0, 1, 401)
    ax.plot(xs, [rho(x) for x in xs], color=hz.INK, lw=1.4, label=r"tally settlement, $\mu = 0.2$")
    ax.plot([0, 1], [0, 1], color=MID, lw=1.0, ls="-.", label=r"proportional, $\mu = 0$")
    # deployed rule, theta = 0.5 against the votes cast with full participation: NO below 0.5, YES above
    ax.plot([0, 0.5], [0, 0], color=MID, lw=1.4, ls="--", label="deployed rule (March 2025)")
    ax.plot([0.5, 1], [1, 1], color=MID, lw=1.4, ls="--")
    ax.plot([0.5, 0.5], [0, 1], color=MID, lw=0.8, ls=":")
    ax.plot([f_with], [rho(f_with)], marker="o", ms=4.5, mfc=hz.INK, mec=hz.INK, zorder=4)
    ax.annotate("March 2025, as voted:\n%.2f a share" % rho(f_with), xy=(f_with, rho(f_with)),
                xytext=(0.60, 0.30), fontsize=7, color="0.2", arrowprops=dict(arrowstyle="-", color="0.5", lw=0.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.03, 1.05)
    ax.set_xlabel("YES share of the votes cast")
    ax.set_ylabel("paid to a YES share (USD)")
    ax.legend(frameon=False, loc="upper left", fontsize=7)
    hz.style_ticklabels(ax)
    hz.save(fig, os.path.join(FIG, "fig_rule.pdf"))


if __name__ == "__main__":
    fig_march()
    fig_winner_share()
    fig_fallback()
    fig_budget()
    fig_ramp()
    fig_rule()
    print("figures written to", FIG)
