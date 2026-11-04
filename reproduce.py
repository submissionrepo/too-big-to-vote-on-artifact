"""Run the artifact's offline calculations, local contract tests, or fork replays."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
PROBES = ROOT / 'research_ideas/probes/oracle_capture'
PAPER = ROOT / 'research_ideas/oracle_capture_paper/tex'
OUT = ROOT / 'outputs'


def run(name, command, cwd=ROOT):
    OUT.mkdir(exist_ok=True)
    start = time.monotonic()
    print(f'Running {name}', flush=True)
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', MPLBACKEND='Agg')
    with (OUT / (name + '.log')).open('w', encoding='utf8') as log:
        result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                                stdout=log, stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - start
    print(f'{name}: exit {result.returncode}, {elapsed:.1f}s; outputs/{name}.log', flush=True)
    if result.returncode:
        print((OUT / (name + '.log')).read_text(encoding='utf8')[-6000:])
        raise SystemExit(result.returncode)


def python_script(name):
    run(Path(name).stem, [sys.executable, PROBES / name])


def paper():
    original = json.loads((PAPER / 'numbers.json').read_text(encoding='utf8'))
    run('paper_numbers', [sys.executable, PAPER / 'make_numbers.py'])
    regenerated = json.loads((PAPER / 'numbers.json').read_text(encoding='utf8'))
    changes = {k: (original.get(k), regenerated.get(k)) for k in original.keys() | regenerated.keys()
               if original.get(k) != regenerated.get(k)}
    if changes:
        raise SystemExit('Paper number differences: ' + json.dumps(changes, ensure_ascii=False))
    print(f'All {len(original)} paper numbers match.', flush=True)
    run('paper_figures', [sys.executable, PAPER / 'make_figures.py'])


def checks():
    for script, output, field in [
        ('participation_checks_20261008.py', 'participation_checks_20261008.json', 'all_pass'),
        ('participation_sympy_20261008.py', 'participation_sympy_20261008.json', 'all_pass'),
    ]:
        python_script(script)
        result = json.loads((PROBES / 'data' / output).read_text())
        if result.get(field) is not True:
            raise SystemExit(f'{script}: result field {field} is not true')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    tasks = ['paper', 'checks', 'unit', 'forks', 'march', 'ceasefire', 'block', 'analysis']
    parser.add_argument('tasks', nargs='*', metavar='TASK', help='Tasks: ' + ', '.join(tasks))
    parser.add_argument('--forge', default=shutil.which('forge'), help='Path to the forge executable')
    args = parser.parse_args()
    for task in args.tasks:
        if task not in tasks:
            parser.error(f'Unknown task {task!r}; choose from ' + ', '.join(tasks))
    for task in args.tasks or ['paper', 'checks']:
        if task == 'paper':
            paper()
        elif task == 'checks':
            checks()
        elif task == 'analysis':
            if not (PROBES / 'data/votes_long.csv').is_file():
                raise SystemExit('Download the release data and run scripts/unpack_data.py first.')
            for script in ['analyze_requests.py', 'answer_tallies.py', 'first_round_participation.py',
                           'capture_economics_summary.py', 'ramp_replay.py']:
                python_script(script)
            paper()
        else:
            if not args.forge:
                raise SystemExit('Foundry is required. Install forge or supply --forge PATH.')
            base = [args.forge, 'test', '-vv', '--gas-limit', '1000000000000']
            if task == 'unit':
                run('contracts_unit', base + ['--no-match-path', 'test/*.fork.t.sol'], PROBES / 'prototype')
                continue
            required = ['FORK_URL'] + ([] if task == 'march' else ['POLYGON_URL'])
            for key in required:
                if not os.environ.get(key):
                    raise SystemExit(f'Set {key} to an archive RPC URL before requesting {task}.')
            suites = {'march': 'MarchReplay.fork.t.sol', 'ceasefire': 'CeasefireCapture.fork.t.sol',
                      'block': 'BlockToDeletion.fork.t.sol'}
            selected = list(suites) if task == 'forks' else [task]
            for suite in selected:
                run('fork_' + suite, base + ['--match-path', 'test/' + suites[suite]], PROBES / 'prototype')


if __name__ == '__main__':
    main()
