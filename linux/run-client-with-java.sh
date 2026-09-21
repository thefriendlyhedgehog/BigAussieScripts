#!/usr/bin/env bash
#
#  Relaunch the RuneLite client under a chosen JVM, bypassing the launcher.
#
#  Why: RemoteInput injects into the client JVM and looks up java/applet/Applet.
#  The Applet API was REMOVED in JDK 25 (JEP 504), so on Java 25+ that lookup
#  yields null and the injected code dereferences it -- the client dies with
#  SIGSEGV inside libjvm while RemoteInput reports "Failed to pair client".
#  Confirmed: crashes on Java 26, pairs on Java 17.
#  Check with:  java --describe-module java.desktop | grep -c applet
#
#  The launcher spawns the client with whatever JVM it is itself running under,
#  so pointing it at an older Java normally means changing the system default.
#  This replays the exact command the launcher last used, with the JVM swapped,
#  so you can test a Java version without touching anything system-wide.
#
#  Usage:
#    linux/run-client-with-java.sh                      # show what it would run
#    linux/run-client-with-java.sh /usr/lib/jvm/java-17-openjdk/bin/java
#
set -euo pipefail

LOG="${RUNELITE_LOG:-$HOME/.runelite/logs/launcher.log}"
JAVA="${1:-}"

[ -f "$LOG" ] || { echo "no launcher log at $LOG -- start RuneLite once first" >&2; exit 1; }

# The launcher logs the client command as: JvmLauncher - Running [a, b, c]
line="$(grep -F 'JvmLauncher - Running [' "$LOG" | tail -1)"
[ -n "$line" ] || { echo "no 'JvmLauncher - Running [...]' entry in $LOG" >&2; exit 1; }

mapfile -t ARGV < <(
  printf '%s' "$line" | sed 's/.*JvmLauncher - Running \[//; s/\]$//' | sed 's/, /\n/g'
)
[ "${#ARGV[@]}" -gt 1 ] || { echo "could not parse the client command" >&2; exit 1; }

ORIG_JAVA="${ARGV[0]}"

if [ -z "$JAVA" ]; then
    echo "Launcher last used: $ORIG_JAVA"
    "$ORIG_JAVA" --describe-module java.desktop 2>/dev/null \
      | grep -q applet && applet=present || applet=REMOVED
    echo "  java.applet:      $applet"
    echo "  main class:       ${ARGV[${#ARGV[@]}-1]}"
    echo
    echo "Installed JVMs:"
    for j in /usr/lib/jvm/*/bin/java; do
        [ -x "$j" ] || continue
        v="$("$j" -version 2>&1 | head -1)"
        "$j" --describe-module java.desktop 2>/dev/null | grep -q applet \
            && a='applet present' || a='applet REMOVED'
        echo "  $j  --  $v  [$a]"
    done
    echo
    echo "Re-run with one of those paths to launch the client under it."
    exit 0
fi

[ -x "$JAVA" ] || { echo "not executable: $JAVA" >&2; exit 1; }
if ! "$JAVA" --describe-module java.desktop 2>/dev/null | grep -q applet; then
    echo "WARNING: $JAVA has no java.applet -- RemoteInput will very likely still" >&2
    echo "         fail to pair and may crash the client." >&2
fi

ARGV[0]="$JAVA"
echo "Launching client under $JAVA ..."
exec "${ARGV[@]}"
