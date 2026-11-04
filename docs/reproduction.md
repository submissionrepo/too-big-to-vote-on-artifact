# Reproduction map

Run commands from the repository root. `P` below denotes
`research_ideas/probes/oracle_capture/`; scripts locate their data relative to
their own file, so the shell's working directory does not change the inputs.

| Paper component | Primary inputs | Command or source |
| --- | --- | --- |
| Every numerical macro and generated table | Included CSV/JSON summaries, March fixture, successful fork log | `python reproduce.py paper` |
| Winner-share, March timeline, budget and mitigation figures | Included request summaries, prices, March vote detail and replay summaries | `python reproduce.py paper` |
| Census, contested requests, pivotality | `data/votes_long.csv`, `data/requests_summary.csv` | `python P/analyze_requests.py` |
| Vote participation and answer splits | Vote-level table and first-round tallies | `python P/answer_tallies.py`; `python P/first_round_participation.py` |
| Votes deciding payouts vs first-dispute bonds | Request summaries and exact request/market mapping; cached transactions | `python P/request_roles.py`; shared `payout_votes.py` |
| Security-budget measurements | `capture_economics.csv`, token prices, payout request roles | `python P/capture_economics_summary.py` |
| Tally-settlement replay, participation adjustment and per-round cap | Request tallies, market measurements, first-round participation | `python P/ramp_replay.py` |
| Prize growth during the vote | Polygon split/merge events and escalation transaction cache | `python P/prize_growth.py` |
| Ceasefire counterfactual trade exposure | Public market trades and historical voting stake | `python P/ceasefire_instance.py` |
| Executable exposure and reveal timing | Market trades and minute prices; public caches | `python P/executable_profit.py`; `python P/reveal_leak.py` |
| Event study | Public daily token-price cache | `python P/delta_event_study.py` |
| Slashing arithmetic port | Raw VoterSlashed events, March tallies | `python P/dvm_port.py` |
| Current participation calculations | Exact rational finite enumeration and symbolic identities | `python reproduce.py checks` |
| March deployed-contract replay | `prototype/fixtures/march_reveals.json` | `python reproduce.py march` |
| Ceasefire two-chain capture and redemption | Ceasefire metadata, calldata and Polygon fixtures | `python reproduce.py ceasefire` |
| Blocking, repeated rolls, deletion and admin settlement | Block metadata and calldata fixtures | `python reproduce.py block` |
| Reader, adapters, bridge and gas | Solidity sources, included forge-std | `python reproduce.py unit` |
| Five proofs moved out of the paper | Stored manuscript proofs, same statements and notation | `docs/proofs.md` |

Replace `P/` with the full path when copying an individual script command.
`python reproduce.py analysis` runs the offline analysis rows together and then
rebuilds the paper outputs. Acquire and unpack the release assets first.

## Expected observations

The included data contain 5,004 resolved requests and 2,345,534 revealed votes
in resolving rounds; the all-round count is 2,374,174. The current paper filters
the Polymarket measurements to the votes that decide a payout: the first
dispute's DVM vote can decide bonds while the adapter has already re-asked the
question. Do not substitute the earlier all-dispute counts for this population.

The March suite contains five tests: the historical reveals resolve the request,
and removing any one of the three wallets, or all three, makes it roll. The
ceasefire suite contains two tests: the historical outcome and the captured
outcome. In the latter the listed holders redeem 18,387,097.729849 USDC.e. This
is distinct from the 58.31 million counterfactual shares estimated from trades.
The blocking suite replays the first round and constructs later rounds until
deletion, then exercises Polygon's administrator settlement path.

Original successful fork logs from 2026-10-08 are included in `P/data/raw/`.
They remain historical evidence. Any execution during packaging is documented
separately in `evidence/`; a missing RPC URL must never be counted as a replay.

## Resources and boundaries

Offline figure generation is small. Decoding the complete raw event history
can take several GB of memory; the original summarizer holds events and votes
in memory. The supplied decoded tables avoid requiring that initial decoding
to inspect the paper. Public archive RPC latency dominates fork runtime.

The proof supplement is a transcription, not an independent proof audit.
Legacy probes and revision-era checks are included for provenance. Only the
current participation scripts are selected by the default check command.
