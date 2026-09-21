#!/usr/bin/env bash
#
#  Launch Simba with a light GTK2 theme, so script-GUI labels stay readable.
#  Affects this Simba process only -- the desktop theme is untouched.
#
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SIMBA_DIR="${SIMBA_DIR:-$HOME/Simba}"
exec env GTK2_RC_FILES="$HERE/gtkrc-light" "$SIMBA_DIR/Simba" "$@"
