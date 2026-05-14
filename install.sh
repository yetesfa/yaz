#!/usr/bin/env bash
# Yaz installer — Ubuntu / Debian / Pop!_OS
#
# Installs system deps via apt (one sudo prompt), creates a Python venv with
# PyQt6 inside the repo, symlinks `yaz` onto your PATH, registers a desktop
# entry, and prints a "ready" message.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
APP_NAME="Yaz"

# --- pretty output ---
red()    { printf '\033[31m%s\033[0m\n'   "$*"; }
green()  { printf '\033[32m%s\033[0m\n'   "$*"; }
yellow() { printf '\033[33m%s\033[0m\n'   "$*"; }
bold()   { printf '\033[1m%s\033[0m\n'    "$*"; }

bold "▶  Installing $APP_NAME from $REPO_DIR"
echo

# --- 1. system deps ---
NEEDED_APT="python3-venv python3-gi gnome-screenshot wl-clipboard"
MISSING_APT=""
for pkg in $NEEDED_APT; do
    dpkg -s "$pkg" >/dev/null 2>&1 || MISSING_APT="$MISSING_APT $pkg"
done
if [ -n "$MISSING_APT" ]; then
    yellow "Installing system packages:$MISSING_APT"
    if command -v pkexec >/dev/null 2>&1 && [ -z "${TERM:-}" -o -z "${SUDO_USER:-}" ]; then
        pkexec apt-get install -y $MISSING_APT
    else
        sudo apt-get update
        sudo apt-get install -y $MISSING_APT
    fi
else
    green "✓ System packages already installed"
fi

# --- 2. python venv + PyQt6 ---
if [ ! -d "$REPO_DIR/.venv" ]; then
    yellow "Creating virtualenv at $REPO_DIR/.venv"
    python3 -m venv --system-site-packages "$REPO_DIR/.venv"
fi
yellow "Installing PyQt6 inside the venv"
"$REPO_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$REPO_DIR/.venv/bin/pip" install --quiet 'PyQt6>=6.5'
green "✓ Python environment ready"

# --- 3. symlink onto PATH ---
mkdir -p "$HOME/.local/bin"
ln -sf "$REPO_DIR/yaz" "$HOME/.local/bin/yaz"
green "✓ Symlinked yaz → $HOME/.local/bin/yaz"

# --- 4. desktop entry (path-aware) ---
mkdir -p "$HOME/.local/share/applications"
sed -e "s|@PREFIX@|$REPO_DIR|g" "$REPO_DIR/yaz.desktop.in" \
    > "$HOME/.local/share/applications/yaz.desktop"
update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
green "✓ Desktop entry installed"

echo
bold "🎉  Done. Run with:"
echo "      yaz"
echo
echo "Or launch from your apps grid: search for $APP_NAME."
echo

# --- 5. PATH check ---
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *)
        yellow "⚠  $HOME/.local/bin is not on your PATH yet."
        echo "   Add this line to your shell config and restart your terminal:"
        echo "      export PATH=\"\$HOME/.local/bin:\$PATH\""
        ;;
esac
