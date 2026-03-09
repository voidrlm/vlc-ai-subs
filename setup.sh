#!/usr/bin/env bash
#
# vlc-ai-subs — setup script
# Installs Python dependencies and the VLC extension.
#
# Usage:
#   ./setup.sh
#
# Requirements:
#   - Python 3.8+
#   - VLC 3.x or 4.x
#   - Internet connection (to download Whisper models on first use)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

echo "=== vlc-ai-subs setup ==="
echo ""

# ── 1. Ensure python3-venv is available (Linux) ──────────────
if [[ "${OSTYPE:-}" == linux* ]]; then
    if ! python3 -m venv --help &>/dev/null; then
        echo "Installing python3-venv..."
        PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        sudo apt-get install -y "python${PY_VER}-venv" || sudo apt-get install -y python3-venv
    fi
fi

# ── 2. Create virtual environment ────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# ── 3. Install faster-whisper ────────────────────────────────
echo "Installing faster-whisper..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet faster-whisper

echo ""
"$VENV_DIR/bin/python3" -c "from faster_whisper import WhisperModel; print('faster-whisper installed successfully!')"

# ── 4. Install VLC extension ────────────────────────────────
echo ""
echo "Installing VLC extension..."
bash "$SCRIPT_DIR/install.sh"

echo ""
echo "=== Setup complete ==="
echo ""
echo "  1. Restart VLC"
echo "  2. Go to View > AI Subs Generator"
echo "  3. Play a video and click Generate"
echo ""
