#!/usr/bin/env python3
"""
WhisperX runner — invoked by the plugin as a subprocess when the main venv
is Python ≥3.14 (whisperX requires <3.14).  This runs inside its own
Python 3.12 venv.

Contract (stdout, JSONL):
  {"type": "status", "msg": "..."}
  {"type": "sub", "i": N, "start": S, "end": E, "text": "..."}
  {"type": "done", "segments": N, "srt_path": "..."}
  {"type": "error", "msg": "..."}

Args:  <media> <model> <language> <task> [mirror_file] [srt_path]
The SRT file is written ONLY when [srt_path] is given — the plugin's caller
(aisubs_whisper.py) owns SRT output, so the runner never creates side-effect
files next to the media (realtime-OSD mode, read-only media dirs).
Env:  VSCL_AISUBS_DEVICE=cpu|cuda forces the device; VSCL_AISUBS_COMPUTE
overrides the compute type; VSCL_AISUBS_MODEL_CACHE sets the HF cache dir.
Translate task: NLLB-200 cascade by default (VSCL_AISUBS_NLLB=0 reverts to
Whisper's built-in translate; VSCL_AISUBS_NLLB_MODEL overrides the model dir;
VSCL_AISUBS_NLLB_FAMILY=nllb|m2m100 picks the cascade family — m2m100 is the
MIT-licensed commercial-use alternative).
"""
import json
import os
import sys

from core.srt import write_srt


_CUDA_COMPUTE = ("int8", "int8_float16", "int8_float32", "float16", "float32")
_CPU_COMPUTE = ("int8", "int8_float32", "float32")


def resolve_device(cuda_available: bool) -> str:
    """Device selection: VSCL_AISUBS_DEVICE=cpu|cuda forces it; else auto."""
    env_device = os.environ.get("VSCL_AISUBS_DEVICE", "").strip().lower()
    if env_device == "cpu":
        return "cpu"
    if env_device == "cuda":
        return "cuda"
    return "cuda" if cuda_available else "cpu"


def resolve_compute(device: str) -> str:
    """Compute type: VSCL_AISUBS_COMPUTE overrides; sensible default per device.

    Validated per device — int8_float16/float16 are CUDA-only and would
    crash inside faster-whisper on CPU.
    """
    env_ct = os.environ.get("VSCL_AISUBS_COMPUTE", "").strip().lower()
    allowed = _CUDA_COMPUTE if device == "cuda" else _CPU_COMPUTE
    if env_ct in allowed:
        return env_ct
    return "int8_float16" if device == "cuda" else "float32"


def model_cache_dir() -> str | None:
    """VSCL_AISUBS_MODEL_CACHE → HF download_root (None = default cache)."""
    cache = os.environ.get("VSCL_AISUBS_MODEL_CACHE", "").strip()
    return cache or None


def hardened_asr_options() -> dict:
    """Research-backed decode options (see .research/final_report.md §2.2).

    WhisperX's defaults are beam_size=5 with temperature fallback ladder and
    no hallucination gate — fine for clean audio, but movie soundtracks get
    silence/music hallucinations. BoH mitigation: beam 1, fixed low
    temperature, no cross-window conditioning, explicit silence thresholds.
    """
    return {
        "beam_size": 1,
        "condition_on_previous_text": False,
        "temperatures": [0.0],
        "hallucination_silence_threshold": 2.0,
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.6,
    }


def emit(data: dict):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def main():
    if len(sys.argv) < 5:
        emit({"type": "error", "msg": "Usage: runner <media> <model> <lang> <task> [mirror] [srt]"})
        sys.exit(1)

    import time
    _t0 = time.time()

    media_path = sys.argv[1]
    model_name = sys.argv[2]
    language = sys.argv[3] if sys.argv[3] != "auto" else None
    task = sys.argv[4]
    srt_requested = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6].strip() else None

    if not os.path.isfile(media_path):
        emit({"type": "error", "msg": f"File not found: {media_path}"})
        sys.exit(1)

    import whisperx
    try:
        import nllb_translate
        nllb_ok = True
    except ImportError:
        nllb_ok = False

    # NLLB cascade for translate: transcribe in the source language, then
    # NLLB-200 translates segments to English (research: ~44.7 BLEU CA→EN vs
    # Whisper's built-in translate). VSCL_AISUBS_NLLB=0 reverts to Whisper.
    # Falls back to Whisper translate — never silently source-language output.
    use_nllb = nllb_ok and nllb_translate.should_cascade(
        task, os.environ.get("VSCL_AISUBS_NLLB")
    )

    # Resolve device: VSCL_AISUBS_DEVICE=cpu|cuda forces it; else auto-detect.
    try:
        import torch
        cuda_available = torch.cuda.is_available()
    except Exception:
        cuda_available = False
    device = resolve_device(cuda_available)
    compute = resolve_compute(device)

    # Load the NLLB/M2M translator up front so a missing/broken model switches
    # to Whisper translate before any audio is transcribed. Family: nllb
    # (CC-BY-NC-4.0, default) or m2m100 (MIT, commercial-use alternative).
    family = os.environ.get("VSCL_AISUBS_NLLB_FAMILY", "nllb").strip().lower()
    if family not in ("nllb", "m2m100"):
        emit({"type": "status", "msg": f"Unknown VSCL_AISUBS_NLLB_FAMILY '{family}' — using nllb (CC-BY-NC-4.0)"})
        family = "nllb"
    translator = None
    if use_nllb:
        translator = nllb_translate.try_load_translator(
            os.environ.get("VSCL_AISUBS_NLLB_MODEL") or nllb_translate.MODEL_DIR_DEFAULT,
            device="cuda" if device == "cuda" else "cpu",
            compute_type="int8_float16" if device == "cuda" else "int8",
            family=family,
        )
        if translator:
            emit({"type": "status", "msg": f"Translate: {family} cascade (transcribe → {family} → English)"})
        else:
            emit({"type": "status", "msg": "NLLB/M2M model not installed — using Whisper translate. Run ./install-nllb-model.sh (or install-m2m-model.sh)"})

    emit({"type": "status", "msg": f"WhisperX: loading {model_name} on {device} ({compute})..."})

    # 1. Transcribe — VAD-first (whisperx default gate) + hardened decode.
    model = whisperx.load_model(
        model_name, device, compute_type=compute,
        asr_options=hardened_asr_options(),
        vad_options={"vad_onset": 0.500, "vad_offset": 0.363},
        download_root=model_cache_dir(),
    )
    emit({"type": "status", "msg": "Transcribing..."})
    result = model.transcribe(
        media_path,
        language=language,
        task="transcribe" if translator else task,
    )
    emit({
        "type": "status",
        "msg": f"WhisperX: transcription done (+{time.time() - _t0:.0f}s)",
    })

    # 2. Hallucination blocklist (research §2.2) — before the cascade and
    # alignment so garbage segments aren't translated or GPU-aligned.
    from core.blocklist import filter_segments
    result["segments"] = filter_segments(result.get("segments", []))

    # 2b. Cascade translation (translate task only, translator loaded)
    if translator and task == "translate":
        tgt_lang = nllb_translate.TARGET_M2M if family == "m2m100" else nllb_translate.TARGET
        src_code = (result.get("language") or language or "en").lower()
        src_flores = nllb_translate.lang_code(src_code, family)
        if not src_flores:
            # Unmapped language — re-transcribe with Whisper's translate so
            # output stays English (never silently source-language).
            emit({"type": "status", "msg": f"{family}: no mapping for '{src_code}' — re-running with Whisper translate"})
            result = model.transcribe(media_path, language=language, task="translate")
        elif src_flores != tgt_lang:
            emit({"type": "status", "msg": f"{family}: translating {src_flores} → {tgt_lang} (+{time.time() - _t0:.0f}s)"})
            before = [(s.get("text") or "").strip() for s in result.get("segments", [])]
            result["segments"] = nllb_translate.translate_segments(
                result.get("segments", []), src_flores, translator
            )
            after = [(s.get("text") or "").strip() for s in result["segments"]]
            if not nllb_translate.translation_viable(before, after):
                # Nothing came back translatable — fall back to Whisper.
                emit({"type": "status", "msg": f"{family} translation failed — re-running with Whisper translate"})
                result = model.transcribe(media_path, language=language, task="translate")
        # src == tgt: source is already English — pass through

    # Re-apply the blocklist: the fallback branches produced fresh unfiltered
    # segments, and NLLB-translated output may itself match an English phrase.
    result["segments"] = filter_segments(result.get("segments", []))

    # 3. Align (word-level timestamps)
    if device == "cuda" and result.get("segments"):
        try:
            # After any translate path the transcript is English — the align
            # model must match the transcript, not the source language.
            align_lang = "en" if task == "translate" else (result.get("language") or language or "en")
            align_model, metadata = whisperx.load_align_model(
                language_code=align_lang, device=device,
            )
            result = whisperx.align(
                result["segments"], align_model, metadata,
                media_path, device, return_char_alignments=False,
            )
            emit({
                "type": "status",
                "msg": f"WhisperX: word alignment done (+{time.time() - _t0:.1f}s)",
            })
        except Exception:
            emit({"type": "status", "msg": "Alignment skipped (may need different language model)"})

    # 4. Yield segments; collect dicts for the SRT writer (shared core.srt)
    segments = result.get("segments", [])
    out_segments = []
    count = 0

    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        count += 1
        item = {
            "start": round(seg.get("start", 0), 3),
            "end": round(seg.get("end", 0), 3),
            "text": text,
        }
        out_segments.append(item)
        emit({"type": "sub", "i": count, **item})

    # 5. Write SRT — only when the caller explicitly requested a path (the
    # plugin caller owns SRT output; no <media>.srt side effects). Empty
    # output → write_srt returns None (no 0-byte SRTs).
    try:
        srt_path = write_srt(out_segments, media_path, srt_requested)
    except OSError as exc:
        emit({"type": "error", "msg": f"Could not write SRT: {exc}"})
        sys.exit(1)

    emit({"type": "done", "segments": count, "srt_path": srt_path})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        emit({"type": "error", "msg": f"{exc}\n{traceback.format_exc()}"})
        sys.exit(1)