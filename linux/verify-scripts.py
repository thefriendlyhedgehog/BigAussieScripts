#!/usr/bin/env python3
"""
Compile every installed script and report what builds on Linux.

Failures are grouped by their error, because the useful signal is the pattern:
one error hitting thirty scripts is a single Linux fix, while thirty distinct
errors are thirty rotted scripts.

    linux/verify-scripts.py [SIMBA_DIR] [--jobs N] [--only SUBSTR]

Notes:
  - Exit codes are unreliable: Simba aborts at teardown regardless (see README,
    `free(): invalid pointer`), so success is read from the compiler's output.
  - The environment must be inherited; a stripped env makes every script report a
    false failure.
"""
import argparse, collections, os, pathlib, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

SKIP_SUFFIXES = ('.upstream', '.prepatch', '.preheightfix', '.orig')
SKIP_NAMES = {'default.simba', 'bash-launcher.simba', 'BashLauncher.simba'}
OK = 'uccesfully compiled'


def classify(out: str) -> str:
    """Reduce compiler output to one comparable error label."""
    m = re.search(r'Unknown declaration "([^"]+)"', out)
    if m:
        return f'Unknown declaration "{m.group(1)}"'
    for pat in (r'^(.*?Exception.*)$', r'^(Error:.*)$', r'^(.*\bexpected\b.*)$'):
        m = re.search(pat, out, re.M)
        if m:
            return re.sub(r'\s+at line \d+.*', '', m.group(1)).strip()[:90]
    return 'unknown failure'


def compile_one(simba: pathlib.Path, script: pathlib.Path):
    try:
        r = subprocess.run([str(simba / 'Simba'), '--compile', str(script)],
                           capture_output=True, text=True, timeout=400,
                           env={**os.environ, 'DISPLAY': os.environ.get('DISPLAY', ':0')},
                           cwd=str(simba))
        out = r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return script, False, 'timeout'
    return script, OK in out, '' if OK in out else classify(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('simba_dir', nargs='?', default=str(pathlib.Path.home() / 'Simba'))
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--only', default='')
    a = ap.parse_args()

    simba = pathlib.Path(a.simba_dir)
    scripts_dir = simba / 'Scripts'
    targets = sorted(p for p in scripts_dir.rglob('*.simba')
                     if not p.name.endswith(SKIP_SUFFIXES)
                     and p.name not in SKIP_NAMES
                     and a.only.lower() in str(p).lower())
    if not targets:
        print('no scripts found', file=sys.stderr)
        return 1

    print(f'Compiling {len(targets)} scripts with {a.jobs} workers...\n', flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for i, (path, ok, err) in enumerate(
                ex.map(lambda p: compile_one(simba, p), targets), 1):
            results.append((path, ok, err))
            print(f'  [{i:3}/{len(targets)}] {"OK  " if ok else "FAIL"}  '
                  f'{path.relative_to(scripts_dir)}', flush=True)

    good = [r for r in results if r[1]]
    bad = [r for r in results if not r[1]]
    print(f'\n{len(good)}/{len(results)} compile.\n')

    if bad:
        groups = collections.defaultdict(list)
        for path, _, err in bad:
            groups[err].append(path.relative_to(scripts_dir))
        print('Failures grouped by error (most common first):\n')
        for err, paths in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            print(f'  [{len(paths):3}]  {err}')
            for p in sorted(paths)[:6]:
                print(f'          {p}')
            if len(paths) > 6:
                print(f'          ... and {len(paths) - 6} more')
            print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
