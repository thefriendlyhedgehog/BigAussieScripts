#!/usr/bin/env python3
"""
Un-gate the script GUI on Linux.

BigAussie's scripts open with:

    {$IFDEF WINDOWS}{$DEFINE SCRIPT_GUI}{$ENDIF}

so `BashLib/optional/handlers/bashgui.simba` is only included on Windows. But the
scripts then reference symbols that file declares -- ENABLEWEBHOOKS, WEBHOOKURL --
*outside* any {$IFDEF SCRIPT_GUI} guard. On Linux those symbols do not exist, so the
script does not compile:

    Unknown declaration "ENABLEWEBHOOKS" at line 3616 ...

bashgui.simba itself compiles fine on Linux, so the gate is an unnecessary
restriction rather than a workaround for anything. Removing it both fixes the build
and gives Linux users the script GUI they would otherwise lose entirely.

    linux/fix-scripts.py [SIMBA_DIR] [--verify]

--verify compiles every patched script afterwards. Note Simba aborts at process exit
regardless (see README, `free(): invalid pointer`), so success is detected from the
compiler's own output, not the exit code.
"""
import os, pathlib, subprocess, sys

GATE = '{$IFDEF WINDOWS}{$DEFINE SCRIPT_GUI}{$ENDIF}'
UNGATED = '{$DEFINE SCRIPT_GUI}   // Linux: bashgui compiles here too, and scripts use its globals unguarded'


def compiles(simba: pathlib.Path, script: pathlib.Path) -> bool:
    try:
        r = subprocess.run([str(simba / 'Simba'), '--compile', str(script)],
                           capture_output=True, text=True, timeout=300,
                           # Inherit the environment; Simba needs more than DISPLAY
                           # (XAUTHORITY, and it resolves AppPath from its own path).
                           env={**os.environ, 'DISPLAY': os.environ.get('DISPLAY', ':0')},
                           cwd=str(simba))
    except subprocess.TimeoutExpired:
        return False
    return 'uccesfully compiled' in (r.stdout + r.stderr)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    verify = '--verify' in sys.argv
    simba = pathlib.Path(args[0] if args else pathlib.Path.home() / 'Simba')
    scripts = simba / 'Scripts'
    if not scripts.is_dir():
        print(f'no Scripts directory under {simba}', file=sys.stderr)
        return 1

    patched, already = [], []
    for path in sorted(scripts.rglob('*.simba')):
        text = path.read_text(encoding='utf-8', errors='surrogateescape')
        if UNGATED in text:
            already.append(path)
            continue
        if GATE not in text:
            continue
        backup = path.with_suffix(path.suffix + '.upstream')
        if not backup.exists():
            backup.write_text(text, encoding='utf-8', errors='surrogateescape')
        path.write_text(text.replace(GATE, UNGATED, 1),
                        encoding='utf-8', errors='surrogateescape')
        patched.append(path)
        print(f'  ungated  {path.relative_to(scripts)}')

    print(f'\n{len(patched)} patched, {len(already)} already done.'
          f'{"  Originals kept as *.upstream." if patched else ""}')

    # Verify everything currently in the ungated state, not just this run's edits.
    targets = patched + already
    if verify and targets:
        print('\nCompiling (exit codes are unreliable; reading compiler output):')
        bad = 0
        for path in targets:
            ok = compiles(simba, path)
            print(f'  {"OK  " if ok else "FAIL"}  {path.relative_to(scripts)}')
            bad += 0 if ok else 1
        print(f'\n{len(targets) - bad}/{len(targets)} compile.')
        return 1 if bad else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
