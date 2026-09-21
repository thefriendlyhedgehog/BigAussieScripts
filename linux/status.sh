#!/usr/bin/env bash
#
#  Are all the Linux fixes actually in place right now?
#
#  Worth running before every session. The launcher re-downloads itself, its
#  packages and its scripts whenever a remote revision is newer, silently
#  reverting everything here -- this has been observed happening mid-session.
#
set -uo pipefail
SIMBA_DIR="${SIMBA_DIR:-$HOME/Simba}"
HERE="$(cd "$(dirname "$0")" && pwd)"
INC="$SIMBA_DIR/Includes"
SCR="$SIMBA_DIR/Scripts"
bad=0

ok()   { printf '  \033[32mOK\033[0m    %s\n' "$*"; }
fail() { printf '  \033[31mFIX\033[0m   %s\n     -> %s\n' "$1" "$2"; bad=1; }

echo "Simba: $SIMBA_DIR"
echo

# 1. launcher, both copies
for f in BashLauncher.simba bash-launcher.simba; do
    if grep -qF 'net\.runelite\.client\.RuneLite' "$SCR/$f" 2>/dev/null; then
        ok "launcher $f"
    else
        fail "launcher $f is stale or unpatched" "linux/install-to-simba.sh"
    fi
done

# 2. RemoteInput executable stack
so="$INC/SRL-B/plugins/libremoteinput/libremoteinput64.so"
flags="$(readelf -lW "$so" 2>/dev/null | awk '/GNU_STACK/{print $(NF-1)}')"
case "$flags" in
    RW)  ok "libremoteinput stack non-exec" ;;
    RWE) fail "libremoteinput requests an executable stack" "linux/fix-plugin-execstack.py" ;;
    *)   fail "libremoteinput missing or unreadable" "reinstall SRL-B, then linux/fix-plugin-execstack.py" ;;
esac

# 3. includes
grep -q "GetEnvironmentVariable('HOME')" \
    "$INC/BashLib/osr/handlers/settingshandler.simba" 2>/dev/null \
    && ok "BashLib profiles2 path" \
    || fail "BashLib still uses %userprofile%" "linux/fix-includes.py"

grep -q "Pos('RuneLite', title) = 1" "$INC/SRL-B/osr/rsclient.simba" 2>/dev/null \
    && ok "SRL-B client detection" \
    || fail "SRL-B still matches the client title exactly" "linux/fix-includes.py"

# 4. scripts (ignore .upstream backups)
gated=$(find "$SCR" -name '*.simba' -exec grep -l '{$IFDEF WINDOWS}{$DEFINE SCRIPT_GUI}{$ENDIF}' {} + 2>/dev/null | wc -l)
[ "$gated" -eq 0 ] \
    && ok "script GUI un-gated (0 scripts still gated)" \
    || fail "$gated script(s) still gate the GUI to Windows" "linux/fix-scripts.py"

# 5. a client JVM that still has java.applet
found=''
for j in /usr/lib/jvm/*/bin/java; do
    [ -x "$j" ] || continue
    "$j" --describe-module java.desktop 2>/dev/null | grep -q applet && found="$j" && break
done
[ -n "$found" ] \
    && ok "JVM with java.applet available: $found" \
    || fail "no installed JVM still has java.applet (RemoteInput cannot pair)" \
            "sudo pacman -S --needed jre17-openjdk"

echo
if [ "$bad" -eq 0 ]; then
    echo "  All Linux fixes in place."
    if pgrep -f 'net\.runelite\.client\.RuneLite' >/dev/null 2>&1; then
        for p in $(pgrep -f 'net\.runelite\.client\.RuneLite'); do
            jvm="$(tr '\0' '\n' < "/proc/$p/cmdline" 2>/dev/null | head -1)"
            printf '  Client running: pid %s on %s\n' "$p" "$jvm"
            case "$jvm" in
                *java-17*|*java-21*) ;;
                *) printf '    \033[33m!\033[0m that JVM may lack java.applet - RemoteInput will crash it\n' ;;
            esac
        done
    else
        echo "  No client running. Start one with:"
        echo "    $HERE/run-client-with-java.sh /usr/lib/jvm/java-17-openjdk/bin/java"
    fi
else
    echo "  Run the commands above from the repo root, then re-check."
fi
exit "$bad"
