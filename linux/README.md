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

- [ ] **Broader script-GUI polish on Linux.** The dropdown fixes (height, and
      leaving the font to the theme) sorted the worst of it, but other controls
      still assume Windows' light system colours in places. Same shape of problem
      each time: a control that sets one half of a colour pair and inherits the
      other from GTK. Deferred until the scripts are actually running.
- [ ] **Script GUI repaints badly on resize.** Dragging a window corner leaves black
      rectangles and the gear image panel does not move with the layout. Cosmetic,
      and only while resizing. Not investigated. Likely child controls lacking
      anchors plus no repaint of the exposed region; the cheap workaround, if it is
      not worth fixing properly, is to make the form non-resizable.
- [ ] **Sidebar title is clipped** ("Tormented Demon" for "Tormented Demons") — a
      label width vs. nav-panel width issue, unrelated to the combo height fix.
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

## RemoteInput requires a client JVM that still has java.applet

**The client JVM must be Java 24 or older.** `jre17-openjdk` is confirmed working.

`libremoteinput64.so` looks up `java/applet/Applet`. The Applet API was removed
outright in JDK 25 (JEP 504), so on Java 25+ the lookup yields null and the
unchecked dereference kills the client:

```
Terminating: [RemoteInput]:[Fatal]: Failed to pair client
SIGSEGV si_addr: 0x0 (SEGV_MAPERR)
Current thread: JavaThread "Thread-10" [_thread_in_vm]
V  [libjvm.so+0x857183]   ... <offset 0x71a8c> in libremoteinput64.so
```

Check any JVM with:

```sh
java --describe-module java.desktop | grep -c applet     # 0 == removed
```

Observed: on Java 26 the client hard-crashed twice with the above. On Java 17 it
pairs — `EIOS_GetClients()` reports an injected client, and Settings Searcher ran to
completion.

### Launching the client on Java 17

Arch's `runelite` package ships `/usr/bin/runelite` as a shell script honouring
`RUNELITE_JAVA`, and the RuneLite launcher spawns the client with the JVM it is
itself running under. So one environment variable pins the whole chain:

```sh
RUNELITE_JAVA=/usr/lib/jvm/java-17-openjdk/bin/java runelite
```

Verified end to end: `launcher.log` then records
`JvmLauncher - Running [/usr/lib/jvm/java-17-openjdk/bin/java, ...]`, and the client
process runs on that JVM.

For the dock / apps menu, put the same env in the desktop entries. A user-level
`~/.local/share/applications/runelite.desktop` shadows the packaged one and survives
package updates:

```
Exec=env RUNELITE_JAVA=/usr/lib/jvm/java-17-openjdk/bin/java runelite
```

The Jagex launcher invokes `runelite` from PATH, so the same env on its entry is
inherited by the client it starts:

```
Exec=env RUNELITE_JAVA=/usr/lib/jvm/java-17-openjdk/bin/java "/opt/jagex-launcher/jagex-launcher.AppImage" %U
```

`linux/run-client-with-java.sh` predates this and is now only a fallback, for a
client already started some other way -- it replays the last command from
`launcher.log` with the JVM swapped. Prefer `RUNELITE_JAVA`.

Still unexplained: `Cannot Initialize Maps`, printed just before one pairing failure.

## Script GUI is gated to Windows, and that breaks the build

Every BigAussie script opens with:

```pascal
{$IFDEF WINDOWS}{$DEFINE SCRIPT_GUI}{$ENDIF}
```

so `BashLib/optional/handlers/bashgui.simba` is only included on Windows. The scripts
then reference symbols it declares — `ENABLEWEBHOOKS`, `WEBHOOKURL` — **outside** any
`{$IFDEF SCRIPT_GUI}` guard, so on Linux they do not compile at all:

```
Unknown declaration "ENABLEWEBHOOKS" at line 3616 in ".../Tormented Demons.simba"
```

`bashgui.simba` compiles fine on Linux, so the gate is an unnecessary restriction
rather than a workaround. Removing it fixes the build *and* gives Linux users the
script GUI they would otherwise lose entirely.

```sh
linux/fix-scripts.py [SIMBA_DIR] [--verify]
```

25 of 28 installed scripts carried the gate. With it removed, **25/25 compile**
(`--verify`). Scripts are re-downloaded by the launcher, so re-run after updates.

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

## Clipped combo boxes in script GUIs

Every dropdown in a script GUI renders with its text cut off at the bottom, while
edits, labels, buttons and checkboxes are fine.

`TLabeledComboBox.Create` sizes its panel as
`Caption.getHeight() + ComboBox.getHeight()` *at creation time*, then
`ComboBox.setAlign(alClient)` makes the combo fill what is left. GTK2 renders a combo
taller than the default height reported before the widget is realised, so the panel
is too short and the combo is clipped. On Windows that default is big enough, which
is why this is Linux-only.

It only affects callers that never set an explicit height:

| caller | sets height? | result |
|---|---|---|
| bashgui `AddCombo` | yes, `AdjustToDPI(58)` | fine |
| a script's own helper (e.g. `AddComboByText`) | no | clipped |
| `gearhandler` equipment combos (13 of them) | no | clipped |

Fixed in `linux/fix-includes.py` with a minimum height inside `Create`, fenced
`{$IFNDEF WINDOWS}`. A caller's later `SetHeight` still wins, so the only behaviour
that changes is for callers that are already broken.

Proved with a two-combo test form — one built with `SetHeight(58)`, one without,
identical otherwise. Before the fix the second reproduced the clipping exactly; after
it, both render identically.

**Not the GTK font.** `gtk-font-name` is `Noto Sans 10`, which looks like the obvious
cause, but rendering at 8 vs 10 is pixel-identical because the code sets the combo
font explicitly. Do not change `~/.gtkrc-2.0` for this.

## Unreadable labels under a dark GTK theme

On the Accounts and Equipment pages the field captions are invisible -- blank space
where "Account", "Password", "World" and the gear slot names should be -- while the
Action page reads fine.

Script GUIs paint their own panels white (`am.SetColor(BASH_GUI_BG)`), but many
labels never set a font colour and so inherit the GTK theme default. Under a dark
theme that default is *light*, which disappears on those white panels. The labels
that do render are the ones bashgui creates itself -- `MakeLabel`, `AddEdit` and
`AddCheck` all call `SetFontColor`; `AddLabel` and the shared lib builders
(`CreateAccountManager`, gearhandler's `_SetupGearPanel`) do not.

So it is an environment mismatch, not a layout bug: these GUIs assume the light
system theme Windows gives them.

```sh
linux/run-simba.sh          # Simba with a light GTK2 theme, this process only
```

`linux/gtkrc-light` includes the user's real GTK2 settings and overrides only
`gtk-theme-name`. Verified that `GTK2_RC_FILES` reaches Simba: its menus, file tree
and search box render light. The desktop theme is not touched.

The alternative -- patching every lib builder to set an explicit font colour -- is
far more invasive and would have to be re-applied after every package update.

## Auditing which scripts build

```sh
linux/verify-scripts.py [SIMBA_DIR] [--jobs N] [--only SUBSTR]
```

Compiles every installed script and groups failures **by error message**, because
that is where the signal is: one error across thirty scripts is a single Linux fix,
thirty distinct errors are thirty rotted scripts.

Baseline after de-duplication: **164 of 169 compile** (26 BASH + 142 third-party +
the local Tormented Demons test copy). The 5 remaining failures are all individual
drift against older WaspLib versions, not Linux problems:

| error | scripts |
|---|---|
| `Unknown declaration "MAP_PATH"` | herbiboar-hunter, thief-aio-portroberts |
| `Unknown declaration "TRSBankWithdrawItem"` | agility_arena_at_brimhaven |
| `Unknown declaration "FireConfig"` | skunk-and-bootje-log-burner |
| `Invalid cast` (line 6168) | garretts-flipper |

The earlier sweep counted 177 because BigAussie's own scripts were duplicated into the
third-party set at older revisions (e.g. Gemstone Crab at rev 75 and a `9 BETA 6`
against rev 94 in the BASH set). Those 8 were removed.

### Case-sensitive include paths

Six scripts failed only because they include
`BashLib/optional/handlers/House/house.simba` with a capital H, while the directory
is lowercase. Windows filesystems are case-insensitive so this works there; Linux is
not. Rather than edit six scripts, `fix-includes.py` maintains a `House -> house`
symlink, which fixes every such script at once including ones not installed yet.

Exit codes are unreliable here (Simba aborts at teardown regardless), so success is
read from the compiler's output, and the environment must be inherited -- a stripped
env makes every script report a false failure.

## Check everything at once

```sh
linux/status.sh
```

Verifies all five: both launcher copies, the plugin's executable stack, the two
includes patches, that no script still gates its GUI to Windows, and that a JVM with
`java.applet` is installed. Prints the exact command to fix anything that is off, and
reports which JVM a running client is on.

**Worth running before every session.** The launcher re-downloads itself, its
packages and its scripts whenever a remote revision is newer, silently reverting
everything here. That was observed mid-session: `bash-launcher.simba` reverted to an
older patch and `Tormented Demons.simba` returned to its gated form, both without any
visible message.

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
