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
name (`pkill -if <name>`) instead.

## Done

| Fix | Symptom before |
|---|---|
| `CloseRuneLite()` uses `pkill -if runelite`; the `Kill()` fallback is Windows-only | whole desktop session SIGKILLed |
| RuneLite `profiles2` path uses `$HOME`, not `%userprofile%` (2 sites) | `userprofile` is empty on Linux, so paths resolved to `/.runelite/profiles2/` and the profile install failed at `ForceDirectories` |
| Generated async mover: `KillWindowByClass` / `KillSimbas` neutered on Linux | same `Kill()` landmine, reachable from a package update |
| Async downloader argument quoting | the `destination="..."` quotes exist to survive `CommandLineToArgvW`; Linux `RunScript` passes them verbatim so they land *inside* the filename, and the updater misreports the failure as a rate limit |

## Still to do

- [ ] Run the full **Install RuneLite Profile** path end to end and confirm the
      profile registers in `profiles.json`.
- [ ] Audit remaining Windows assumptions (`TProcess.SetCommandLine` callers,
      path separators, any other `GetEnvironmentVariable` Windows names).
- [ ] Decide whether `pkill -if runelite` is specific enough, or whether it should
      match the RuneLite main class instead.
- [ ] Check the SRL-B / BashLib package update path on Linux (file locking is a
      Windows concept; `IsFileLocked` always returns False here).
- [ ] Confirm nothing else in `Free Scripts/` calls `TOSWindow.Kill()`.

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
