# Scope of computational evidence

The distributed scripts preserve the distinction between finite exact checks,
symbolic identities, numerical discovery, and execution against deployed code.
The authors' verification ledger remains in their research workspace. The
artifact does not create a second ledger or automatically issue credentials.

| Script | Scope |
| --- | --- |
| `participation_checks_20261008.py` | Current participation-dependent tally range and construction instances; exact integer/rational enumeration over the script's finite grids |
| `participation_sympy_20261008.py` | Symbolic identities for the participation-scaled construction, round budget and payout width |
| `honest_electorate_probe.py` | Finite-grid capture/block/fallback thresholds, including the denominator distinction |
| `tally_rules_probe.py` | Finite instances of the earlier tally-rule formulation; inspect later honest-electorate and revision checks before interpreting it |
| `ramp_probe.py` | Earlier full-participation case and rational self-financing examples; the current paper includes participation explicitly |
| `capture_probe.py` E1–E6 | Accounting identities and finite examples; its hard-coded March example is the first-dispute/bond request, not the later payout request |
| `capture_probe.py` E7 | Floating-point noisy-game exploration; not a universal theorem credential |
| `review*_checks_*.py`, `remarks_check.py` | Calculations attached to the corresponding revision; source comments define their scope |
| `variant_probe.py` | Finite instances of an exploratory fallback variant |
| `dvm_port.py` | Integer rounding and slashing replay against historical event records |
| Solidity unit tests | Research prototype behavior, including bridge sender checks and bounded fuzz tests |
| Solidity fork tests | Named historical requests on local forks, with the stated counterfactual interventions |

The earlier March numbers and full-participation formulas are retained as
historical inputs. They must not be described as validation of a different
request or of a participation-free version of the current theorem. The paper's
numbers are generated from the current payout-vote summaries.

`--record` was an author-workspace integration for a shared ledger. It is
disabled with an explicit error in the distributed scripts; omitting it runs
the same calculation. No calculation relies on that ledger integration.

## Replay of the market-referenced fallback (Appendix B of the paper)

$F_\mu$ at $\mu = 0.2$ moves 18 Polymarket votes that decided a payout, in 17 markets; a market voted on twice counts once, by its later vote, and the reference price is the hourly mean of Yes over the 24 hours before the request reached the vote. 7 resolved "too early" and 10 Yes or No. In 4 of the 10 the vote's winner had been priced below one half before the dispute, March 2025 among them; where the vote confirmed the market, $F_\mu$ costs the winners a median of 10 cents a share. These numbers stood in Appendix B of the paper until 2026-10-09 and now live here; they are the `replay*` keys of the paper's `numbers.json`, produced by the fallback replay script of the probes directory.

## Gas of the prototype

`TallyRootTunnel` and `TallyChildTunnel` carry the tally share of Section 5 of the paper as one more state-sync message through the FxPortal interfaces that UMA's oracle tunnel already uses; six tests run the path end to end with a mock bridge and check who may send. The relay's figure includes the mock bridge delivering to the child in the same transaction, which the real state sync does asynchronously, and the mock-based figure for the votes-cast reader omits the cold-storage reads of the live contract. The market-referenced adapter of Appendix B costs 54,246 gas on every fill for its price accumulator.

Gas of the prototype (Foundry 1.8.5, solc 0.8.24, optimizer 200 runs); `python reproduce.py unit` reruns the tests.

| Call | Gas | When |
|---|---:|---|
| register (MarginReader, mainnet fork) | 102,204 | per disputed request |
| register (votes cast, mock) | 61,304 | per disputed request |
| settle, undisputed (TallyAdapter) | 129,404 | per question |
| settle, paid in full | 135,819 | per question |
| settle, paid below full | 155,719 | per question |
| relay (TallyRootTunnel, mock bridge) | 88,434 | per disputed request |
| receive (TallyChildTunnel) | 24,528 | per disputed request |
