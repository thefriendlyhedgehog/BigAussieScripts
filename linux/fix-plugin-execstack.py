#!/usr/bin/env python3
"""
Make Simba's RemoteInput plugin loadable on a modern glibc.

libremoteinput64.so ships with PT_GNU_STACK marked RWE -- it asks the loader for
an executable stack. Since glibc 2.41 dlopen refuses that request outright rather
than silently granting it, so the plugin fails to load:

    dlopen: cannot enable executable stack as shared object requires

Simba reports this through its generic plugin-load path as the much more
misleading:

    Loading plugin failed. Architecture mismatch? (expected a 64 bit plugin)

The binary is a perfectly good x86-64 ELF; nothing is mismatched. The RWE marking
is the usual artefact of hand-written assembly built without a .note.GNU-stack
section (the plugin carries Detours-style inline hooking code). The trampolines
live in mmap'd memory, not on the stack, so clearing the flag is safe -- verified
by loading the patched library and resolving its EIOS_* entry points.

The real fix belongs in the SRL-B/WaspLib build (link with `-z noexecstack`).
Until then, re-run this after any package update, which restores the shipped
binary.

    linux/fix-plugin-execstack.py [SIMBA_DIR]      # default: ~/Simba
"""
import pathlib, struct, subprocess, sys

PT_GNU_STACK, PF_X = 0x6474e551, 0x1


def clear_execstack(path: pathlib.Path) -> str:
    """Clear PF_X from a little-endian 64-bit ELF's PT_GNU_STACK header."""
    b = bytearray(path.read_bytes())
    if b[:4] != b'\x7fELF':
        return 'not an ELF'
    if b[4] != 2 or b[5] != 1:
        return 'not a little-endian 64-bit ELF'

    e_phoff = struct.unpack_from('<Q', b, 0x20)[0]
    e_phentsize = struct.unpack_from('<H', b, 0x36)[0]
    e_phnum = struct.unpack_from('<H', b, 0x38)[0]

    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_flags = struct.unpack_from('<II', b, off)
        if p_type != PT_GNU_STACK:
            continue
        if not p_flags & PF_X:
            return 'already non-exec'
        path.with_suffix(path.suffix + '.execstack').write_bytes(bytes(b))
        struct.pack_into('<I', b, off + 4, p_flags & ~PF_X)
        path.write_bytes(bytes(b))
        return f'cleared PF_X ({p_flags:#x} -> {p_flags & ~PF_X:#x})'
    return 'no PT_GNU_STACK header'


def loadable(path: pathlib.Path) -> str:
    """Confirm the patched library actually dlopens."""
    r = subprocess.run(
        [sys.executable, '-c',
         'import ctypes,sys; ctypes.CDLL(sys.argv[1]); print("ok")', str(path)],
        capture_output=True, text=True)
    return 'dlopen ok' if r.returncode == 0 else f'dlopen FAILED: {r.stderr.strip().splitlines()[-1]}'


def main() -> int:
    simba = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                         pathlib.Path.home() / 'Simba')
    includes = simba / 'Includes'
    if not includes.is_dir():
        print(f'no Includes directory under {simba}', file=sys.stderr)
        return 1

    found = rc = 0
    for so in sorted(includes.rglob('*.so')):
        head = so.read_bytes()[:4]
        if head != b'\x7fELF':
            continue
        result = clear_execstack(so)
        if result in ('already non-exec', 'no PT_GNU_STACK header'):
            continue
        found += 1
        rel = so.relative_to(includes)
        print(f'  {rel}\n      {result}')
        check = loadable(so)
        print(f'      {check}')
        if 'FAILED' in check:
            rc = 1

    if not found:
        print('No plugin required an executable stack. Nothing to do.')
    else:
        print(f'\nPatched {found} plugin(s). Originals kept as *.so.execstack.')
    return rc


if __name__ == '__main__':
    sys.exit(main())
