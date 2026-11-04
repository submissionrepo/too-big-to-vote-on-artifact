# Packaging execution record, 2026-10-09

The commands below were executed in an independent artifact directory.
Python dependencies were installed from `requirements.txt` into a new Python
3.11 virtual environment. Historical theorem credentials were not reissued.

| Execution | Observed result | Log |
| --- | --- | --- |
| Paper numbers | All 517 macros equal the source manuscript | `paper_numbers.log` |
| Data figures | All figure routines completed | `paper_figures.log` |
| Current participation enumeration | Script reports `all_pass: true` | `participation_checks_20261008.log` |
| Current symbolic identities | Script reports `all_pass: true` | `participation_sympy_20261008.log` |
| Solidity unit tests | 30 passed, 0 failed, 0 skipped; includes 256 fuzz runs | `contracts_unit.log` |
| March fork replay | 5 passed, 0 failed, 0 skipped | `fork_march.log` |
| Ceasefire two-chain replay | 2 passed, 0 failed, 0 skipped | `fork_ceasefire.log` |
| Blocking/deletion two-chain replay | 1 passed, 0 failed, 0 skipped | `fork_block.log` |
| Complete vote-table analysis | Census, answer tallies, participation, budget and tally replay completed; all 517 regenerated macros still match | The five named analysis logs |
| Manuscript build | `latexmk -pdf paper.tex` completed; 18 pages | Rebuild from the included source |
| Release data unpacking | All three ZIP archives extracted successfully | Re-run `scripts/unpack_data.py` |

Fork execution used Foundry 1.8.5, solc 0.8.24, the included fixtures, and the
public Ethereum/Polygon Tenderly archive gateways. Foundry may reuse its local
RPC cache. The commands exercised the independent package layout; they were
not an independent reimplementation of the experiments.

Local filesystem prefixes have been replaced by `ARTIFACT_ROOT` in the copied
logs. The research workspace's shared ledger records this as an artifact
portability run, separate from the original checks of the mathematical claims.
