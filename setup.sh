#!/usr/bin/env bash
#
# vlc-ai-subs — setup & install
# Installs Python dependencies and copies the VLC extension to all detected
# VLC extension directories. Supports VLC 3.x / 4.x on Linux (native, snap,
# flatpak) and macOS.
#
# Usage:
#   ./setup.sh            Full setup (Python deps + VLC extension)
#   ./setup.sh --install   Only install/update the VLC extension
#
# Requirements:
#   - Python 3.8+
#   - VLC 3.x or 4.x
#   - Internet connection (to download Whisper models on first use)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
SRC="$SCRIPT_DIR/aisubs.lua"

# ── VLC extension installer ─────────────────────────────────

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

install_vlc_extension() {
    if [ ! -f "$SRC" ]; then
        echo "ERROR: aisubs.lua not found at $SRC"
        exit 1
    fi

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
}

# ── Install-only mode ────────────────────────────────────────

if [ "${1:-}" = "--install" ]; then
    install_vlc_extension
    echo "Done! Restart VLC and check View > AI Subs Generator"
    exit 0
fi

# ── Full setup ───────────────────────────────────────────────

echo "=== vlc-ai-subs setup ==="
echo ""

# 1. Ensure python3-venv is available (Linux)
if [[ "${OSTYPE:-}" == linux* ]]; then
    if ! python3 -m venv --help &>/dev/null; then
        echo "Installing python3-venv..."
        PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        sudo apt-get install -y "python${PY_VER}-venv" || sudo apt-get install -y python3-venv
    fi
fi

# 2. Create virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# 3. Install faster-whisper
echo "Installing faster-whisper..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet faster-whisper

echo ""
"$VENV_DIR/bin/python3" -c "from faster_whisper import WhisperModel; print('faster-whisper installed successfully!')"

# 4. Install VLC extension
echo ""
install_vlc_extension

echo ""
echo "=== Setup complete ==="
echo ""
echo "  1. Restart VLC"
echo "  2. Go to View > AI Subs Generator"
echo "  3. Play a video and click Generate"
echo ""
