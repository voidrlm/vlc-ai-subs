#!/usr/bin/env bash
#
# vlc-ai-subs — sherpa-onnx model downloader
#
# Downloads a Whisper ONNX model from k2-fsa's model zoo into
# ~/.local/share/sherpa-onnx/models/<name>/.
#
# Usage:
#   ./install-sherpa-onnx-model.sh [MODEL]
#   MODEL ∈ tiny tiny.en base base.en small small.en medium medium.en
#           (default: small.en)
#
set -euo pipefail

MODEL="${1:-small.en}"
SHARE="$HOME/.local/share/sherpa-onnx/models"
DEST="$SHARE/sherpa-onnx-whisper-$MODEL"
URL_BASE="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models"

log() { printf '  -> %s\n' "$*"; }
ok()  { printf '  [ok] %s\n' "$*"; }

# Map model names to release tarball names
case "$MODEL" in
  tiny)     TAR="sherpa-onnx-whisper-tiny.tar.bz2" ;;
  tiny.en)  TAR="sherpa-onnx-whisper-tiny.en.tar.bz2" ;;
  base)     TAR="sherpa-onnx-whisper-base.tar.bz2" ;;
  base.en)  TAR="sherpa-onnx-whisper-base.en.tar.bz2" ;;
  small)    TAR="sherpa-onnx-whisper-small.tar.bz2" ;;
  small.en) TAR="sherpa-onnx-whisper-small.en.tar.bz2" ;;
  medium)   TAR="sherpa-onnx-whisper-medium.tar.bz2" ;;
  medium.en) TAR="sherpa-onnx-whisper-medium.en.tar.bz2" ;;
  *) echo "Unknown model '$MODEL'. Use: tiny|tiny.en|base|base.en|small|small.en|medium|medium.en"; exit 1 ;;
esac

mkdir -p "$SHARE"

if [ -d "$DEST" ]; then
    ok "Model already present: $DEST"
else
    URL="$URL_BASE/$TAR"
    # A random, freshly-created name — a fixed /tmp/$TAR path could be
    # pre-planted as a symlink by another local user (curl -o follows it).
    TMP_TAR="$(mktemp "${TMPDIR:-/tmp}/aisubs-XXXXXX")"
    log "Downloading $MODEL model ($URL)..."
    curl -L --fail --progress-bar -o "$TMP_TAR" "$URL" || { echo "[ERR] Download failed"; rm -f "$TMP_TAR"; exit 1; }
    log "Extracting to $SHARE ..."
    tar xvf "$TMP_TAR" -C "$SHARE" >/dev/null
    rm -f "$TMP_TAR"
    ok "Model installed: $DEST"
fi

echo ""
echo "Done. sherpa-onnx Whisper model ready: $DEST"
echo "The plugin auto-detects it on next run."
