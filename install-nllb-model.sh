#!/usr/bin/env bash
#
# install-nllb-model.sh — download NLLB-200-distilled-1.3B (ctranslate2 int8)
# for the translate cascade (WhisperX transcribes → NLLB translates to English).
#
# ~1.3 GB. LICENSE: CC-BY-NC-4.0 (research / non-commercial) — the model is a
# separate runtime download; the plugin code stays MIT. Set VSCL_AISUBS_NLLB=0
# to use Whisper's built-in translate instead. Idempotent.
#
set -euo pipefail

DEST="$HOME/.local/share/vlc-ai-subs/nllb-200-distilled-1.3B-int8"
REPO="michaelfeil/ct2fast-nllb-200-distilled-1.3B"
VENV_PY="$HOME/.local/share/vlc-ai-subs/venv-whisperx/bin/python"

if [ -f "$DEST/model.bin" ]; then
    echo "  ✓ NLLB model already installed ($DEST)"
    exit 0
fi

if [ ! -x "$VENV_PY" ]; then
    echo "  ✗ venv-whisperx python not found at $VENV_PY — run install.sh first"
    exit 1
fi

echo "  → Downloading NLLB-200-distilled-1.3B (int8, ~1.3 GB, CC-BY-NC-4.0)..."
mkdir -p "$(dirname "$DEST")"
"$VENV_PY" - "$REPO" "$DEST" <<'EOF'
import os
import sys
from huggingface_hub import snapshot_download

repo, dest = sys.argv[1], sys.argv[2]
os.makedirs(dest, exist_ok=True)
snapshot_download(repo, local_dir=dest)
EOF

ls -lh "$DEST"/model.bin
echo "  ✓ NLLB model ready: $DEST"
echo "    (translate task uses it; VSCL_AISUBS_NLLB=0 reverts to Whisper translate)"
