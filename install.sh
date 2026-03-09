#!/usr/bin/env bash
#
# vlc-ai-subs — extension installer
# Copies aisubs.lua into all detected VLC extension directories.
# Supports VLC 3.x / 4.x on Linux (native, snap, flatpak) and macOS.

set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/aisubs.lua"

if [ ! -f "$SRC" ]; then
    echo "ERROR: aisubs.lua not found at $SRC"
    exit 1
fi

INSTALLED=0

install_to() {
    local dir="$1"
    local needs_sudo="${2:-false}"

    if [ -d "$dir" ]; then
        if [ "$needs_sudo" = "true" ]; then
            sudo cp "$SRC" "$dir/aisubs.lua"
        else
            mkdir -p "$dir"
            cp "$SRC" "$dir/aisubs.lua"
        fi
        echo "  ✓ $dir"
        INSTALLED=1
    fi
}

echo "Installing VLC extension..."
echo ""

# Linux — VLC 4.x (system)
install_to "/usr/lib/x86_64-linux-gnu/vlc/libexec/vlc/lua/extensions" true

# Linux — VLC 3.x (system, various distros)
install_to "/usr/lib/vlc/lua/extensions" true
install_to "/usr/lib64/vlc/lua/extensions" true
install_to "/usr/share/vlc/lua/extensions" true

# Linux — snap
if [ -d "$HOME/snap/vlc" ]; then
    install_to "$HOME/snap/vlc/current/.local/share/vlc/lua/extensions"
fi

# Linux — flatpak
if [ -d "$HOME/.var/app/org.videolan.VLC" ]; then
    install_to "$HOME/.var/app/org.videolan.VLC/data/vlc/lua/extensions"
fi

# Linux — user-level (VLC 3.x fallback)
install_to "$HOME/.local/share/vlc/lua/extensions"

# macOS
if [ -d "/Applications/VLC.app" ] || [ -d "$HOME/Applications/VLC.app" ]; then
    install_to "$HOME/Library/Application Support/org.videolan.vlc/lua/extensions"
fi

echo ""
if [ "$INSTALLED" -eq 0 ]; then
    echo "WARNING: No VLC extension directory found."
    echo "Copy aisubs.lua manually to your VLC lua/extensions folder."
    exit 1
fi

echo "Done! Restart VLC and check View > AI Subs Generator"
