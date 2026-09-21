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

**Re-run it after every launcher self-update.** `CheckBashLauncherUpdate()` pulls the
upstream launcher whenever the remote `SCRIPT_REVISION` is higher, which reverts all
of the above. Keep this branch rebased on `upstream/main` and reinstall.
