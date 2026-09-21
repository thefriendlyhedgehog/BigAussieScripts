#!/usr/bin/env bash
#
#  Launch Simba with a light GTK2 theme, so script-GUI labels stay readable.
#  Affects this Simba process only -- the desktop theme is untouched.
#
#  Script GUIs paint their panels white but many labels never set a font colour,
#  so under a dark theme they inherit light text and vanish. Some controls also
#  take their background straight from the theme (bashgui's AddEdit sets a font
#  colour but no background), so which light theme you pick changes how edit
#  boxes look -- Breeze renders them button-face grey rather than white.
#
#  Try another with:  SIMBA_GTK_THEME=Raleigh linux/run-simba.sh
#  Available themes:  ls -d /usr/share/themes/*/gtk-2.0 | xargs -n1 dirname | xargs -n1 basename
#
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SIMBA_DIR="${SIMBA_DIR:-$HOME/Simba}"
THEME="${SIMBA_GTK_THEME:-Breeze}"

if [ ! -d "/usr/share/themes/$THEME/gtk-2.0" ]; then
    echo "no GTK2 data for theme '$THEME' in /usr/share/themes" >&2
    echo "available:" >&2
    for d in /usr/share/themes/*/gtk-2.0; do [ -d "$d" ] && echo "  $(basename "$(dirname "$d")")" >&2; done
    exit 1
fi

RC="$(mktemp -t simba-gtkrc.XXXXXX)"
trap 'rm -f "$RC"' EXIT
{
    [ -f "$HOME/.gtkrc-2.0" ] && echo "include \"$HOME/.gtkrc-2.0\""
    echo "gtk-theme-name=\"$THEME\""
} > "$RC"

echo "Simba with GTK2 theme: $THEME"
GTK2_RC_FILES="$RC" "$SIMBA_DIR/Simba" "$@"
