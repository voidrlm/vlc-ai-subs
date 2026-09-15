#!/usr/bin/env python3
"""
Parakeet runner — invoked by the plugin as a subprocess inside the Python
3.12 venv (sherpa-onnx). English-only, NVIDIA Parakeet-TDT-0.6B-v2 int8.

Why (2026-08 research): native word-level timestamps (no aligner step),
WER 6.05% (beats Whisper large-v3 7.44%), ~10x faster, ~0.7GB int8,
CC-BY-4.0, transducer blanking = no hallucination loops on music.

Contract (stdout, JSONL) — same as whisperx_runner:
  {"type": "status", "msg": "..."}
  {"type": "sub", "i": N, "start": S, "end": E, "text": "..."}
  {"type": "done", "segments": N, "srt_path": "..."}
  {"type": "error", "msg": "..."}

Args:  <media> <model> <language> <task> [mirror_file] [srt_path]
The <model> arg is ignored (fixed parakeet-tdt-0.6b-v2). English-only:
translate or non-"en" language → actionable error, callers fall back.
The SRT file is written ONLY when [srt_path] is given — the plugin's caller
(aisubs_whisper.py) owns SRT output, so the runner never creates side-effect
files next to the media (realtime-OSD mode, read-only media dirs).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from typing import TYPE_CHECKING

from core.srt import write_srt

if TYPE_CHECKING:
    import numpy as np

MODEL_NAME = "parakeet-tdt-0.6b-v2"
MODEL_DIR = os.path.expanduser(
    "~/.local/share/sherpa-onnx/models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
)


def emit(data: dict):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def decode_to_wav16k(media_path: str) -> str:
    """Decode arbitrary media to a 16 kHz mono PCM wav via ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found — required by the Parakeet backend")
    fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="parakeet_")
    os.close(fd)
    proc = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", media_path,
         "-ac", "1", "-ar", "16000", "-f", "wav", tmp],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise RuntimeError(f"ffmpeg decode failed: {(proc.stderr or '').strip()[:300]}")
    return tmp


def load_float32_16k(wav_path: str) -> "np.ndarray":
    """Read a 16 kHz mono wav into float32 samples in [-1, 1].

    numpy is imported lazily so the module stays importable in dev venvs
    that only install pytest (tests cover the pure logic, not the runtime).
    """
    import numpy as np

    with wave.open(wav_path, "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1, "expected 16k mono"
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def tokens_to_words(tokens, times) -> list:
    """Merge sherpa-onnx BPE tokens into words with (text, start, end)."""
    words = []
    cur, cur_start, last_t = "", 0.0, 0.0
    for tok, t in zip(tokens, times):
        if not cur:
            cur, cur_start = tok.strip(), t
        elif tok.startswith(" "):
            words.append((cur.strip(), cur_start, last_t))
            cur, cur_start = tok.strip(), t
        else:
            cur += tok
        last_t = max(last_t, t)
    if cur.strip():
        words.append((cur.strip(), cur_start, last_t))
    return words


def words_to_segments(words) -> list:
    """Group words into subtitle cues (sentence punctuation / length caps)."""
    segments, seg = [], []

    def flush():
        if not seg:
            return
        text = " ".join(w[0] for w in seg).strip()
        if text:
            segments.append({"start": seg[0][1], "end": seg[-1][2], "text": text})
        seg.clear()

    for w in words:
        seg.append(w)
        span = w[2] - seg[0][1]
        if w[0][-1:] in ".!?" or len(seg) >= 12 or span > 9.0:
            flush()
    flush()
    return segments


SAMPLE_RATE = 16000
# 20 min — the 0.6B TDT model is designed for up to 24-min single-pass
# segments; long media is decoded in chunks instead of one giant stream.
CHUNK_SECONDS = 20 * 60


def chunk_plan(n_samples: int, chunk_samples: int) -> list:
    """[(start, stop)] sample ranges covering n_samples in ≤chunk_samples pieces."""
    return [
        (start, min(start + chunk_samples, n_samples))
        for start in range(0, n_samples, chunk_samples)
    ]


def shift_words(words: list, dt: float) -> list:
    """Offset (text, start, end) words by dt seconds (chunk time alignment)."""
    return [(w[0], w[1] + dt, w[2] + dt) for w in words]


def main():
    if len(sys.argv) < 5:
        emit({"type": "error", "msg": "Usage: runner <media> <model> <lang> <task> [mirror] [srt]"})
        sys.exit(1)

    media_path = sys.argv[1]
    language = sys.argv[3] if sys.argv[3] != "auto" else None
    task = sys.argv[4]
    srt_requested = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6].strip() else None

    if task == "translate":
        emit({"type": "error", "msg": "Parakeet is English-only (no translation) — use WhisperX for translate."})
        sys.exit(1)
    if language and language.lower() != "en":
        emit({"type": "error", "msg": f"Parakeet supports English only (requested '{language}') — use WhisperX."})
        sys.exit(1)
    if not os.path.isfile(media_path):
        emit({"type": "error", "msg": f"File not found: {media_path}"})
        sys.exit(1)

    enc, dec, joi, tok = (
        os.path.join(MODEL_DIR, name)
        for name in ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")
    )
    if not all(os.path.isfile(p) for p in (enc, dec, joi, tok)):
        emit({"type": "error", "msg": "Parakeet model not installed — run ./install-parakeet-model.sh"})
        sys.exit(1)

    import sherpa_onnx  # noqa: E402 — import lazily; heavy package

    t0 = time.time()
    num_threads = min(8, os.cpu_count() or 2)
    emit({"type": "status", "msg": f"Parakeet: loading {MODEL_NAME} (CPU, int8, {num_threads} threads)..."})
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=enc, decoder=dec, joiner=joi, tokens=tok,
        num_threads=num_threads, provider="cpu",
        model_type="nemo_transducer", modeling_unit="cjkchar",
    )

    emit({"type": "status", "msg": f"Parakeet: decoding audio (+{time.time()-t0:.0f}s)"})
    wav_path = decode_to_wav16k(media_path)
    samples = load_float32_16k(wav_path)
    os.unlink(wav_path)

    # Long media: decode in ≤20-min chunks (the 0.6B TDT model is designed
    # for up to 24-min single-pass segments) instead of one giant stream.
    ranges = chunk_plan(len(samples), CHUNK_SECONDS * SAMPLE_RATE)
    words = []
    n_chunks = len(ranges)
    for ci, (start, stop) in enumerate(ranges, 1):
        if n_chunks > 1:
            emit({"type": "status", "msg": f"Parakeet: decoding chunk {ci}/{n_chunks} (+{time.time()-t0:.0f}s)"})
        stream = rec.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples[start:stop])
        rec.decode_stream(stream)
        result = stream.result
        tokens = result.tokens or []
        times = result.timestamps or []
        if tokens:
            words.extend(shift_words(tokens_to_words(tokens, times), start / SAMPLE_RATE))

    if not words:
        emit({"type": "status", "msg": "No speech detected."})
        emit({"type": "done", "segments": 0, "srt_path": None})
        return

    segments = words_to_segments(words)

    # Drop known hallucination segments (research §2.2) before emitting.
    from core.blocklist import filter_segments
    segments = filter_segments(segments)

    # Emit each segment for the caller (status / OSD progress).
    for i, seg in enumerate(segments, 1):
        emit({
            "type": "sub", "i": i,
            "start": round(seg["start"], 3), "end": round(seg["end"], 3),
            "text": seg["text"],
        })

    # Write SRT — only when the caller explicitly requested a path (the
    # plugin caller owns SRT output; no <media>.srt side effects). Empty
    # output → write_srt returns None (no 0-byte SRTs).
    try:
        srt_path = write_srt(segments, media_path, srt_requested)
    except OSError as exc:
        emit({"type": "error", "msg": f"Could not write SRT: {exc}"})
        sys.exit(1)

    emit({"type": "done", "segments": len(segments), "srt_path": srt_path})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        emit({"type": "error", "msg": f"{exc}\n{traceback.format_exc()}"})
        sys.exit(1)