# Too Big to Vote On: research artifact

Code, decoded data, supplementary proofs, and local-fork experiments for the
paper **Too Big to Vote On**. The reference manuscript is the November 2026 version; observation dates are recorded with the datasets.

## Start here

Use Python 3.11 or newer. The dependency versions below are the versions tested
when packaging the artifact. No blockchain account or signing key is needed.

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python reproduce.py
```

The default command runs offline: it regenerates the paper's numerical macros,
three generated tables and data figures, compares the numerical macros with the
included manuscript's numbers, and runs the current participation calculations.
Output is written under `research_ideas/oracle_capture_paper/tex/` and logs under
`outputs/`. It fails if a command fails or the regenerated numbers differ.
The first exact enumeration takes a few minutes on a laptop.

The repository retains the original `research_ideas/` layout so that script
imports and relative data paths are the same across the research workspace and
this independent checkout. It has no dependency on the authors' workspace.

| Material | Location |
| --- | --- |
| Scripts and decoded per-request summaries | `research_ideas/probes/oracle_capture/` |
| Solidity prototypes, tests and all replay fixtures | `research_ideas/probes/oracle_capture/prototype/` |
| Manuscript, generated numbers and figure scripts | `research_ideas/oracle_capture_paper/tex/` |
| Proofs referred to the artifact | [docs/proofs.md](docs/proofs.md) |
| Figure/table-to-command map | [docs/reproduction.md](docs/reproduction.md) |
| Data sources and complete re-fetch instructions | [docs/data.md](docs/data.md) |
| Interpretation of computational checks | [docs/computational_evidence.md](docs/computational_evidence.md) |
| Third-party source and license information | [THIRD_PARTY.md](THIRD_PARTY.md) |

## Contract tests

Install Foundry; the preparation environment uses **Foundry 1.8.5** and
**Solidity 0.8.24**, optimizer 200 runs, Cancun EVM. `forge-std` is included.

```sh
python reproduce.py unit
```

Fork tests require Ethereum and Polygon archive JSON-RPC URLs. Set `FORK_URL`
and `POLYGON_URL` in the process environment, then run:

```sh
python reproduce.py forks
```

The wrapper refuses to count a missing RPC URL as a successful fork run.
Tests run on local forks. They send no transaction to a live chain.
Use `python reproduce.py --help` for individual suites and `--forge` to supply
the executable path. Blocking-to-deletion can take tens of minutes on public RPC.

## Full data

Small summaries and fixtures are included in Git. Large vote-level tables,
raw chain events, and public API caches are attached to the **artifact-2026-11**
GitHub Release in this repository:

```sh
gh release download artifact-2026-11 --repo submissionrepo/too-big-to-vote-on-artifact --pattern 'oracle-capture-*.zip' --dir downloads
python scripts/unpack_data.py downloads
python reproduce.py analysis
```

Download the assets above, or
use the GitHub Release page to save the three ZIP files. The unpacking command
also works on files downloaded in the browser. After extraction, allow about
8 GB of free disk space in addition to the downloaded archives.

`analysis` regenerates the principal derived measurements from the supplied
vote table and source caches. Some acquisition scripts deliberately contact
public services; see [docs/data.md](docs/data.md) before re-fetching.

## Manuscript

```sh
python reproduce.py paper
cd research_ideas/oracle_capture_paper/tex
latexmk -pdf paper.tex
```

The conceptual diagram PDF is included with its standalone TikZ source. Changes
to that diagram can be compiled with `latexmk -pdf fig_flow.tex` in `figures/`.
The data figures use the included `hz_figstyle.py`: serif, grayscale, vector PDF.

The manuscript's theorems and proofs are research claims. Finite enumerations
and historical contract replay establish the documented instances; they do not
turn all mathematical statements into machine-checked theorems. The packaging
work does not issue a new proof-review credential.
## Public package

Repository: https://github.com/submissionrepo/too-big-to-vote-on-artifact

The release contains a ZIP of this repository.
Original code and documentation are available under the [MIT License](LICENSE). Third-party components retain their own licenses. Source credits and third-party terms are in [THIRD_PARTY.md](THIRD_PARTY.md) and [docs/data.md](docs/data.md).

Large inputs are the three `oracle-capture-*.zip` data assets of the same release. Unpack them with `scripts/unpack_data.py` before running `reproduce.py analysis`. Account profile names, biographies and profile images are removed from public trade responses; numerical fields and pseudonymous on-chain identifiers used by the scripts are retained.
