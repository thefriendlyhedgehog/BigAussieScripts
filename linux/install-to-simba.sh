#!/usr/bin/env bash
#
#  Install this branch's launcher over a local Simba install.
#
#  The launcher self-updates: CheckBashLauncherUpdate() re-downloads the upstream
#  (Windows-only) launcher from GitHub whenever the remote SCRIPT_REVISION is
#  higher than the installed one. That silently reverts every Linux fix, so re-run
#  this after any launcher update -- a reverted install is a live session-kill risk
#  (see linux/README.md).
#
#  Both copies matter:
#    BashLauncher.simba   what Data/default.simba runs via SimbaRunInTab
#    bash-launcher.simba  BASH_LAUNCHER_FILE, what actually runs after migration
#
set -euo pipefail

SIMBA_DIR="${SIMBA_DIR:-$HOME/Simba}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/B.A.S.H Launcher.simba"
SCRIPTS="$SIMBA_DIR/Scripts"

[ -f "$SRC" ]      || { echo "missing: $SRC" >&2; exit 1; }
[ -d "$SCRIPTS" ]  || { echo "no Simba Scripts dir: $SCRIPTS" >&2; exit 1; }

for name in BashLauncher.simba bash-launcher.simba; do
    dest="$SCRIPTS/$name"
    if [ -f "$dest" ] && [ ! -f "$dest.upstream" ]; then
        cp "$dest" "$dest.upstream"
        echo "  backed up $name -> $name.upstream"
    fi
    cp "$SRC" "$dest"
    echo "  installed $name"
done

if [ -x "$SIMBA_DIR/Simba" ]; then
    echo "  verifying..."
    for name in BashLauncher.simba bash-launcher.simba; do
        if "$SIMBA_DIR/Simba" --compile "$SCRIPTS/$name" 2>&1 \
             | grep -qi 'compiled'; then
            echo "    $name compiles"
        else
            echo "    $name FAILED TO COMPILE" >&2; exit 1
        fi
    done
fi

echo "Done. Launch Simba and press play."
