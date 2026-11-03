#!/usr/bin/env bash
#
#  Re-apply the Linux fixes after a B.A.S.H update.
#
#  The launcher re-downloads SRL-B and BashLib from upstream, which restores the
#  executable-stack RemoteInput plugin, the Windows %userprofile% path and the
#  Windows-only script GUI gate; scripts can be re-fetched as well. Run this after
#  any update -- double-click the desktop shortcut on Cachy.
#
#    linux/apply-linux-fixes.sh            show the result in dialogs
#    linux/apply-linux-fixes.sh --no-ui    headless, prints to stdout
#
set -uo pipefail

REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
SIMBA_DIR="${SIMBA_DIR:-$HOME/Simba}"
LOG_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/bash-linux-fixes"
LOG="$LOG_DIR/last.log"
UI=1
[ "${1:-}" = "--no-ui" ] && UI=0

mkdir -p "$LOG_DIR"
if [ "$UI" = 1 ]; then
    exec > >(tee "$LOG") 2>&1
else
    exec > >(tee "$LOG") 2>&1
fi

echo "B.A.S.H Linux fixes - $(date '+%Y-%m-%d %H:%M')"
echo "Repo: $REPO"
echo

cd "$REPO" || { echo "Missing repo: $REPO"; exit 1; }

failed=0
run() {
    echo "== $*"
    "$@" || failed=1
    echo
}

run python3 linux/fix-plugin-execstack.py
run python3 linux/fix-includes.py
run python3 linux/fix-scripts.py

echo "== linux/status.sh"
bash linux/status.sh
status_rc=$?

if [ "$UI" = 0 ]; then
    exit "$status_rc"
fi

if [ "$failed" -eq 0 ] && [ "$status_rc" -eq 0 ]; then
    title="B.A.S.H Linux fixes - OK"
else
    title="B.A.S.H Linux fixes - PROBLEMS"
fi

kdialog --title "$title" --textbox "$LOG" 780 620 >/dev/null 2>&1

if pgrep -x Simba >/dev/null 2>&1; then
    if kdialog --title "B.A.S.H Linux fixes" --yesno \
        "Simba is still running with the old plugin loaded.\n\nRestart Simba now? Stop any running script first." \
        >/dev/null 2>&1; then
        echo "Restarting Simba..."
        pkill -TERM -x Simba 2>/dev/null
        for _ in $(seq 1 10); do
            pgrep -x Simba >/dev/null 2>&1 || break
            sleep 1
        done
        if pgrep -x Simba >/dev/null 2>&1; then
            kdialog --title "B.A.S.H Linux fixes" --error \
                "Simba did not close. Close it from the desktop and reopen it." >/dev/null 2>&1
        else
            ( cd "$SIMBA_DIR" && setsid env GTK2_RC_FILES="$SIMBA_DIR/gtkrc-light" \
                ./Simba >/dev/null 2>&1 < /dev/null & )
        fi
    fi
fi

exit "$status_rc"
