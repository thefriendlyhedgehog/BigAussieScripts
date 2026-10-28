**BashLib gearhandler: saving or removing a loadout can delete a *different* loadout (all platforms)**

`TRSGearHandler.Edit()` removes the JSON key by position (`keys.GetStrings(idx)`) and then re-adds the loadout with `Config.Put`, which puts it at the **end** of `gearhandler.json`, while `Sets[idx]` stays where it was. Once you've edited any loadout but the last one, the file order and `Sets[]` order no longer match, so the next Edit or Remove drops the wrong key. `Remove()` has the same positional lookup.

Repro (3 loadouts A, B, C):
- edit A → file order is now `B C A`, Sets is still `A B C`
- edit B → removes key[1] = **C** → file is `B A` (C is gone)
- Remove A (idx 0) → removes key[0] = **B**

Knock-on effect: scripts that store a loadout by index (Tormented Demons' `Loadout1Index`/`Loadout2Index`) point at the wrong set or none after a restart, and TD stops with "Invalid gear loadout configuration". That's how I found it: I lost a ranged loadout this way.

Fix: a `_WriteConfig()` that rewrites the file from `Sets[]`, so the order always matches. Edit and Remove call it instead of the positional remove/put.

**Smaller Linux one, same file:** on GTK2 the 13 equipment slot dropdowns (`csDropDownList`) open as a single screen-tall menu of every item in the game, with only scroll arrows to move through it. The patch makes them `csDropDown` + `AutoComplete` (fenced `{$IFNDEF WINDOWS}`, though it would probably be nice on Windows too). Typing "ar" selects Arclight. Two guards go with it: the slot image ignores half-typed text (`GetItemIDs(text)[0]` would hit an empty array), and on save, text that matches no item is stored as `None`.

Patch against current BashLib attached (`bashlib-gearhandler.patch`, applies cleanly). Tested on Linux with a stubbed-config test of Edit/Remove (old code reproduces the loss, new code keeps file order = Sets order) and an xdotool-driven test of the dropdown. Tormented Demons rev 24 compiles with it. Leftover nit: Edit() now has unused `keys`/`obj`/`slot` vars.

---

**BashLib bashgui: the Discord webhook is forgotten on every run when you have 2+ saved accounts (all platforms)**

The Accounts panel reads the saved webhook (`<user> Webhook Settings` in `Configs/BASettings.ini`) for whichever account is current while the GUI is being built, which is the *first* saved account. Then the account manager switches to the last-used account. `OnAccountSelected()` reloads that account's antiban profile but not its webhook, so the box keeps the first account's URL, which is usually empty. On Start, `StartScript` writes that box to the selected account's section, so the URL you entered last time is erased.

Repro: save accounts `A` and `B`, select `B`, enter a webhook, Start. Stop, run the script again: the box is empty, and `[B Webhook Settings]` now has `WebhookURL=` and `EnableWebhooks=false`.

Fix: `OnAccountSelected()` also reloads the webhook URL and checkbox for the new account (`bashlib-webhook-account.patch`, 7 lines, applies cleanly to current BashLib). Tormented Demons rev 24 compiles with it.
