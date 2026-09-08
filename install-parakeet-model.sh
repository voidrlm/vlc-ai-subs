#!/usr/bin/env bash
#
# install-parakeet-model.sh — download NVIDIA Parakeet-TDT-0.6B-v2 (int8, ONNX)
#
# English-only, CC-BY-4.0, ~0.7GB int8. Used by the vlc-ai-subs Parakeet
# backend (VSCL_AISUBS_BACKEND=parakeet). Idempotent.
#
set -euo pipefail

DEST="$HOME/.local/share/sherpa-onnx/models"
NAME="sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/${NAME}.tar.bz2"

mkdir -p "$DEST"
cd "$DEST"

if [ -f "$NAME/encoder.int8.onnx" ] && [ -f "$NAME/tokens.txt" ]; then
    echo "  ✓ Parakeet model already installed ($DEST/$NAME)"
    exit 0
fi

echo "  → Downloading $NAME ..."
curl -L --fail --progress-bar -o "$NAME.tar.bz2" "$URL"

echo "  → Extracting..."
tar xf "$NAME.tar.bz2"
rm -f "$NAME.tar.bz2"

ls -lh "$NAME"/*.onnx "$NAME"/tokens.txt
echo "  ✓ Parakeet model ready: $DEST/$NAME"