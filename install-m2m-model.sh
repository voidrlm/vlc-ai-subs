#!/usr/bin/env bash
#
# install-m2m-model.sh — MIT-licensed M2M-100 1.2B (ctranslate2, fp16 weights,
# loaded with int8 compute) as the commercial-use alternative to the
# CC-BY-NC-4.0 NLLB cascade model.
#
# ~2.5 GB download. After installing, run the cascade with:
#   VSCL_AISUBS_NLLB_FAMILY=m2m100 VSCL_AISUBS_NLLB_MODEL=$HOME/.local/share/vlc-ai-subs/m2m100_1.2B-int8 vlc
#
# M2M-100 covers 100 languages (NLLB: 200) at somewhat lower quality — the
# trade for a permissive license. Idempotent.
#
set -euo pipefail

DEST="$HOME/.local/share/vlc-ai-subs/m2m100_1.2B-int8"
REPO="michaelfeil/ct2fast-m2m100_1.2B"
VENV_PY="$HOME/.local/share/vlc-ai-subs/venv-whisperx/bin/python"

if [ -f "$DEST/model.bin" ]; then
    echo "  ✓ M2M-100 model already installed ($DEST)"
    exit 0
fi

if [ ! -x "$VENV_PY" ]; then
    echo "  ✗ venv-whisperx python not found at $VENV_PY — run install.sh first"
    exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
    echo "  ✗ uv not found (needed for sentencepiece). Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "  → Installing sentencepiece (M2M tokenizer dependency)..."
uv pip install --python "$VENV_PY" sentencepiece

echo "  → Downloading M2M-100 1.2B (fp16 weights, ~2.5 GB, MIT)..."
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
echo "  ✓ M2M-100 ready: $DEST"
echo "    run: VSCL_AISUBS_NLLB_FAMILY=m2m100 VSCL_AISUBS_NLLB_MODEL=$DEST vlc"
