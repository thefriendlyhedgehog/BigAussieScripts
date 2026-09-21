#!/usr/bin/env python3
"""
Patch the installed SRL-B / BashLib packages.

These live in other repos (BigWaspBackup/SRL-B, BigWaspBackup/BashLib), so they
are not covered by this branch's launcher changes. The package updater re-downloads
both, so re-run this after any package update.

    linux/fix-includes.py [SIMBA_DIR]        # default: ~/Simba

1. BashLib settingshandler GetProfilesPath()  --  Linux-only, {$IFDEF WINDOWS} fenced
   Uses %userprofile%, which is empty on Linux, so the profiles2 path resolves to
   /.runelite/profiles2. Consequences seen in a real run:
       profiles.json not found, skipping check
       BASH RuneLite profile is not installed.
   both of which are false on Linux even with the profile correctly installed.

2. BashLib TLabeledComboBox.Create()  --  Linux-only, {$IFNDEF WINDOWS} fenced
   Sizes its panel from the combo's height *before* the widget is realised. GTK2
   renders a combo taller than that, so the panel is too short and every dropdown
   in a script GUI shows its text clipped. Callers that set an explicit height
   (bashgui's AddCombo does) were fine; callers that do not (a script's own helper,
   and gearhandler's 13 equipment combos) were not.

3. SRL-B rsclient GetCurrentClient()  --  NOT Linux-specific, applied unconditionally
   Matches the root window title exactly against 'RuneLite'. RuneLite appends the
   logged-in display name ("RuneLite - someone"), so the match only ever succeeds
   while logged out, and the client is reported as UNKNOWN:
       [BASH] Client: UNKNOWN
       [BASH] Warning: BASH scripts expect RuneLite
   Changed to a prefix match, which is strictly more permissive -- it can only turn
   an UNKNOWN into a correct answer, never the reverse.
"""
import pathlib, sys

FIXES = [
    # (relative path, old, new, label)
    (
        'BashLib/osr/handlers/settingshandler.simba',
        """  Result := GetEnvironmentVariable('userprofile') +
            DirectorySeparator + '.runelite' +
            DirectorySeparator + 'profiles2';""",
        """  {$IFDEF WINDOWS}
  Result := GetEnvironmentVariable('userprofile') +
            DirectorySeparator + '.runelite' +
            DirectorySeparator + 'profiles2';
  {$ELSE}
  // 'userprofile' is a Windows environment variable and is empty on Linux.
  Result := GetEnvironmentVariable('HOME') +
            DirectorySeparator + '.runelite' +
            DirectorySeparator + 'profiles2';
  {$ENDIF}""",
        'BashLib: profiles2 path uses $HOME on Linux',
    ),
    (
        'SRL-B/osr/rsclient.simba',
        """  case win.GetRootWindow().GetTitle() of
    'Old School RuneScape': Result := ERSClient.LEGACY;
    'RuneLite': Result := ERSClient.RUNELITE;
  end;""",
        """  title := win.GetRootWindow().GetTitle();

  // RuneLite appends the logged-in display name ("RuneLite - someone"), so an
  // exact match only ever succeeds while logged out. Match on the prefix.
  if Pos('RuneLite', title) = 1 then
    Exit(ERSClient.RUNELITE);
  if Pos('Old School RuneScape', title) = 1 then
    Exit(ERSClient.LEGACY);""",
        'SRL-B: client detection matches title prefix',
    ),
    (
        'SRL-B/osr/rsclient.simba',
        """function TRSClient.GetCurrentClient(): ERSClient;
var
  win: TOSWindow;
begin""",
        """function TRSClient.GetCurrentClient(): ERSClient;
var
  win: TOSWindow;
  title: String;
begin""",
        'SRL-B: declare title local',
    ),
    (
        'BashLib/utils/forms/formutils.simba',
        """  h += TControl.AdjustToDPI(Self.Caption.getHeight());
  h += TControl.AdjustToDPI(Self.ComboBox.getHeight());

  Self.Panel.setHeight(h);
end;""",
        """  h += TControl.AdjustToDPI(Self.Caption.getHeight());
  h += TControl.AdjustToDPI(Self.ComboBox.getHeight());

  {$IFNDEF WINDOWS}
  // GTK2 renders a combo taller than the default height reported here, before the
  // widget is realised, so a panel sized from it clips the combo -- every dropdown
  // shows its text cut off. Reserve at least what bashgui's AddCombo reserves.
  // A caller's later SetHeight still overrides this, so only callers that set no
  // height at all are affected -- exactly the ones that are already broken.
  if h < TControl.AdjustToDPI(58) then
    h := TControl.AdjustToDPI(58);
  {$ENDIF}

  Self.Panel.setHeight(h);
end;""",
        'BashLib: minimum TLabeledComboBox height (GTK2 clipping)',
    ),
]


def main() -> int:
    simba = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                         pathlib.Path.home() / 'Simba')
    includes = simba / 'Includes'
    if not includes.is_dir():
        print(f'no Includes directory under {simba}', file=sys.stderr)
        return 1

    rc = applied = skipped = 0
    for rel, old, new, label in FIXES:
        path = includes / rel
        if not path.is_file():
            print(f'  MISSING  {rel}  ({label})')
            rc = 1
            continue
        text = path.read_text(encoding='utf-8', errors='surrogateescape')
        if new in text:
            print(f'  ok       {label} (already applied)')
            skipped += 1
            continue
        n = text.count(old)
        if n != 1:
            print(f'  FAIL     {label}: expected 1 site in {rel}, found {n}')
            rc = 1
            continue
        backup = path.with_suffix(path.suffix + '.upstream')
        if not backup.exists():
            backup.write_text(text, encoding='utf-8', errors='surrogateescape')
        path.write_text(text.replace(old, new), encoding='utf-8',
                        errors='surrogateescape')
        print(f'  PATCH    {label}')
        applied += 1

    print(f'\n{applied} applied, {skipped} already present.'
          f'{"  Originals kept as *.upstream." if applied else ""}')
    return rc


if __name__ == '__main__':
    sys.exit(main())
