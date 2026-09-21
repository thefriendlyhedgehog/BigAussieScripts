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
    (
        'BashLib/utils/forms/formutils.simba',
        """procedure TLabeledControl.Create(owner: TControl);
begin
  Self.Panel.Create(owner);
  Self.Panel.setBevelWidth(0);

  Self.Caption.Create(Self.Panel);
  Self.Caption.setAlign(alTop);
end;""",
        """procedure TLabeledControl.Create(owner: TControl);
begin
  Self.Panel.Create(owner);
  Self.Panel.setBevelWidth(0);

  Self.Caption.Create(Self.Panel);
  Self.Caption.setAlign(alTop);
  {$IFNDEF WINDOWS}
  // Script GUIs are designed against Windows' light system colours. On Linux the
  // GTK theme decides, so under a dark theme captions come out light on the white
  // panels these GUIs paint, and are invisible. Pin both ends explicitly so the
  // result no longer depends on the desktop theme.
  //
  // Deliberately NOT done for the inner TComboBox: GTK2 ignores setColor there (the
  // box renders dark whatever we ask, and identically under a light theme) but DOES
  // honour the font colour -- so pinning a dark font gives dark text on a dark box.
  Self.Panel.setColor($FFFFFF);
  Self.Caption.getFont().setColor($1C1C1E);
  {$ENDIF}
end;""",
        'BashLib: pin TLabeledControl colours',
    ),
    (
        'BashLib/utils/forms/formutils.simba',
        """procedure TLabeledPanel.Create(owner: TControl); override;
begin
  Self.Panel.Create(owner);

  Self.Caption.Create(Self.Panel);
  Self.Caption.setAlign(alTop);
end;""",
        """procedure TLabeledPanel.Create(owner: TControl); override;
begin
  Self.Panel.Create(owner);

  Self.Caption.Create(Self.Panel);
  Self.Caption.setAlign(alTop);
  {$IFNDEF WINDOWS}
  // Script GUIs are designed against Windows' light system colours. On Linux the
  // GTK theme decides, so under a dark theme captions come out light on the white
  // panels these GUIs paint, and are invisible. Pin both ends explicitly so the
  // result no longer depends on the desktop theme.
  //
  // Deliberately NOT done for the inner TComboBox: GTK2 ignores setColor there (the
  // box renders dark whatever we ask, and identically under a light theme) but DOES
  // honour the font colour -- so pinning a dark font gives dark text on a dark box.
  Self.Panel.setColor($FFFFFF);
  Self.Caption.getFont().setColor($1C1C1E);
  {$ENDIF}
end;""",
        'BashLib: pin TLabeledPanel colours',
    ),
    (
        'BashLib/utils/forms/formutils.simba',
        """  Self.Edit.Create(Self.Panel);
  Self.Edit.setAlign(alClient);
""",
        """  Self.Edit.Create(Self.Panel);
  Self.Edit.setAlign(alClient);

  {$IFNDEF WINDOWS}
  Self.Edit.setColor($FFFFFF);
  Self.Edit.getFont().setColor($1C1C1E);
  {$ENDIF}
""",
        'BashLib: pin TLabeledEdit colours',
    ),
    (
        'BashLib/optional/handlers/bashgui.simba',
        """  box.SetFontSize(BASH_GUI_COMBO_FONT);
  box.ComboBox.SetFontColor(BASH_GUI_TEXT);
  box.ComboBox.GetFont().SetSize(BASH_GUI_COMBO_FONT);""",
        """  box.SetFontSize(BASH_GUI_COMBO_FONT);
  {$IFDEF WINDOWS}
  box.ComboBox.SetFontColor(BASH_GUI_TEXT);
  {$ELSE}
  // BASH_GUI_TEXT is near-black, which is correct on Windows where a combo's box
  // is white. GTK2 renders the box dark and ignores setColor on it, so forcing a
  // dark font here makes the selection unreadable. Leave the font to the theme,
  // which pairs it with its own background.
  {$ENDIF}
  box.ComboBox.GetFont().SetSize(BASH_GUI_COMBO_FONT);""",
        'BashLib: leave combo font to the theme (readable selection)',
    ),
]


# Case-only aliases. Windows filesystems are case-insensitive, so a script that
# writes "House/house.simba" works there and fails here. A symlink fixes every such
# script at once, including ones not installed yet, without editing any of them.
LINKS = [
    ('BashLib/optional/handlers/House', 'house'),
]


def ensure_links(includes: pathlib.Path) -> int:
    made = 0
    for rel, target in LINKS:
        link = includes / rel
        if link.is_symlink() or link.exists():
            print(f'  ok       case alias {rel} -> {target} (present)')
            continue
        if not (link.parent / target).is_dir():
            print(f'  MISSING  {rel}: target "{target}" does not exist')
            continue
        link.symlink_to(target)
        print(f'  LINK     case alias {rel} -> {target}')
        made += 1
    return made


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

    ensure_links(includes)

    print(f'\n{applied} applied, {skipped} already present.'
          f'{"  Originals kept as *.upstream." if applied else ""}')
    return rc


if __name__ == '__main__':
    sys.exit(main())
