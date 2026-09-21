#!/usr/bin/env python3
"""
Prove that the Linux changes cannot affect Windows.

Resolves every {$IFDEF WINDOWS} / {$IFNDEF WINDOWS} block as a Windows compiler
would, leaving all other conditionals untouched, and diffs the result against the
same resolution of the upstream file. A clean run means the Windows build sees a
byte-for-byte identical script -- so no PR from this branch can regress Windows.

    linux/windows-parity-check.py [--base upstream/main] ["B.A.S.H Launcher.simba"]

Exit 0 = Windows-side identical. Exit 1 = a real Windows-visible change.
"""
import argparse, difflib, re, subprocess, sys, pathlib

DIRECTIVE = re.compile(r'^\s*\{\$(IFDEF|IFNDEF|ELSE|ENDIF|ELSEIFDEF)\b\s*([A-Za-z0-9_]*)\s*\}\s*$',
                       re.IGNORECASE)
# A WINDOWS conditional sharing a line with code would make this resolver lie.
INLINE_WIN = re.compile(r'\{\$IF(N?)DEF\s+WINDOWS\s*\}', re.IGNORECASE)


def resolve_windows(text: str, origin: str) -> str:
    """Return `text` as the Windows compiler sees it."""
    out, stack = [], []   # stack entries: None (foreign) or bool (emit this branch)
    for lineno, line in enumerate(text.split('\n'), 1):
        m = DIRECTIVE.match(line)
        if not m:
            if INLINE_WIN.search(line):
                sys.exit(f'{origin}:{lineno}: inline WINDOWS conditional, cannot resolve safely:\n  {line}')
            if all(s is not False for s in stack):
                out.append(line)
            continue

        kind, sym = m.group(1).upper(), m.group(2).upper()
        if kind in ('IFDEF', 'IFNDEF'):
            if sym == 'WINDOWS':
                # WINDOWS is defined, so {$IFDEF WINDOWS} takes its first branch
                # and {$IFNDEF WINDOWS} takes its {$ELSE}.
                stack.append(kind == 'IFDEF')
            else:
                stack.append(None)   # foreign conditional: pass through verbatim
        elif kind == 'ELSE':
            if stack and stack[-1] is not None:
                stack[-1] = not stack[-1]
            elif all(s is not False for s in stack[:-1]):
                out.append(line)
            continue
        elif kind == 'ENDIF':
            popped = stack.pop() if stack else None
            if popped is None and all(s is not False for s in stack):
                out.append(line)
            continue
        else:
            sys.exit(f'{origin}:{lineno}: {{$ELSEIFDEF}} is not handled by this checker')

        # emit the directive line itself only for foreign conditionals
        if stack[-1] is None and all(s is not False for s in stack[:-1]):
            out.append(line)
    return '\n'.join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='upstream/main', help='git ref to compare against')
    ap.add_argument('path', nargs='?', default='B.A.S.H Launcher.simba')
    a = ap.parse_args()

    current = pathlib.Path(a.path).read_text(encoding='utf-8', errors='surrogateescape')
    base = subprocess.run(['git', 'show', f'{a.base}:{a.path}'],
                          capture_output=True, check=True).stdout.decode('utf-8', 'surrogateescape')

    win_base = resolve_windows(base, a.base)
    win_head = resolve_windows(current, a.path)

    if win_base == win_head:
        kept = len(win_head.split('\n'))
        print(f'OK  Windows-resolved output is identical to {a.base} ({kept} lines).')
        print(f'    Linux-only delta: {len(current.splitlines()) - len(base.splitlines()):+d} lines in the source.')
        return 0

    print(f'WINDOWS-VISIBLE CHANGE vs {a.base} -- this would ship to Windows users:\n')
    print('\n'.join(difflib.unified_diff(
        win_base.split('\n'), win_head.split('\n'),
        fromfile=f'{a.base} (windows)', tofile=f'{a.path} (windows)', lineterm='', n=3)))
    return 1


if __name__ == '__main__':
    sys.exit(main())
