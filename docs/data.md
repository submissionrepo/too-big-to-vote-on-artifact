# Data and acquisition

The repository contains public on-chain observations and public API responses
used in the paper. Wallet-to-trader linkage outputs from the separate exploratory
analysis, user-specific trade-history caches, disclosure correspondence, and
credentials are excluded. No signing key is required or distributed.

## Included and released data

| Package | Contents |
| --- | --- |
| Git checkout | Per-request and market summaries, daily/minute prices, the March decoded tally, proof/analysis outputs, all Solidity replay fixtures, selected successful logs |
| `oracle-capture-votes.zip` | Full decoded vote table and the later concentration snapshot |
| `oracle-capture-events.zip` | Five raw VotingV2 event segments, resolved-request logs, March slashing events, Polygon redemption logs, round cache and fetch progress |
| `oracle-capture-caches.zip` | Public market, trade, price, transaction and event caches consumed by the acquisition scripts |

Download from the repository's `artifact-2026-11` Release and run
`python scripts/unpack_data.py downloads`. ZIP paths are relative to this
repository; the extractor accepts only members under the data directory.
The original filenames inside the data directory are retained because scripts
use them as input names and cache keys.

## Re-fetching chain events

The study reads Ethereum VotingV2 at
`0x004395edb43EFca9885CEdad51EC9fAf93Bd34ac`, deployed in March 2023, and
Polygon conditional-token, adapter and oracle-tunnel contracts. Exact addresses
and historical fork blocks are in the acquisition scripts and replay fixtures.

Each `data/raw/fetch_state_<tag>.json` records a segment's last processed block
and fixed end block. Read those stored values to reproduce the historical
census; using `latest` intentionally creates a new census. `fetch_votingv2_logs.py`
supports explicit block bounds and a filename tag:

```sh
python research_ideas/probes/oracle_capture/fetch_votingv2_logs.py FROM_BLOCK TO_BLOCK TAG
python research_ideas/probes/oracle_capture/summarize_votes.py
python research_ideas/probes/oracle_capture/analyze_requests.py
```

The supplied segments have observed event-block ranges 16,697,232–19,399,792
(`a`), 19,400,361–22,799,972 (`b`), 22,800,023–24,500,000 (`c1`),
24,500,026–25,766,636 (`c2`), and 25,400,002–26,133,616 (`c3`). The `c2`
fetch was interrupted; `c3` overlaps it and finishes the census. The decoder
deduplicates event identities across files. For a single new acquisition use
blocks 16,000,000 through **26,133,617** and a new tag in an empty raw-data
directory; do not combine that new full-range dump with the five supplied files.

The fetcher is resumable. Use a new tag in a fresh data directory when starting
from scratch; do not append a second copy of a segment to the supplied event
history. `LOG_ENDPOINT` can select an archive endpoint instead of the public
fallback list. Historical state calls require a provider that serves the
requested block; latest-state-only endpoints are insufficient.

The summarizer's current-staker snapshot uses live calls. Re-fetching that
snapshot later changes concentration and “today's top holders” figures. The
supplied `voters_current.csv`, `delegates_current.csv`, `concentration.json` and
later quick-tally snapshot retain the study's original observation. The offline
reproduction command uses those supplied values.

## Markets, prices and exposure

`pm_markets.py` matches requests to markets by question/condition identifiers
and handles the title-based neg-risk fallback. Public services are Polymarket's
Gamma, CLOB and data APIs, Coinbase daily price candles, and DefiLlama daily
token prices. These endpoints can change, rate-limit queries, or stop serving
historical responses. The included public response caches preserve the inputs
used for the reported measurements.

The main acquisition order is:

1. `fetch_votingv2_logs.py`, then `summarize_votes.py` and `analyze_requests.py`.
2. `map_polygon_disputes.py`, `replay_fallback.py`, and `capture_economics.py`.
3. `request_roles.py` and the payout-vote selection in `payout_votes.py`.
4. `prize_growth.py`, `executable_profit.py`, `reveal_leak.py`,
   `march_stake_history.py`, `march_trades.py`, `ceasefire_instance.py`,
   `undisputed_control.py`, and `delta_event_study.py`.
5. `capture_economics_summary.py`, `ramp_replay.py`, then `reproduce.py paper`.

The artifact's default command starts from the supplied derived inputs. A full
fresh acquisition is a separate operation and can be slow on public RPCs.

## Fork fixtures

Every calldata binary required by the fork tests is included in Git, including
the block and ceasefire subdirectories. The corresponding `build_*_fixture.py`
scripts can regenerate them from archive RPC. `build_ceasefire_fixture.py
--split` writes the per-transaction calldata files. These are local simulation
inputs: the test harness impersonates historical senders on local forks.

The capture replay bridges Ethereum's resulting message into Polygon through
the test harness's system-call simulation. The blocked request's later voting
rounds are constructed from the historical first-round electorate. These
choices are part of the experiment, not observations of live attacks.
