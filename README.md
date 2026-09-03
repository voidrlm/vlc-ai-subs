# vlc-ai-subs

VLC media player plugin that generates subtitles using local AI — works offline
with any video, any language. Transcribe and translate into clean `.srt` files
or real-time on-screen captions.

[Upstream](https://github.com/voidrlm/vlc-ai-subs) · [Install](#quick-start) · [Engine](#engine) · [Models](#models) · [Env vars](#environment-variables)

## Features

| | |
|---|---|
| **Zero-config** | "Recommended (auto)" model + Translate to English by default — open a video, click Generate, done |
| **Word-level timing** | WhisperX wav2vec2 alignment on CUDA, or Parakeet's native TDT word timestamps (CPU too) |
| **Two engines** | WhisperX (multilingual, word-aligned) or Parakeet (English, ~10× faster) |
| **GPU acceleration** | CUDA auto-detected (int8_float16), CPU fallback — works on NVIDIA, AMD, Intel |
| **Two modes** | Real-time OSD (subtitles appear as they're generated) or Generate & Load SRT |
| **SRT output** | Standard `.srt` files written next to your video — compatible with Kdenlive, VLC, mpv, PotPlayer |
| **Any language** | Auto-detection or specify a language code (`en`, `es`, `fr`, `hi`, `ja`, `zh`…) |
| **Translation** | Translate any language to English subtitles |
| **VLC 3.x & 4.x** | Works with current and next-gen VLC |
| **Cross-platform** | Linux, macOS, Windows (native, snap, flatpak) |

## Quick Start

### Linux / macOS

```bash
git clone https://github.com/chethan62/vlc-ai-subs.git
cd vlc-ai-subs
./install.sh
```

`install.sh` is the full installer (WhisperX + Parakeet + NLLB translate
models + ffmpeg check + VLC extension sync; NLLB is skippable via
`VSCL_AISUBS_SKIP_NLLB=1`). `setup.sh` is the minimal WhisperX-only
variant (no Parakeet, no NLLB, no ffmpeg check).

### Windows

```powershell
git clone https://github.com/chethan62/vlc-ai-subs.git
cd vlc-ai-subs
setup.bat
```

Then:

1. **Restart VLC**
2. Open a video
3. **View → AI Subs Generator**
4. Click **Generate**

## Engines

| Engine | Languages | Word timing | Speed (this box) | License |
|---|---|---|---|---|
| **WhisperX** (default) | 99 (faster-whisper + wav2vec2 alignment) | wav2vec2 forced alignment | ~2–4× realtime (medium) | BSD-2 + MIT |
| **Parakeet** (opt-in: `VSCL_AISUBS_BACKEND=parakeet`) | English only | **native TDT word timestamps** (no aligner) | **~10× faster, CPU-friendly** | CC-BY-4.0 |

Pick **Parakeet** in the dialog for English films — WER 6.05% (beats Whisper
large-v3 7.44% on the Open-ASR leaderboard), ~0.7 GB int8 model, and its
transducer decoder structurally avoids the hallucination loops Whisper
hits on music/silence. WhisperX handles non-English and translate.

- WhisperX requires Python **< 3.14**, so it runs in its own Python 3.12 venv
  (`venv-whisperx`), launched as a subprocess with the same JSONL contract.
- The **"Recommended (auto)"** model is picked from GPU VRAM:
  large ≥ 8 GB, **large-v3-turbo ≥ 4 GB** (the 4 GB sweet spot — near-large
  accuracy at ~4× the speed), small ≥ 2 GB; CPU falls back to RAM-based sizing.
- To force CPU: `VSCL_AISUBS_DEVICE=cpu vlc`.
- WhisperX's wav2vec2 word alignment runs on **CUDA only**; on CPU the
  segments keep faster-whisper's timestamps (no alignment pass). Parakeet's
  native TDT word timestamps work on CPU as well.
- WhisperX decode is hardened for movies (beam 1, no cross-window
  conditioning, silence/hallucination gates) — research-backed, see
  `.research/final_report.md` §2.2.
- Translate uses the **NLLB-200 cascade** (WhisperX transcribes in the
  source language, NLLB-200 translates to English — research: ~44.7 BLEU
  CA→EN vs Whisper's built-in translate). The model is ~1.3 GB,
  **CC-BY-NC-4.0** (research/non-commercial); `VSCL_AISUBS_NLLB=0` reverts
  to Whisper translate, and unmapped languages fall back automatically.
- Parakeet decodes audio with `ffmpeg`, which must be on PATH — `install.sh`
  checks for it up front and aborts with a clear message otherwise (the
  runner also errors cleanly if ffmpeg is missing at runtime).
- Long media is decoded in ≤20-min chunks — the 0.6B TDT model's
  single-pass design limit is ~24 min (`.research/final_report.md` §2.1).

## Models

| Model | Speed | Accuracy | RAM | Download |
|-------|-------|----------|-----|----------|
| `tiny` | Fastest | Basic | ~1 GB | ~75 MB |
| `base` | Fast | Good | ~1 GB | ~140 MB |
| `small` | Moderate | Better | ~2 GB | ~460 MB |
| `medium` | Slow | Great | ~5 GB | ~1.5 GB |
| `large` | Slowest | Best | ~10 GB | ~3 GB |
| `large-v3-turbo` | Fast | Near-large | ~2 GB | ~1.6 GB |

Models are downloaded from Hugging Face on first use (cached in `~/.cache/huggingface` by default).

## Environment Variables

| Variable | Values | Default | Applies to |
|----------|--------|---------|------------|
| `VSCL_AISUBS_BACKEND` | `whisperx` \\| `parakeet` | `whisperx` | backend selection |
| `VSCL_AISUBS_DEVICE` | `cuda` \\| `cpu` | auto | WhisperX (runner) |
| `VSCL_AISUBS_COMPUTE` | `int8_float16` \\| `int8_float32` \\| `float16` \\| `float32` \\| `int8` | per device | WhisperX (runner) |
| `VSCL_AISUBS_MODEL_CACHE` | directory path | `~/.cache/huggingface` | WhisperX (runner) |
| `VSCL_AISUBS_NLLB` | `1` \| `0` | `1` | translate task (0 = Whisper translate) |
| `VSCL_AISUBS_NLLB_MODEL` | directory path | `~/.local/share/vlc-ai-subs/nllb-200-distilled-1.3B-int8` | translate task |
| `VSCL_AISUBS_NLLB_FAMILY` | `nllb` \| `m2m100` | `nllb` | cascade model family (m2m100 = MIT) |
| `VSCL_AISUBS_BLOCKLIST` | `1` \| `0` | `1` | hallucination-phrase filter (research §2.2) |

## Architecture

```
aisubs.lua                   VLC extension (dialog + timer polling)
aisubs_whisper.py            CLI entry-point (args → backend → JSONL → SRT)
whisperx_runner.py           WhisperX inside the Python 3.12 venv (subprocess)
parakeet_runner.py           Parakeet TDT via sherpa-onnx (same JSONL contract)
core/
  emitter.py                 JSONL + Lua poll-mirror output
  srt.py                     SRT timestamp formatting + file writing
backends/
  base.py                    TranscriptionBackend ABC
  whisperx_backend.py        WhisperX (Python 3.12 subprocess, PYTHONPATH-cleaned)
  parakeet.py                Parakeet (sherpa-onnx, English, CPU)
```

**JSONL contract (stdout):** `{"type":"status","msg":...}`, `{"type":"sub","i":N,"start":S,"end":E,"text":...}`, `{"type":"done","segments":N,"srt_path":...}`, `{"type":"error","msg":...}`. Lua polls the mirror file (argv[5]) for progress.

## Testing

### Automated tests (dev)

```bash
cd vlc-ai-subs
python3 -m venv venv && venv/bin/pip install pytest              # one-time
PYTHONPATH= venv/bin/python -m pytest tests/ -v               # suite: 82 tests (model-free)
```

Coverage: SRT formatting (float-drift-safe rounding, rollover, clamp),
JSONL emitter + mirror file, VRAM/RAM model recommendation (boundary cases),
backend resolution (WhisperX default, Parakeet opt-in, missing-backend errors),
runner CLI errors, and the main CLI's JSONL error contract. No WhisperX
model download needed — transcription is out of scope for unit tests.

The `PYTHONPATH=` prefix neutralizes any foreign `PYTHONPATH` exported by
the calling shell (e.g. a desktop-agent terminal), which would otherwise
shadow packages with an unrelated interpreter's site-packages.

### End-to-end (installed plugin)

```bash
# 1. Run the backend directly (bypasses VLC)
~/.local/share/vlc-ai-subs/venv/bin/python3 \
  ~/.local/share/vlc-ai-subs/aisubs_whisper.py \
  /path/to/video.mp4 recommended auto translate

# 2. Check the .srt file written next to the video
ls -la /path/to/video.srt

# 3. Confirm WhisperX CUDA is active (watch the status lines)
~/.local/share/vlc-ai-subs/venv-whisperx/bin/python -c "import torch; print(torch.cuda.is_available())"
# Should print: True
```

In VLC: restart → open a video → **View → AI Subs Generator** → click **Generate**.

## Debugging

Add `--debug` to the CLI args (VLC already appends it to every run it
launches) or set `VSCL_AISUBS_DEBUG=1`. This writes:

| File | Contents |
|------|----------|
| `/tmp/aisubs_debug.log` | main CLI phases + timings (args, backend, model pick, segment count, elapsed) |
| `/tmp/aisubs_whisperx.log` | full subprocess stdout+stderr dump (WhisperX runtime logs) |
| `/tmp/aisubs_parakeet.log` | full subprocess stdout+stderr dump (Parakeet runtime logs) |

Debug lines are also mirrored to stderr, so they appear in VLC's own logs
(`vlc -vvv`). Failed WhisperX runs additionally include the stderr tail and
stdout's last JSONL line in the emitted error — no more silent failures.

## Options

- **Engine** — WhisperX (multilingual, word-aligned; default) or Parakeet (English, fastest).
- **Model** — `Recommended (auto)` (VRAM-aware) or `tiny` / `base` / `small` / `medium` / `large` / `large-v3-turbo`.
- **Language** — `auto` for detection, or a code like `en`, `es`, `fr`, `hi`, `ja`, `zh`, etc.
- **Task** — `Translate to English` (default) or `Transcribe (same language)`.
- **Mode** — `Generate & Load SRT` (default) or `Real-time OSD`.

## Manual Installation

If the setup script doesn't work for your system:

1. Install WhisperX (Python 3.12 venv):
   ```bash
   uv venv --python 3.12 venv-whisperx
   uv pip install --python venv-whisperx/bin/python whisperx
   ```
2. Copy `aisubs.lua` to your VLC extensions folder:
   - **Linux**: `~/.local/share/vlc/lua/extensions/`
   - **macOS**: `~/Library/Application Support/org.videolan.vlc/lua/extensions/`
   - **Windows**: `%APPDATA%\vlc\lua\extensions\`
3. Place the Python files (`aisubs_whisper.py`, `whisperx_runner.py`, `nllb_translate.py`, `parakeet_runner.py`, `core/`, `backends/`) next to `venv-whisperx` (the backend falls back to `~/.local/share/vlc-ai-subs/`).
4. Restart VLC.

## Credits

- [voidrlm/vlc-ai-subs](https://github.com/voidrlm/vlc-ai-subs) — original VLC plugin (Lua extension)
- [m-bain/whisperX](https://github.com/m-bain/whisperX) — word-level forced alignment
- [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) — CTranslate2 Whisper

## License

Plugin code: **MIT** (see LICENSE). Models are separate runtime downloads, each
with its own license — checked per model card:

| Model | License | Use in the plugin |
|---|---|---|
| faster-whisper / WhisperX | MIT | default engine (multilingual, word-aligned) |
| Parakeet-TDT-0.6B-v2 | CC-BY-4.0 (commercial OK) | English ASR engine |
| NLLB-200 (translate cascade, default) | **CC-BY-NC-4.0** | personal / non-commercial |
| M2M-100 1.2B (translate cascade, optional) | **MIT** | commercial use |

**Translate license decision**: NLLB-200 is the default cascade model — best
quality (research: 44.7 BLEU CA→EN) and its CC-BY-NC-4.0 license permits
personal/non-commercial use, which covers this plugin's typical use. It is
flagged at install time and skippable (`VSCL_AISUBS_SKIP_NLLB=1`), and
`VSCL_AISUBS_NLLB=0` reverts to Whisper translate (MIT). For commercial
deployment, install the MIT-licensed M2M-100 cascade instead:

```bash
bash install-m2m-model.sh          # sentencepiece + M2M-100 1.2B (~2.5 GB, fp16 weights, int8 compute)
VSCL_AISUBS_NLLB_FAMILY=m2m100 VSCL_AISUBS_NLLB_MODEL=~/.local/share/vlc-ai-subs/m2m100_1.2B-int8 vlc
```

M2M-100 covers 100 languages (vs NLLB's 200) at somewhat lower quality — the
trade for a permissive license. Unmapped languages fall back to Whisper
translate in either family.