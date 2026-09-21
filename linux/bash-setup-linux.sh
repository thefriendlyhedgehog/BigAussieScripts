#!/usr/bin/env bash
#
#  B.A.S.H - BigAussie Script House : Linux setup
#  ==============================================
#  Linux equivalent of bash-setup.exe (BigWaspBackup/bash-setup/windows/bash-setup.cmd).
#
#  Mirrors the Windows installer, plus the Linux-only steps it has no reason to do:
#  native package deps, cap_sys_ptrace for RemoteInput, a .desktop entry, and an X11 check.
#
#  IMPORTANT, and the reason a naive port fails:
#  Simba comes from Torwent/Simba, NOT Villavu/Simba. Torwent's fork adds three IDE script
#  methods that stock Simba 1400 does not have -- SimbaOpenInTab, SimbaRunInTab and
#  SimbaCloseTab. The BASH launcher calls SimbaOpenInTab, so on a stock build it dies at
#  compile time with: Unknown declaration "SimbaOpenInTab".
#  Torwent's own wasp-setup/linux/simba-setup.sh points at Villavu's release and is stale.
#
#  Usage:
#    ./bash-setup-linux.sh [--dir DIR] [--fresh] [--no-deps] [--no-setcap] [--silent]
#
#    --dir DIR     install location            (default: ~/Simba)
#    --fresh       delete DIR first            (default: install over the top)
#    --no-deps     skip native package install (use if you manage deps yourself)
#    --no-setcap   skip the sudo setcap step   (RemoteInput will not work without it)
#    --no-fixes    skip the Linux source fixes  (nothing will work properly)
#    --no-java     skip installing a JVM <= 24  (RemoteInput will not pair)
#    --silent      no prompts, no pauses
#
set -uo pipefail

SIMBA_DIR="$HOME/Simba"
FRESH=0; NO_DEPS=0; NO_SETCAP=0; SILENT=0; NO_FIXES=0; NO_JAVA=0
HERE="$(cd "$(dirname "$0")" && pwd)"

while [ $# -gt 0 ]; do
    case "$1" in
        --dir)        SIMBA_DIR="${2:?--dir needs a path}"; shift 2 ;;
        --fresh)      FRESH=1; shift ;;
        --no-deps)    NO_DEPS=1; shift ;;
        --no-setcap)  NO_SETCAP=1; shift ;;
        --no-fixes)   NO_FIXES=1; shift ;;
        --no-java)    NO_JAVA=1; shift ;;
        --silent)     SILENT=1; shift ;;
        -h|--help)    sed -n '2,25p' "$0" | sed 's/^#\{0,1\} \{0,1\}//'; exit 0 ;;
        *)            echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

SIMBA_URL="https://github.com/Torwent/Simba/releases/latest/download/Simba-Linux64"
SRLB_URL="https://github.com/BigWaspBackup/SRL-B/archive/refs/heads/master.zip"
BASHLIB_URL="https://github.com/BigWaspBackup/BashLib/archive/refs/heads/master.zip"
LAUNCHER_URL="https://raw.githubusercontent.com/BigAussie/BASH/main/B.A.S.H%20Launcher.simba"
CONSOLAS_URL="https://github.com/tsenart/sight/raw/master/fonts/Consolas.ttf"
DISCORD="https://discord.gg/qsmKs5uKfR"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say()  { printf '  %s\n' "$*"; }
ok()   { printf '  \033[32m*\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n  \033[31mERROR\033[0m %s\n\n' "$*" >&2; exit 1; }

cat <<BANNER

  B.A.S.H - BigAussie Script House
  ================================
  Linux setup   |   Discord: $DISCORD

BANNER

# ---------------------------------------------------------------- prerequisites
for t in curl unzip; do
    command -v "$t" >/dev/null || die "'$t' is required but not installed."
done

# ------------------------------------------------------------------ native deps
# Simba is a GTK2 Lazarus app. gtk2 is the one that silently blocks startup:
# without it the binary exists and is executable but dies on missing
# libgtk-x11-2.0.so.0 / libgdk-x11-2.0.so.0.
if [ "$NO_DEPS" -eq 0 ]; then
    say "Installing native dependencies..."
    if   command -v pacman  >/dev/null; then
        sudo pacman -S --needed --noconfirm gtk2 libxtst libffi libcap \
            || die "pacman failed. Re-run with --no-deps if you manage deps yourself."
    elif command -v apt-get >/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y libgtk2.0-0 libxtst6 libffi8 libcap2-bin \
            || sudo apt-get install -y libgtk2.0-0 libxtst6 libffi7 libcap2-bin \
            || die "apt-get failed."
    elif command -v dnf     >/dev/null; then
        sudo dnf install -y gtk2 libXtst libffi libcap || die "dnf failed."
    elif command -v zypper  >/dev/null; then
        sudo zypper -n install gtk2 libXtst6 libffi8 libcap2 || die "zypper failed."
    else
        warn "Unknown distro - install GTK2, libXtst, libffi and libcap manually."
    fi
    ok "dependencies"
else
    say "Skipping native dependencies (--no-deps)"
fi

# ------------------------------------------------------------------- java <= 24
# RemoteInput's libremoteinput looks up java/applet/Applet. The Applet API was
# removed in JDK 25 (JEP 504), so on a newer JVM that lookup yields null and the
# injected code kills the client. The CLIENT's JVM is what matters, not Simba's.
have_applet_jvm() {
    for j in /usr/lib/jvm/*/bin/java; do
        [ -x "$j" ] || continue
        if "$j" --describe-module java.desktop 2>/dev/null | grep -q applet; then
            printf '%s' "$j"; return 0
        fi
    done
    return 1
}

JAVA_FOR_CLIENT=""
if [ "$NO_JAVA" -eq 0 ]; then
    if JAVA_FOR_CLIENT="$(have_applet_jvm)"; then
        ok "JVM with java.applet: $JAVA_FOR_CLIENT"
    else
        say "No installed JVM still has java.applet - installing jre17..."
        if   command -v pacman  >/dev/null; then sudo pacman -S --needed --noconfirm jre17-openjdk || true
        elif command -v apt-get >/dev/null; then sudo apt-get install -y openjdk-17-jre || true
        elif command -v dnf     >/dev/null; then sudo dnf install -y java-17-openjdk || true
        fi
        if JAVA_FOR_CLIENT="$(have_applet_jvm)"; then
            ok "JVM with java.applet: $JAVA_FOR_CLIENT"
        else
            warn "No JVM with java.applet. RemoteInput will fail to pair and will"
            warn "crash the client. Install jre17 (or any JVM <= 24) and re-run."
        fi
    fi
else
    say "Skipping the JVM check (--no-java)"
fi

# ------------------------------------------------------------------ directories
if [ "$FRESH" -eq 1 ] && [ -d "$SIMBA_DIR" ]; then
    if [ "$SILENT" -eq 0 ]; then
        printf '  --fresh will DELETE %s\n  Continue? [y/N] ' "$SIMBA_DIR"
        read -r reply < /dev/tty
        case "$reply" in [Yy]*) ;; *) die "aborted" ;; esac
    fi
    rm -rf "$SIMBA_DIR"
    ok "removed old $SIMBA_DIR"
fi

say "Creating directory tree..."
mkdir -p "$SIMBA_DIR"/{Data/packages,Includes,Scripts,Fonts,Plugins,Configs} \
    || die "could not create $SIMBA_DIR"
ok "$SIMBA_DIR"

# ----------------------------------------------------------------------- Simba
say "Downloading Simba (Torwent fork, Linux64)..."
curl -fsSL -o "$SIMBA_DIR/Simba" "$SIMBA_URL" || die "failed to download Simba from $SIMBA_URL"
chmod +x "$SIMBA_DIR/Simba"

# Guard against silently installing the wrong build again.
# NB: use grep -c, not grep -q. grep -q exits at the first match and closes the
# pipe, so strings dies of SIGPIPE and `set -o pipefail` reports the whole pipeline
# as failed -- producing a false "wrong build" warning. grep -c drains the input.
simba_syms="$(strings -a "$SIMBA_DIR/Simba" 2>/dev/null | grep -c 'SimbaOpenInTab' || true)"
if [ "${simba_syms:-0}" -eq 0 ]; then
    warn "This build lacks SimbaOpenInTab - the launcher will not compile."
    warn "That means a stock Villavu build was fetched instead of Torwent's fork."
else
    ok "Simba $(du -h "$SIMBA_DIR/Simba" | cut -f1) (SimbaOpenInTab present)"
fi

missing="$(ldd "$SIMBA_DIR/Simba" 2>/dev/null | grep 'not found' || true)"
[ -n "$missing" ] && { warn "unresolved libraries:"; printf '      %s\n' "$missing"; }

# ------------------------------------------------------------- default.simba
say "Writing default.simba and packages.ini..."
cat > "$SIMBA_DIR/Data/default.simba" <<'EOF'
(* Thank you for choosing B.A.S.H - BigAussie Script House *)
(* Discord: https://discord.gg/qsmKs5uKfR *)

(* To start simply double click the green play button. *)

begin
  SimbaRunInTab(ScriptPath + 'BashLauncher.simba');
end.
EOF

# Written to both locations, matching bash-setup.cmd.
cat > "$SIMBA_DIR/Data/packages.ini" <<EOF
[BigWaspBackup/SRL-B]
Name=SRL-B
Templates=$SIMBA_DIR/Includes/SRL-B/templates

[BigWaspBackup/BashLib]
Name=BashLib
Templates=$SIMBA_DIR/Includes/BashLib/templates
EOF
cp -f "$SIMBA_DIR/Data/packages.ini" "$SIMBA_DIR/Data/packages/packages.ini"
ok "default.simba + packages.ini"

# ------------------------------------------------------------------- packages
install_pkg() {  # $1=url  $2=dest-name  $3=archive-prefix
    say "Installing $2..."
    curl -fsSL -o "$TMP/$2.zip" "$1" || die "failed to download $2"
    unzip -qo "$TMP/$2.zip" -d "$TMP/x_$2" || die "failed to extract $2"
    rm -rf "${SIMBA_DIR:?}/Includes/$2"
    mv "$TMP/x_$2/$3"-* "$SIMBA_DIR/Includes/$2" || die "unexpected archive layout for $2"
    ok "$2 ($(du -sh "$SIMBA_DIR/Includes/$2" | cut -f1))"
}
install_pkg "$SRLB_URL"    SRL-B   SRL-B
install_pkg "$BASHLIB_URL" BashLib BashLib

# ------------------------------------------------------------------- launcher
# Must be BashLauncher.simba: default.simba calls SimbaRunInTab on that exact name.
say "Installing B.A.S.H Launcher as BashLauncher.simba..."
curl -fsSL -o "$SIMBA_DIR/Scripts/BashLauncher.simba" "$LAUNCHER_URL" \
    || die "failed to download the B.A.S.H Launcher"
ok "BashLauncher.simba ($(du -h "$SIMBA_DIR/Scripts/BashLauncher.simba" | cut -f1))"

# ----------------------------------------------------------- linux source fixes
# Everything below is a Linux-only defect in upstream BASH/BashLib/SRL-B. Each
# tool is idempotent and keeps backups. Once these land upstream this phase can
# go away; until then they must also be re-run after any in-launcher update,
# which re-downloads the launcher, the packages and the scripts.
if [ "$NO_FIXES" -eq 0 ]; then
    say "Applying Linux fixes..."

    if [ -f "$HERE/../B.A.S.H Launcher.simba" ]; then
        SIMBA_DIR="$SIMBA_DIR" "$HERE/install-to-simba.sh" >/dev/null 2>&1 \
            && ok "patched launcher installed" \
            || warn "install-to-simba.sh failed"
    else
        warn "patched launcher not found next to this script - using upstream's"
        warn "(the RuneLite profile button will take down your desktop session)"
    fi

    for t in fix-includes.py fix-scripts.py fix-plugin-execstack.py; do
        if [ -x "$HERE/$t" ]; then
            "$HERE/$t" "$SIMBA_DIR" >/dev/null 2>&1 \
                && ok "$t" \
                || warn "$t reported a problem - run it directly to see why"
        else
            warn "missing: $HERE/$t"
        fi
    done
else
    say "Skipping Linux fixes (--no-fixes)"
fi

# ----------------------------------------------------------------------- font
say "Installing Consolas (SRL OCR dependency)..."
mkdir -p "$HOME/.local/share/fonts"
if curl -fsSL -o "$HOME/.local/share/fonts/Consolas.ttf" "$CONSOLAS_URL"; then
    command -v fc-cache >/dev/null && fc-cache -f >/dev/null 2>&1
    ok "Consolas"
else
    warn "could not fetch Consolas - OCR may be degraded"
fi

# --------------------------------------------------------------------- setcap
# RemoteInput injects into a target JVM via ptrace. With Yama ptrace_scope=1
# (the common default) that is refused unless Simba carries cap_sys_ptrace.
# NOTE: file capabilities are wiped whenever the binary is replaced, so this
# must be re-run after every Simba update.
if [ "$NO_SETCAP" -eq 0 ]; then
    if command -v setcap >/dev/null; then
        say "Granting cap_sys_ptrace to Simba (needed for RemoteInput)..."
        if sudo setcap cap_sys_ptrace=eip "$SIMBA_DIR/Simba"; then
            ok "$(getcap "$SIMBA_DIR/Simba")"
        else
            warn "setcap failed - RemoteInput will not be able to attach"
        fi
    else
        warn "setcap not found (install libcap) - skipping"
    fi
else
    say "Skipping setcap (--no-setcap)"
fi

# ------------------------------------------------------------- desktop entry
mkdir -p "$HOME/.local/share/applications"

# Script GUIs are authored against Windows' light system colours; controls that
# inherit theme colours look wrong under a dark GTK theme. Give Simba alone a
# light theme rather than touching the desktop's.
cat > "$SIMBA_DIR/gtkrc-light" <<EOF
include "$HOME/.gtkrc-2.0"
gtk-theme-name="Breeze"
EOF

cat > "$HOME/.local/share/applications/simba.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Simba
Comment=Simba - B.A.S.H
Exec=env GTK2_RC_FILES=$SIMBA_DIR/gtkrc-light $SIMBA_DIR/Simba
Path=$SIMBA_DIR
Terminal=false
Categories=Development;
EOF
ok "desktop entry"

# The RuneLite launcher spawns the client with the JVM it runs under, and
# /usr/bin/runelite honours RUNELITE_JAVA. A user-level entry shadows the
# packaged one and survives package updates.
if [ -n "$JAVA_FOR_CLIENT" ] && command -v runelite >/dev/null; then
    cat > "$HOME/.local/share/applications/runelite.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=RuneLite
Comment=Open source Old School RuneScape client (JVM pinned for RemoteInput)
Exec=env RUNELITE_JAVA=$JAVA_FOR_CLIENT runelite
Icon=runelite
Terminal=false
Categories=Game;
EOF
    ok "runelite entry pinned to $JAVA_FOR_CLIENT"
fi
command -v update-desktop-database >/dev/null && \
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null

# -------------------------------------------------------------- verification
say "Verifying: compiling the launcher..."
compile_out="$("$SIMBA_DIR/Simba" --compile "$SIMBA_DIR/Scripts/BashLauncher.simba" 2>&1 \
               | grep -viE 'canberra|theme engine|XDisplay|^$')"
case "$compile_out" in
    *ompiled*) compile_ok=1 ;;
    *)         compile_ok=0 ;;
esac
if [ "$compile_ok" -eq 1 ]; then
    ok "$(printf '%s' "$compile_out" | grep -i compiled | head -1)"
else
    warn "launcher did not compile:"
    printf '      %s\n' "$compile_out"
fi

# ------------------------------------------------------------- linux caveats
echo
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
    warn "You are on WAYLAND. Simba is X11-only - screen capture and input will"
    warn "not work. Log into an X11/Xorg session before using it."
else
    ok "session type: ${XDG_SESSION_TYPE:-unknown} (X11 required, looks fine)"
fi

cat <<DONE

  Installation complete.

    Simba     : $SIMBA_DIR/Simba
    Launcher  : $SIMBA_DIR/Scripts/BashLauncher.simba
    Discord   : $DISCORD

  Start Simba and press the green play button - default.simba opens the launcher.

  Note: re-run the setcap step after any Simba update, file capabilities do not
  survive the binary being replaced:
      sudo setcap cap_sys_ptrace=eip "$SIMBA_DIR/Simba"

DONE

[ "$SILENT" -eq 0 ] && [ -t 0 ] && { printf '  Press enter to close... '; read -r _ < /dev/tty; }
exit 0
