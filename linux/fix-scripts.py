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

It also applies the per-script fixes in SCRIPT_FIXES below. Those scripts are paid and
so have no fork to hold the change -- the launcher re-downloads them and silently
reverts, which is why they are reapplied from here rather than hand-edited.
"""
import os, pathlib, subprocess, sys

GATE = '{$IFDEF WINDOWS}{$DEFINE SCRIPT_GUI}{$ENDIF}'
UNGATED = '{$DEFINE SCRIPT_GUI}   // Linux: bashgui compiles here too, and scripts use its globals unguarded'

# Eagle Eye and Mystic Might were removed from OSRS and replaced by Deadeye and Mystic
# Vigour. The matching SRL-B enum fix is in fix-includes.py; without it these names do
# not exist and nothing compiles. Applied to every script rather than named ones,
# because any of them can be re-downloaded and they all share the enum.
RENAMES = [
    ('ERSPrayer.EAGLE_EYE', 'ERSPrayer.DEADEYE'),
    ('ERSPrayer.MYSTIC_MIGHT', 'ERSPrayer.MYSTIC_VIGOUR'),
]

# (script path relative to Scripts/, old, new, label)
#
# 1. Tormented Demons, games necklace -> Tears of Guthix.
#    Upstream right-clicks the neck slot and picks 'Tears of Guthix' from the context
#    menu. With the destination menu-swapped onto a left click, a plain click is what a
#    human does, so pass an empty option. UseJewelryTeleport is the wrong helper for
#    that: its first act is an unconditional Inventory.ClickSlot(), so a left click on
#    an inventory necklace teleports immediately and the function then looks for the
#    item in Equipment, finds nothing and reports False despite having succeeded.
#    UseTeleportItem handles inventory-first properly (as TeleToFeroxEnclave does).
#    A left click also returns True the moment it clicks, so arrival is the real check.
#
# 2/3. Tormented Demons, light creature wait loop. NOT Linux-specific.
#    MoveToLightCreatureWaitSpot() is called once and its result ignored, then the
#    `while True` loop has no timeout and never re-walks. Observed 2026-09-24: WalkBlind
#    failed with 'Failed to advance path', leaving the player parked 12-14 tiles from
#    the creatures against an 8-tile threshold, spinning forever with no error. Now it
#    retries the walk every 15s and gives up after 2min so the caller can recover.
SCRIPT_FIXES = [
    (
        'bigaussie/Tormented Demons.simba',
        """  if Self.HasGamesNecklace() then
    Result := Self.UseJewelryTeleport(getChargedJewelleryNames('games necklace'),
      'Tears of Guthix', 'Necklace')
  else
  begin
    WriteLn('[NAV] No games necklace - using POH jewellery box for Tears');""",
        """  if Self.HasGamesNecklace() then
    Result := Self.GamesNecklaceToTears()
  else
  begin
    WriteLn('[NAV] No games necklace - using POH jewellery box for Tears');""",
        'TD: games necklace teleport routes through the inventory-only helper',
    ),
    (
        # The teleport is a menu-swapped LEFT CLICK on the inventory item. UseTeleportItem
        # falls back to Equipment.ClickSlot when the item is not in the inventory, and the
        # same click on the equipped necklace does something else entirely -- so the
        # fallback is removed rather than relied on. HasGamesNecklace is narrowed to the
        # inventory to match, otherwise an equipped-only necklace routes down a branch
        # that then cannot click it.
        'bigaussie/Tormented Demons.simba',
        """function TNavigation.HasGamesNecklace(): Boolean;
begin
  Result := Inventory.ContainsAny(getChargedJewelleryNames('games necklace')) or
            Equipment.ContainsAny(getChargedJewelleryNames('games necklace'));
end;""",
        """function TNavigation.HasGamesNecklace(): Boolean;
begin
  // Inventory only. The teleport is a menu-swapped left click on the inventory item;
  // the same click on the equipped necklace does something else entirely, so an
  // equipped one is not usable here and must not route us down this branch.
  Result := Inventory.ContainsAny(getChargedJewelleryNames('games necklace'));
end;

function TNavigation.GamesNecklaceToTears(): Boolean;
var
  slots: TIntegerArray;
begin
  if not Inventory.Open() then
  begin
    WriteLn('[NAV] Could not open the inventory for the games necklace');
    Exit;
  end;

  if not Inventory.FindItems(getChargedJewelleryNames('games necklace'), slots) then
  begin
    WriteLn('[NAV] No games necklace in the inventory - not falling back to the equipped one');
    Exit;
  end;

  WriteLn('[NAV] Games necklace -> Tears of Guthix (inventory left click)');
  if not Inventory.ClickSlot(slots[0], '') then
  begin
    WriteLn('[NAV] Failed to click the games necklace');
    Exit;
  end;

  Self.WaitMinimapChange();
  Result := WaitUntil(Self.IsAtTearsOfGuthix(), 200, 10000);
  if not Result then
    WriteLn('[NAV] Games necklace click did not land at Tears of Guthix');
end;""",
        'TD: inventory-only games necklace helper, no equipment fallback',
    ),
    (
        'bigaussie/Tormented Demons.simba',
        """  clickPoint: TPoint;
  hasClickPoint: Boolean;
begin
  tileDist := Self.GetNearestLightCreatureTileDist();""",
        """  clickPoint: TPoint;
  hasClickPoint: Boolean;
  waitStart, lastWalk: UInt64;
begin
  tileDist := Self.GetNearestLightCreatureTileDist();""",
        'TD: light creature wait loop gets a deadline (vars)',
    ),
    (
        'bigaussie/Tormented Demons.simba',
        """      ' tiles - skipping wait spot walk');

  while True do
  begin""",
        """      ' tiles - skipping wait spot walk');

  waitStart := GetTickCount();
  lastWalk := GetTickCount();

  while True do
  begin
    // The walk above can fail and leave us parked out of range, where no amount of
    // waiting helps. Bail out so the caller can recover instead of spinning forever.
    if GetTickCount() - waitStart > 120000 then
    begin
      WriteLn('[NAV] Gave up waiting for a light creature within ',
        LIGHT_CREATURE_MAX_TILES, ' tiles');
      Exit(False);
    end;
""",
        'TD: light creature wait loop gives up after 2min',
    ),
    (
        'bigaussie/Tormented Demons.simba',
        """      WriteLn('[NAV] Nearest light creature at ', Round(tileDist * 10) / 10,
        ' tiles, waiting for one within ', LIGHT_CREATURE_MAX_TILES, ' tiles');
      Wait(1200, 2000);
      Continue;
    end;""",
        """      WriteLn('[NAV] Nearest light creature at ', Round(tileDist * 10) / 10,
        ' tiles, waiting for one within ', LIGHT_CREATURE_MAX_TILES, ' tiles');
      if GetTickCount() - lastWalk > 15000 then
      begin
        WriteLn('[NAV] Still out of range - retrying walk to central wait spot');
        Self.MoveToLightCreatureWaitSpot();
        lastWalk := GetTickCount();
      end;
      Wait(1200, 2000);
      Continue;
    end;""",
        'TD: retry the wait-spot walk while out of range',
    ),
    (
        # Pre-existing local edit, previously unregistered and so silently reverted by
        # every script update. Upstream rubs the ring and then picks the destination out
        # of the chatbox; with the destination present directly on the ring's menu that
        # second step is skipped. Kept here so it survives, same as the rest.
        'bigaussie/Tormented Demons.simba',
        """  WriteLn('[NAV] Rubbing ring of dueling from inventory -> Ferox Enclave');
  Result := Self.UseTeleportItem(
    getChargedJewelleryNames('ring of dueling'),
    'Rub',
    'Ferox Enclave');
  if Result then
    Result := WaitUntil(Self.IsAtFerox(), 200, 10000)
  else
    WriteLn('[NAV] Failed to rub ring of dueling to Ferox Enclave');""",
        """  WriteLn('[NAV] Ring of dueling -> Ferox Enclave (menu-swapped left click)');
  Result := Self.UseTeleportItem(
    getChargedJewelleryNames('ring of dueling'),
    'Ferox Enclave',
    '');
  if Result then
    Result := WaitUntil(Self.IsAtFerox(), 200, 10000)
  else
    WriteLn('[NAV] Failed to teleport ring of dueling to Ferox Enclave');""",
        'TD: ring of dueling picks Ferox Enclave off the ring menu directly',
    ),
    (
        'bigaussie/Tormented Demons.simba',
        """  if Prayer.CanActivate(ERSPrayer.PIETY) then
    Self.BestMeleePrayer := ERSPrayer.PIETY
  else if Prayer.CanActivate(ERSPrayer.CHIVALRY) then
    Self.BestMeleePrayer := ERSPrayer.CHIVALRY
  else if Prayer.CanActivate(ERSPrayer.ULTIMATE_STRENGTH) then""",
        """  // Chivalry over Piety deliberately: it drains far less for a small stat loss, which
  // is the better trade over a long trip.
  if Prayer.CanActivate(ERSPrayer.CHIVALRY) then
    Self.BestMeleePrayer := ERSPrayer.CHIVALRY
  else if Prayer.CanActivate(ERSPrayer.PIETY) then
    Self.BestMeleePrayer := ERSPrayer.PIETY
  else if Prayer.CanActivate(ERSPrayer.ULTIMATE_STRENGTH) then""",
        'TD: prefer Chivalry over Piety (lower drain)',
    ),
    (
        # DEBUGMODE is False by default, so every [TD] line is suppressed -- including the
        # only two that say which prayer was chosen and why. Both are promoted to plain
        # WriteLn, and the switch line gains the gear style and the demon's overhead,
        # since offensive prayer follows CurrentGearStyle while protection follows the
        # demon. Without those three values a wrong prayer is indistinguishable from a
        # wrong gear-style belief.
        'bigaussie/Tormented Demons.simba',
        """  Self.DebugMsg('Offensive prayers - Melee: ' + ToStr(Self.BestMeleePrayer) +
    '  Ranged: ' + ToStr(Self.BestRangePrayer) +
    '  Magic: ' + ToStr(Self.BestMagePrayer) +
    '  (EE=' + ToStr(hasEE) + ' MM=' + ToStr(hasMM) + ').');""",
        """  // Unconditional: which prayer was picked per style is the first thing needed when a
  // prayer looks wrong, and DEBUGMODE is off by default.
  WriteLn('[TD] Offensive prayers - Melee: ' + ToStr(Self.BestMeleePrayer) +
    '  Ranged: ' + ToStr(Self.BestRangePrayer) +
    '  Magic: ' + ToStr(Self.BestMagePrayer) +
    '  (EE=' + ToStr(hasEE) + ' MM=' + ToStr(hasMM) + ').');""",
        'TD: always log the chosen offensive prayers',
    ),
    (
        'bigaussie/Tormented Demons.simba',
        """  Self.DebugMsg('Switching offensive prayer to: ' + ToStr(target) +
    ' (' + StyleToString(attackStyle) + ').');""",
        """  // Unconditional: names the prayer AND the gear style that chose it, which is what
  // separates a bad prayer mapping from a bad gear-style belief.
  WriteLn('[TD] Switching offensive prayer to: ' + ToStr(target) +
    ' (style=' + StyleToString(attackStyle) +
    ', gear=' + StyleToString(Self.CurrentGearStyle) +
    ', demon overhead=' + StyleToString(Self.Tracker.Overhead) + ').');""",
        'TD: log gear style and demon overhead on prayer switch',
    ),
    (
        # The script carries its own compensation for stock ERSPrayer being wrong on an
        # account whose scrolls upgraded Eagle Eye and Mystic Might. With ERSPrayer now
        # matching the measured book (see fix-includes.py), that remap fires a SECOND
        # time: it forces RIGOUR and AUGURY to slot 25, which is Mystic Vigour. The
        # cascades then take their first branch, because CanActivate probes slot 25 and
        # finds it lit, and pray Mystic Vigour for both the ranged and magic phases.
        # CHIVALRY has no case here, which is why melee alone looked correct.
        #
        # Note the names below are post-RENAMES (EAGLE_EYE -> DEADEYE, MYSTIC_MIGHT ->
        # MYSTIC_VIGOUR), so this entry must apply after that pass -- it does, the rename
        # loop runs first.
        'bigaussie/Tormented Demons.simba',
        """function ResolvePrayerIndex(prayer: ERSPrayer): Int32;
begin
  Result := Ord(prayer);

  if (prayer = ERSPrayer.DEADEYE) and not hasEE then
  begin
    if hasMM then Result := 25 else Result := 24;
    Exit;
  end;

  if (prayer = ERSPrayer.RIGOUR) and not hasEE then
  begin
    Result := 25;
    Exit;
  end;

  if (prayer = ERSPrayer.MYSTIC_VIGOUR) and not hasMM then
  begin
    Result := 25;
    Exit;
  end;

  if (prayer = ERSPrayer.MYSTIC_VIGOUR) and hasMM and not hasEE then
  begin
    Result := 19;
    Exit;
  end;

  if (prayer = ERSPrayer.AUGURY) and not hasMM then
  begin
    Result := 25;
    Exit;
  end;
end;""",
        """function ResolvePrayerIndex(prayer: ERSPrayer): Int32;
begin
  // Pass-through. This used to remap slots to compensate for stock ERSPrayer, which
  // still listed Eagle Eye and Mystic Might and so mis-numbered every prayer past 18 on
  // an account whose scrolls upgraded them to Deadeye and Mystic Vigour.
  //
  // ERSPrayer now matches the live book (measured by Scripts/linux-test/Prayer Book
  // Scan.simba), so the ordinal is already right and the old remap corrected a second
  // time: it forced RIGOUR and AUGURY to slot 25, which is Mystic Vigour. CanActivate
  // then saw that lit, took the first cascade branch, and prayed Mystic Vigour for both
  // the ranged and magic phases. Chivalry had no case here, which is why melee looked
  // fine while the other two did not.
  Result := Ord(prayer);
end;""",
        'TD: ResolvePrayerIndex is a pass-through (no double correction)',
    ),
    (
        # NOT Linux-specific. During the instance loading screen the minimap is black and
        # IsGameRunning() is still False, so GetState returns GAME_START and
        # HandleGameStart returned instantly on the black-minimap check. MainLoop has no
        # delay of its own, so it spun: 2026-09-28 logged "State: GAME_START" ~2,400 times
        # in 1.2 s (one loading screen). Wait for the minimap instead, bounded at 5 s.
        'waspscripts.com/cjs-tempoross-by-canadianjames.simba',
        """  if Minimap.PercentBlack() > 40 then
    Exit;

  Self.ResetGame();""",
        """  // A black minimap means a loading screen. Returning at once made MainLoop call
  // back in with no delay, re-logging "State: GAME_START" thousands of times until
  // the screen cleared. Wait it out (bounded) so each loading screen costs one pass.
  if Minimap.PercentBlack() > 40 then
  begin
    WaitUntil(Minimap.PercentBlack() <= 40, 100, 5000);
    Exit;
  end;

  Self.ResetGame();""",
        'Tempoross: wait out loading screens instead of spinning GAME_START',
    ),
    (
        # NOT Linux-specific. FishHover (the walk-click onto a fishing spot) checked the
        # uptext with a bare ConfirmUptext, whose yellow-text test is instant. Uptext lags
        # the cursor by a frame, so it read the stale "Walk here", short-circuited past
        # IsUpText's own settle wait, and all five hover attempts failed ("WalkFish
        # clicked? False"). ClickFishingSpot -- the path that does succeed -- already
        # wraps the same call in WaitUntil(..., 30, 350); do the same here.
        'waspscripts.com/cjs-tempoross-by-canadianjames.simba',
        """      Mouse.OnMovingEx := @Self._UpdateSpot;
      Mouse.Move(targetTPA.NearestPoint(Mouse.Position()));

      if Self.ConfirmUptext(Self.GetFishingUptext()) then""",
        """      Mouse.OnMovingEx := @Self._UpdateSpot;
      Mouse.Move(targetTPA.NearestPoint(Mouse.Position()));

      // Uptext lags the cursor by a frame, and ConfirmUptext's yellow-text check is
      // instant, so a bare call reads the stale "Walk here" and fails. Same wait as
      // ClickFishingSpot, which is the path that does succeed.
      if WaitUntil(Self.ConfirmUptext(Self.GetFishingUptext()), 30, 350) then""",
        'Tempoross: FishHover waits for the uptext to settle',
    ),
    (
        # targetTPA was never cleared between hover attempts, so an attempt whose search
        # found no spot re-hovered the previous attempt's (by then stale) position.
        'waspscripts.com/cjs-tempoross-by-canadianjames.simba',
        """    Writeln("Hover attempt: ", attempt);
    rects := Self.GetMSFishRects(Mainscreen.Bounds);""",
        """    Writeln("Hover attempt: ", attempt);
    targetTPA := [];
    rects := Self.GetMSFishRects(Mainscreen.Bounds);""",
        'Tempoross: FishHover resets its target each attempt',
    ),
    (
        # NOT Linux-specific. WalkBlind(..., 43) returns while the player is still ~10
        # tiles out and running. On the long first walk off the boat the camera is still
        # panning, so the spot slides out from under the cursor and all five hovers miss
        # (2026-09-28: both remaining misses in a 9-walk run were game-start walks, each
        # attempt ~0.46 s, i.e. spot found, cursor moved, 350 ms uptext wait expired).
        # On failure, wait for the player to stop and hover again. Bounded at 2.5 s plus
        # two attempts because nothing in WalkFish watches for hazards.
        'waspscripts.com/cjs-tempoross-by-canadianjames.simba',
        """  clickedFish := Self.FishHover(4);
  Self.Debugln("WalkFish clicked? " + ToStr(clickedFish), EOutputLevel.USEFUL);""",
        """  clickedFish := Self.FishHover(4);

  // WalkBlind stops waiting 43 units short, so on the long first walk off the boat the
  // player is still running and the camera still panning: the spot slides out from
  // under the cursor on every attempt. Once standing it holds still, so retry there.
  // Kept short -- nothing in here watches for hazards.
  if not clickedFish then
  begin
    Minimap.WaitPlayerMoving(500, 2500);
    Writeln("Hover retry after stopping");
    clickedFish := Self.FishHover(1);
  end;

  Self.Debugln("WalkFish clicked? " + ToStr(clickedFish), EOutputLevel.USEFUL);""",
        'Tempoross: WalkFish retries the hover once the player stops',
    ),
    (
        # Diagnostics: say WHY a hover attempt failed, so the retry above can be judged
        # from a log instead of inferred from timings.
        'waspscripts.com/cjs-tempoross-by-canadianjames.simba',
        """    if Length(rects) < 1 then
    begin
      Self.SetFishingAngle();
      continue;
    end;""",
        """    if Length(rects) < 1 then
    begin
      Writeln("  no fish rects in view");
      Self.SetFishingAngle();
      continue;
    end;""",
        'Tempoross: FishHover logs empty fish rects',
    ),
    (
        'waspscripts.com/cjs-tempoross-by-canadianjames.simba',
        """          Exit(true);
          }
      end;
    end;
  end;
end;""",
        """          Exit(true);
          }
      end;
      Writeln("  uptext was: ", Mainscreen.GetUpText());
    end
    else
      Writeln("  no spot found in rects");
  end;
end;""",
        'Tempoross: FishHover logs uptext and no-spot failures',
    ),
    (
        # HandleBanking had no give-up path: on any Withdraw failure (e.g. the bank
        # stack of a loadout item coming up short of the requested quantity -- see
        # BashLib basescript.simba's own 'bankempty' screenshot check) it just logged
        # and Exit'd, letting the state machine re-enter STATE_BANKING and retry the
        # exact same failing withdraw from scratch. Observed 2026-09-24: looped for
        # 5 straight minutes until the unrelated inactivity watchdog killed the
        # script. Now it counts consecutive failures and terminates after 5.
        'bigaussie/Tormented Demons.simba',
        '    LastSuppliesVerdict: Int32;\n    BankSupplyFailCount: Int32;\n',
        '    LastSuppliesVerdict: Int32;\n    BankSupplyFailCount: Int32;\n'
        '    BankItemsFailCount: Int32;\n',
        'TD: add BankItemsFailCount field',
    ),
    (
        'bigaussie/Tormented Demons.simba',
        """  if not Self.HandleBankItems() then
  begin
    WriteLn('[BANK] Failed to handle bank items');
    Self.BankEquippedCacheValid := False;
    Exit;
  end;

  if not Self.InCombat then
    Self.DoAntiban(True, True);
  Self.MergeTravelLoadout();""",
        """  if not Self.HandleBankItems() then
  begin
    Inc(Self.BankItemsFailCount);
    WriteLn('[BANK] Failed to handle bank items (attempt ', Self.BankItemsFailCount, '/5).');
    Self.BankEquippedCacheValid := False;

    if Self.BankItemsFailCount >= 5 then
    begin
      WriteLn('[BANK] ERROR: Could not withdraw loadout items after 5 attempts - a required item is likely missing or short in the bank.');
      if Bank.IsOpen() then
        Bank.Close();
      TerminateScript('Bank withdrawal failed 5 times in a row - check bank stock for loadout items.');
    end;
    Exit;
  end;

  Self.BankItemsFailCount := 0;

  if not Self.InCombat then
    Self.DoAntiban(True, True);
  Self.MergeTravelLoadout();""",
        'TD: give up banking after 5 straight withdraw failures instead of looping',
    ),
    (
        'bigaussie/Tormented Demons.simba',
        '  Self.LastSuppliesVerdict := -1;\n  Self.BankSupplyFailCount := 0;\n  XPBar.Read();',
        '  Self.LastSuppliesVerdict := -1;\n  Self.BankSupplyFailCount := 0;\n'
        '  Self.BankItemsFailCount := 0;\n  XPBar.Read();',
        'TD: reset BankItemsFailCount on setup',
    ),
]


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

    renamed = []
    for path in sorted(scripts.rglob('*.simba')):
        text = path.read_text(encoding='utf-8', errors='surrogateescape')
        new = text
        hits = 0
        for old, repl in RENAMES:
            hits += new.count(old)
            new = new.replace(old, repl)
        if not hits:
            continue
        backup = path.with_suffix(path.suffix + '.upstream')
        if not backup.exists():
            backup.write_text(text, encoding='utf-8', errors='surrogateescape')
        path.write_text(new, encoding='utf-8', errors='surrogateescape')
        renamed.append(path)
        print(f'  renamed  {hits} prayer refs in {path.relative_to(scripts)}')
    if renamed:
        print(f'\n{len(renamed)} script(s) had removed prayers renamed.')

    rc = 0
    fixed, present = [], 0
    for rel, old, new, label in SCRIPT_FIXES:
        path = scripts / rel
        if not path.is_file():
            print(f'  MISSING  {rel}  ({label})')
            rc = 1
            continue
        text = path.read_text(encoding='utf-8', errors='surrogateescape')
        if new in text:
            print(f'  ok       {label} (already applied)')
            present += 1
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
        fixed.append(path)

    if SCRIPT_FIXES:
        print(f'\n{len(fixed)} script fixes applied, {present} already present.')

    # Verify everything currently in the ungated state, not just this run's edits.
    targets = patched + already + [p for p in fixed + renamed if p not in patched + already]
    if verify and targets:
        print('\nCompiling (exit codes are unreliable; reading compiler output):')
        bad = 0
        for path in targets:
            ok = compiles(simba, path)
            print(f'  {"OK  " if ok else "FAIL"}  {path.relative_to(scripts)}')
            bad += 0 if ok else 1
        print(f'\n{len(targets) - bad}/{len(targets)} compile.')
        return 1 if (bad or rc) else 0
    return rc


if __name__ == '__main__':
    sys.exit(main())
