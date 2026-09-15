#!/usr/bin/env bash
#
# vlc-ai-subs — whisper.cpp (Vulkan) backend installer
#
# Builds, installs and wires whisper.cpp into the VLC subtitle plugin.
# whisper.cpp is the ONLY Whisper runtime with a Vulkan backend, so this is
# the "GPU without CUDA" path. faster-whisper remains the CPU/CUDA fallback.
#
# Installs to:
#   ~/.local/share/whisper-cpp/          binaries + models
#   ~/.local/bin/                        whisper-cli symlink
#
# Usage:
#   ./install-whisper-cpp.sh [MODEL]     # MODEL ∈ tiny base small medium large (default small)
#
set -euo pipefail

MODEL="${1:-small}"
PREFIX="$HOME/.local"
SHARE="$PREFIX/share/whisper-cpp"
BINDIR="$PREFIX/bin"
REPO="ggml-org/whisper.cpp"
TAG="v1.9.2"

log() { printf '  -> %s\n' "$*"; }
ok()  { printf '  [ok] %s\n' "$*"; }
err() { printf '  [ERR] %s\n' "$*" >&2; exit 1; }

# valid model -> exact ggml file
case "$MODEL" in
  tiny)   MM="ggml-tiny.bin" ;;
  base)   MM="ggml-base.bin" ;;
  small)  MM="ggml-small.bin" ;;
  medium) MM="ggml-medium.bin" ;;
  large)  MM="ggml-large-v3-turbo.bin" ;;
  *) err "Unknown model '$MODEL'. Use tiny/base/small/medium/large" ;;
esac

mkdir -p "$BINDIR"

#───────────────────────────────────────────── 1. Source
log "Cloning whisper.cpp ($REPO @ $TAG)..."
SRC="$(mktemp -d /tmp/whisper-cpp-XXXXXX)"
git clone --depth 1 --branch "$TAG" "https://github.com/$REPO" "$SRC" 2>&1 | tail -1
git -C "$SRC" submodule update --init --recursive 2>&1 | tail -1 || true

#───────────────────────────────────────────── 2. Build (Vulkan)
if ! command -v glslc >/dev/null 2>&1; then
    err "glslc not found — install shaderc (pacman -S shaderc glslang)"
fi
log "Building with GGML_VULKAN=ON (Makefiles, Release, RPATH=\$ORIGIN)..."
cmake -S "$SRC" -B "$SRC/build" -DGGML_VULKAN=ON \
      -DGGML_VULKAN_MALLOC=M_PROPERTY \
      -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX="$SHARE" \
      -DCMAKE_INSTALL_LIBDIR=. \
      -DCMAKE_INSTALL_BINDIR=. \
      -DCMAKE_INSTALL_RPATH='$ORIGIN' \
      >/tmp/whisper-cmake.log 2>&1 || { tail -30 /tmp/whisper-cmake.log; err "CMake configure failed"; }
cmake --build "$SRC/build" --config Release --parallel 2>&1 | tail -5

#───────────────────────────────────────────── 3. Install binaries + libs
# Flat layout: bin + libs side by side in $SHARE, RUNPATH=$ORIGIN (baked at
# link time) so whisper-cli finds its sibling .so files no matter how it is
# launched (VLC subprocess, symlink from ~/.local/bin, etc.).
log "Installing to $SHARE (flat layout)..."
mkdir -p "$SHARE"
cmake --install "$SRC/build" --prefix "$SHARE" \
      >/tmp/whisper-install.log 2>&1 || { tail -20 /tmp/whisper-install.log; err "cmake --install failed"; }

[ -x "$SHARE/whisper-cli" ] || err "whisper-cli missing after install"
chmod +x "$SHARE/whisper-cli"
ln -sf "$SHARE/whisper-cli" "$BINDIR/whisper-cli"
for so in "$SHARE"/libggml*.so* "$SHARE"/libwhisper*.so*; do
    [ -e "$so" ] && chmod +x "$so" || true
done
ok "Binary: $SHARE/whisper-cli"

#───────────────────────────────────────────── 4. Model (idempotent)
if [ -f "$SHARE/$MM" ]; then
    ok "Model already present: $SHARE/$MM"
else
    log "Downloading $MODEL model ($MM)..."
    URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MM"
    curl -L --fail --progress-bar -o "$SHARE/$MM" "$URL" || err "Model download failed ($URL)"
    ok "Model: $SHARE/$MM"
fi

#───────────────────────────────────────────── 5. Plugin wiring config
printf 'whisper_bin=%s\nwhisper_model=%s\n' \
    "$SHARE/whisper-cli" "$SHARE/$MM" > "$SHARE/vlc-ai-subs.conf"
ok "Config: $SHARE/vlc-ai-subs.conf"

rm -rf "$SRC"
log ""
log "DONE. whisper.cpp Vulkan installed:"
log "  binary  $SHARE/whisper-cli"
log "  model   $SHARE/$MM ($(du -h "$SHARE/$MM" | cut -f1))"
log ""
log "The VLC plugin uses this binary automatically; faster-whisper remains"
log "the CPU/CUDA fallback if whisper-cli is missing."
