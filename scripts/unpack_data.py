"""Extract the three release data archives into this checkout."""
from pathlib import Path
import argparse
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = (ROOT / 'research_ideas/probes/oracle_capture/data').resolve()
NAMES = ['oracle-capture-votes.zip', 'oracle-capture-events.zip', 'oracle-capture-caches.zip']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('directory', type=Path)
    args = ap.parse_args()
    for name in NAMES:
        source = args.directory / name
        if not source.is_file():
            raise SystemExit(f'Missing {source}')
        with zipfile.ZipFile(source) as archive:
            for entry in archive.infolist():
                target = (ROOT / entry.filename).resolve()
                if not target.is_relative_to(DATA):
                    raise ValueError(f'Archive member outside the data directory: {entry.filename}')
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry) as src, target.open('wb') as dst:
                        shutil.copyfileobj(src, dst)
        print(f'Extracted {name}', flush=True)


if __name__ == '__main__':
    main()
