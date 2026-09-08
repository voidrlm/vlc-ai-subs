#!/usr/bin/env python3
"""
vlc-ai-subs — Whisper transcription backend for VLC.

Architecture
────────────
  aisubs_whisper.py        CLI entry-point (you are here)
  core/
    emitter.py             JSONL output + file mirror for Lua polling
    srt.py                 SRT timestamp formatting and file writing
  backends/
    base.py                Abstract TranscriptionBackend
    whisperx_backend.py    WhisperX (word-aligned, Python 3.12 subprocess) — default
    parakeet.py            Parakeet TDT via sherpa-onnx (English, CPU, ~10x faster)

Usage
─────
  python3 aisubs_whisper.py <media> <model> <language> <task> [out_file] [srt_path]

Output (stdout) — one JSON object per line
  {"type": "status", "msg": "..."}
  {"type": "sub", "i": N, "start": S, "end": E, "text": "..."}
  {"type": "done", "segments": N, "srt_path": "..."}
  {"type": "error", "msg": "..."}
"""

import os
import sys
import time
import traceback

from core.emitter import Emitter
from core.srt import write_srt
from core.blocklist import filter_segments
from backends import resolve_backend

# ── Debug logging ────────────────────────────────────────────────────
# Enable with a trailing `--debug` CLI arg or VSCL_AISUBS_DEBUG=1.
# Debug lines go to stderr AND /tmp/aisubs_debug.log (VLC itself shows
# stderr in its logs; the file survives terminal restarts).

DEBUG_FILE = "/tmp/aisubs_debug.log"


def _debug_enabled() -> bool:
    return os.environ.get("VSCL_AISUBS_DEBUG") == "1" or "--debug" in sys.argv


def _log_debug(msg: str) -> None:
    line = f"[debug {time.strftime('%H:%M:%S')}] {msg}"
    sys.stderr.write(line + "\n")
    try:
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ── Hardware-aware model recommendation ──────────────────────────────────

def _detect_vram_mb() -> int:
    """Return GPU VRAM in MiB via nvidia-smi, or 0 if detection fails."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader"],
            text=True, timeout=5,
        )
        return int(out.strip().split()[0])
    except Exception:
        return 0


def _detect_ram_gb() -> int:
    """Return system RAM in GiB from /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb // (1024 * 1024)  # KB → GiB
    except Exception:
        pass
    return 4  # conservative default


def _recommend_model(backend_name: str = "whisperx") -> str:
    """Pick the model based on GPU VRAM (system RAM on CPU).

    WhisperX transcribes via faster-whisper (CTranslate2, int8_float16 on
    CUDA) — roughly 2× the VRAM footprint of GGML models. When a GPU is
    detected, only VRAM tiering applies (never fall through to RAM sizing,
    which could over-recommend for a small GPU).

    Research (2026-08): large-v3-turbo (809M) is WhisperX's accuracy/speed
    sweet spot — near-large WER at ~4× the speed, ~1.5-1.8GB VRAM int8.
    """
    vram_mb = _detect_vram_mb()
    if vram_mb > 0:
        if vram_mb >= 8000:   return "large"
        elif vram_mb >= 4000: return "large-v3-turbo"
        elif vram_mb >= 2000: return "small"
        return "base"

    # No usable GPU — CPU path, bound by system RAM
    ram_gb = _detect_ram_gb()
    if ram_gb >= 8:   return "medium"
    elif ram_gb >= 4: return "small"
    return "base"


# ── CLI entry-point ──────────────────────────────────────────────────────

def main():
    _t0 = time.time()
    # --debug may appear anywhere; capture BEFORE stripping, then remove it
    # so positional parsing is unaffected.
    debug = _debug_enabled()
    if "--debug" in sys.argv:
        sys.argv.remove("--debug")
    if debug:
        # Propagate to the WhisperX subprocess (backend dumps runner output)
        os.environ["VSCL_AISUBS_DEBUG"] = "1"

    if len(sys.argv) < 5:
        sys.stderr.write(
            "Usage: aisubs_whisper.py <media> <model> <lang> <task> [out_file] [srt_path]\n"
        )
        sys.exit(1)

    media_path = sys.argv[1]
    model_name = sys.argv[2]
    language = sys.argv[3] if sys.argv[3] != "auto" else None
    task = sys.argv[4]
    mirror_file = sys.argv[5] if len(sys.argv) > 5 else None
    srt_requested = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6].strip() else None

    if debug:
        _log_debug(f"args: media={media_path!r} model={model_name!r} lang={language!r} task={task!r}")

    emitter = Emitter(mirror_file)

    if not os.path.isfile(media_path):
        emitter.emit({"type": "error", "msg": f"File not found: {media_path}"})
        emitter.close()
        sys.exit(1)

    try:
        backend = resolve_backend()
    except RuntimeError as exc:
        emitter.emit({"type": "error", "msg": str(exc)})
        emitter.close()
        sys.exit(1)
    if debug:
        _log_debug(f"backend resolved: {backend.name()} ({time.time() - _t0:.1f}s)")

    # Resolve "recommended" → best model for this backend + hardware
    if model_name == "recommended":
        model_name = _recommend_model(backend.name())
        if debug:
            _log_debug(
                f"recommended -> {model_name} (VRAM {_detect_vram_mb()} MiB, RAM {_detect_ram_gb()} GiB)"
            )

    emitter.emit({
        "type": "status",
        "msg": f"Backend: {backend.name()} — {model_name} ({language or 'auto'}, {task})",
    })

    # Transcribe
    emitter.emit({"type": "status", "msg": "Transcribing..."})
    segments = []
    _t1 = time.time()
    try:
        for seg in backend.transcribe(media_path, model_name, language, task):
            segment = {
                "start": round(seg["start"], 3),
                "end": round(seg["end"], 3),
                "text": seg["text"],
            }
            segments.append(segment)
            emitter.emit({
                "type": "sub",
                "i": len(segments),
                **segment,
            })
    except Exception as exc:
        emitter.emit({
            "type": "error",
            "msg": f"Transcription failed: {exc}\n{traceback.format_exc()}",
        })
        emitter.close()
        sys.exit(1)
    if debug:
        _log_debug(f"transcription done: {len(segments)} segments in {time.time() - _t1:.1f}s")

    # Write SRT (skip if no segments — avoids empty .srt files)
    # Drop known hallucination segments (research §2.2) before writing.
    raw_empty = not segments
    segments = filter_segments(segments)
    if not segments:
        msg = ("No speech detected — skipping SRT." if raw_empty
               else "All segments filtered by the hallucination blocklist — skipping SRT.")
        emitter.emit({"type": "status", "msg": msg})
        emitter.emit({"type": "done", "segments": 0, "srt_path": None})
        emitter.close()
        sys.exit(0)

    try:
        srt_path = write_srt(segments, media_path, srt_requested)
    except OSError as exc:
        # Media dir may be read-only (mounted disc, network share) — fall
        # back to a writable temp path instead of aborting after a
        # successful run; the status line tells the user where it went.
        import tempfile
        fallback = os.path.join(
            tempfile.gettempdir(), f"aisubs_{int(time.time())}_{os.getpid()}.srt"
        )
        try:
            srt_path = write_srt(segments, media_path, fallback)
        except OSError as exc2:
            emitter.emit({"type": "error", "msg": f"Could not write SRT: {exc2}"})
            emitter.close()
            sys.exit(1)
        emitter.emit({
            "type": "status",
            "msg": f"Could not write SRT next to media ({exc}); wrote {srt_path} instead.",
        })

    emitter.emit({"type": "done", "segments": len(segments), "srt_path": srt_path})
    if debug:
        _log_debug(f"done: {len(segments)} segments -> {srt_path} (total {time.time() - _t0:.1f}s)")
    emitter.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            print(
                '{"type": "error", "msg": "%s"}' % str(exc).replace('"', '\\"'),
                flush=True,
            )
        except OSError:
            pass
        sys.exit(1)
