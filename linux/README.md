# Linux support

Work-in-progress branch making the B.A.S.H launcher usable on Linux. **No PR until
the Linux story is complete**; this file tracks what is done and what is left.

Every change is fenced with `{$IFDEF WINDOWS}` so the Windows build is untouched.
That is enforced, not asserted — see [Windows parity](#windows-parity) below.

## Why this branch exists

The launcher assumes Windows in a few places. Most of those just fail; one of them
destroys the user's desktop session.

### The session killer

`TWaspForm.CloseRuneLite()` shells out to `taskkill /f /im RuneLite.exe`. There is
no `taskkill` on Linux, so `TProcess.Execute` raises, and the `except` branch falls
back to walking every X window and calling `TOSWindow.Kill()` on any whose title
contains "runelite".

Simba's Linux `Kill()` resolves its target from the window's `_NET_WM_PID` property.
**Most X windows do not carry it.** `GetPID()` then returns `4294967295` (UInt32 of
-1) and `Kill()` degrades to `kill(-1, SIGKILL)` — SIGKILL to every process the user
owns, `systemd --user` included. The whole desktop session dies.

Observed on CachyOS / KDE / X11, clicking **Install RuneLite Profile**:

```
12:28:18 systemd[1]: user@1000.service: Main process exited, code=killed, status=9/KILL
12:28:18 plasmalogin[1022]: Removing display ... Greeter starting...
```

Confirmed two ways rather than inferred:

- A read-only probe over `GetWindows()` reported 76 windows, the large majority with
  `pid=4294967295`; only real toolkit top-levels resolve a true PID.
- Calling `Kill()` on one of those windows inside an isolated PID namespace
  (`unshare -Urpf --mount-proc`), with a marker process alongside, killed the marker —
  proving the broadcast — while the real session outside survived. That namespace is
  the safe way to test anything kill-adjacent here.

**Rule for this codebase: never call `TOSWindow.Kill()` on Linux.** Kill by process
name with `pkill -f`, using a pattern specific enough not to catch bystanders
(see [Verified on Linux](#verified-on-linux)).

## Done

| Fix | Symptom before |
|---|---|
| `CloseRuneLite()` uses an anchored `pkill -f` on the RuneLite main class; the `Kill()` fallback is Windows-only | whole desktop session SIGKILLed |
| RuneLite `profiles2` path uses `$HOME`, not `%userprofile%` (2 sites) | `userprofile` is empty on Linux, so paths resolved to `/.runelite/profiles2/` and the profile install failed at `ForceDirectories` |
| Generated async mover: `KillWindowByClass` / `KillSimbas` neutered on Linux | same `Kill()` landmine, reachable from a package update |
| Async downloader argument quoting | the `destination="..."` quotes exist to survive `CommandLineToArgvW`; Linux `RunScript` passes them verbatim so they land *inside* the filename, and the updater misreports the failure as a rate limit |

## Verified on Linux

- **Install RuneLite Profile, end to end.** Writes
  `<install-hex>-<id>.properties` and registers it in `profiles.json`; the desktop
  session survives; a pre-existing profile is left byte-for-byte untouched.
  Verified on CachyOS / KDE / X11, 2026-09-21.
- **`pkill` pattern specificity.** `pkill -if runelite` is far too loose — with
  RuneLite *not running* it still matched a shell whose command line merely
  contained the word. Tested against a decoy carrying the client's real 2296-char
  command line (reconstructed from `launcher.log`) plus an innocent bystander
  process mentioning the main class:

  | pattern | matches |
  |---|---|
  | `-if runelite` | decoy + bystander + unrelated shells |
  | `net\.runelite\.client\.RuneLite` | decoy + bystander |
  | `^[^[:space:]]*/java[[:space:]].*net\.runelite\.client\.RuneLite` | decoy only |

  The anchored form is what ships. It also confirms `pkill -f` reads the whole
  command line — the main class sits at offset 2268 and still matched. The pattern
  contains no spaces on purpose, since `SetCommandLine` splits on them.
  Known constraint: it assumes `argv[0]` ends in `/java`, which is how the official
  launcher spawns the client (`JvmLauncher - Running [...]` in `launcher.log`).
- **No other Windows assumptions in the repo.** `TOSWindow.Kill()` appears only at
  the fenced sites — nothing in `Free Scripts/`. `SetCommandLine` and `.exe` occur
  only in the fenced `taskkill`. `GetEnvironmentVariable` is only the four sites
  above. Every backslash use is `path.Replace('\', '/')`, i.e. normalising *to*
  forward slashes, which is already Linux-correct.

## Still to do

- [ ] **Package update path (SRL-B / BashLib) on Linux.** Analysed, not yet
      exercised. `IsFileLocked()` tests for a lock by deleting the file and
      restoring it from a `.bak`. Linux has no mandatory locking, so deleting an
      in-use `libremoteinput.so` always succeeds and the function always reports
      "unlocked" — which is arguably the right answer on Linux, since the file
      genuinely can be replaced while mapped. `FindLockedPlugins()` then returns
      empty, `UnlockPlugins()` exits early, and the kill paths are never reached.
      Worth running a real package update to confirm, and to check the
      delete/restore round-trip cannot lose a plugin if it is interrupted.

## RemoteInput plugin: executable stack

Separate from the launcher, and hit when running a script rather than installing a
profile. Simba reports:

```
Loading plugin failed. Architecture mismatch? (expected a 64 bit plugin)
  at line 1, column 11 in file ".../SRL-B/osr/remoteinput.simba"
```

Nothing is mismatched — the binary is a valid x86-64 ELF whose dependencies all
resolve. The actual loader error is:

```
dlopen: cannot enable executable stack as shared object requires
```

`libremoteinput64.so` ships with `PT_GNU_STACK` marked `RWE`; every sibling plugin
is `RW`. Since **glibc 2.41** `dlopen` refuses that request outright instead of
silently granting it, so on any current distro the plugin cannot load. The RWE
marking is the usual artefact of hand-written assembly built without a
`.note.GNU-stack` section — the plugin carries Detours-style inline hooking code,
whose trampolines live in `mmap`'d memory rather than on the stack.

```sh
linux/fix-plugin-execstack.py [SIMBA_DIR]     # default: ~/Simba
```

Scans `Includes/` for plugins requesting an executable stack, clears `PF_X` from
that one program header, keeps the original as `*.so.execstack`, and verifies each
patched library actually `dlopen`s. Verified end to end: after patching, Simba's own
`{$loadlib}` succeeds and `EIOS_*` entry points resolve.

**The real fix belongs in the SRL-B / WaspLib build** — link the plugin with
`-z noexecstack`. Until then this must be re-run after any package update, which
restores the shipped binary.

Unrelated and still open: Simba prints `Error dumping libremoteinput64.so` when
building plugin metadata. It does so for plugins that were never `RWE` (e.g.
`libslacktree64.so`) and Simba carries on regardless, so it looks cosmetic — but it
is not explained yet.

## RemoteInput pairing: the client JVM must still have java.applet

With the plugin loading (above), injection now works — `libremoteinput64.so` shows
up mapped in the client's address space. But pairing fails and takes the client
with it:

```
Cannot Initialize Maps
Terminating: [RemoteInput]:[Fatal]: Failed to pair client
```

and RuneLite dies with a JVM-level SIGSEGV whose stack has a libremoteinput frame:

```
SIGSEGV (0xb), si_addr: 0x0  (SEGV_MAPERR)
Current thread: JavaThread "Thread-10" [_thread_in_vm]
V  [libjvm.so+0x857183]
... <offset 0x71a8c> in .../libremoteinput/libremoteinput64.so
```

`libremoteinput64.so` looks up `java/applet/Applet`, among `sun/awt/SunToolkit`
and the AWT event classes. **The Applet API was removed outright in JDK 25**
(JEP 504). On Java 25+ that lookup returns null, and a null dereference inside the
VM is exactly the crash above. Confirm on any JVM with:

```sh
java --describe-module java.desktop | grep -c applet     # 0 == removed
```

So the client JVM must be **Java 24 or older** — `jre17-openjdk` matches what the
SRL/Wasp toolchain targets, `jre21-openjdk` also still has the Applet API.

The launcher spawns the client with whatever JVM it is itself running under, so
normally this means changing the system default. To test a version without touching
anything system-wide:

```sh
linux/run-client-with-java.sh                                    # audit installed JVMs
linux/run-client-with-java.sh /usr/lib/jvm/java-17-openjdk/bin/java
```

It replays the exact client command from `~/.runelite/logs/launcher.log` with the
JVM swapped, and warns if the JVM you picked also lacks `java.applet`.

Not yet confirmed end to end: no JVM older than 26 is installed on the test machine,
so "pairing succeeds on Java 17" remains a strong inference from the crash, not an
observation. `Cannot Initialize Maps` appeared alongside the pairing failure and has
not been investigated separately.

## SRL-B and BashLib need fixes too (different repos)

Found by running Settings Searcher to completion. These live in
`BigWaspBackup/SRL-B` and `BigWaspBackup/BashLib`, so they are **not** covered by
this branch — `linux/fix-includes.py` patches the installed copies, and must be
re-run after any package update.

```sh
linux/fix-includes.py [SIMBA_DIR]        # default: ~/Simba
```

**BashLib `GetProfilesPath()`** — the same `%userprofile%` Windows-ism the launcher
had, in a second copy (`BashLib/osr/handlers/settingshandler.simba`). Empty on Linux,
so the path resolved to `/.runelite/profiles2` and a correctly installed profile was
reported as missing:

```
GetProfilesPath -> Returning profiles2 path
CheckGPUPlugin -> profiles.json not found, skipping check
_CheckBashProfileRequired -> BASH RuneLite profile is not installed.
```

Fenced with `{$IFDEF WINDOWS}`. Verified after patching: the path resolves to the
real directory and `profiles.json` is found.

**SRL-B `GetCurrentClient()`** — *not* Linux-specific. It matches the root window
title exactly against `'RuneLite'`, but RuneLite appends the logged-in display name:

```
root title = "RuneLite - <name>"     →  ERSClient.UNKNOWN
[BASH] Client: UNKNOWN
[BASH] Warning: BASH scripts expect RuneLite
```

So the exact match only ever succeeds while logged out. Changed to a prefix match,
applied unconditionally — strictly more permissive, so it can only turn an UNKNOWN
into a correct answer.

## Known: `free(): invalid pointer` at Simba exit

Harmless to results, but it aborts the process and dumps core. It is **not** caused
by anything on this branch, and not by RemoteInput. Reproduces with a two-line
script:

```pascal
{$loadlib ../plugins/libtpaex/libtpaex}
begin WriteLn('done'); end.
```

Per-plugin, loading each on its own:

| plugin | exit |
|---|---|
| libtpaex, libslacktree, libsimpleocr | 134 (abort at teardown) |
| libasyncmouse, libremoteinput | 0, clean |

It fires at process exit, after the script has finished successfully, from a plugin
destructor calling back into Simba (an earlier core showed
`exit → __run_exit_handlers → libslacktree64.so → Simba`). All five plugins export
`SetPluginMemoryManager`, so the likely shape is a free through the wrong allocator
once Simba has torn its memory manager down. Fixing it means rebuilding the plugins;
out of scope here, and script results are unaffected.

## Windows parity

```sh
linux/windows-parity-check.py
```

It resolves every `{$IFDEF WINDOWS}` / `{$IFNDEF WINDOWS}` block the way a Windows
compiler would, leaves all other conditionals alone, and diffs the result against the
same resolution of `upstream/main`. Exit 0 means the Windows build sees a
byte-for-byte identical script. Run it before every push; it is the gate that lets
this branch be merged without Windows risk.

It refuses to guess: a `WINDOWS` conditional sharing a line with code aborts the run
rather than producing a misleading pass.

## Installing locally

```sh
linux/install-to-simba.sh          # or SIMBA_DIR=/path/to/Simba linux/install-to-simba.sh
```

Copies the launcher over both installed copies (`BashLauncher.simba` and
`bash-launcher.simba`), keeps one `.upstream` backup each, and compiles both.
Run `linux/fix-plugin-execstack.py` alongside it — the two cover different things
(the launcher script vs. the native plugins) and a package update reverts the latter.

**Re-run it after every launcher self-update.** `CheckBashLauncherUpdate()` pulls the
upstream launcher whenever the remote `SCRIPT_REVISION` is higher, which reverts all
of the above. Keep this branch rebased on `upstream/main` and reinstall.
