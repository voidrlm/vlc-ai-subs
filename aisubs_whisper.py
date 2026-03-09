#!/usr/bin/env python3
"""
vlc-ai-subs — Whisper transcription backend.

Transcribes audio from a media file using faster-whisper (or openai-whisper
as fallback) and streams results as JSON lines to stdout. Also writes a
standard SRT subtitle file next to the source media.

Usage:
    python3 aisubs_whisper.py <media_path> <model> <language> <task>

Arguments:
    media_path  Path to the video/audio file
    model       Whisper model size: tiny, base, small, medium, large
    language    Language code (e.g. en, es, hi) or "auto" for detection
    task        "transcribe" or "translate" (translate outputs English)

Output (stdout):
    One JSON object per line:
      {"type": "status", "msg": "..."}           — progress updates
      {"type": "sub", "i": N, "start": S, "end": E, "text": "..."}  — subtitle
      {"type": "done", "segments": N, "srt_path": "..."}            — finished
      {"type": "error", "msg": "..."}            — fatal error
"""

import sys
import os
import json


def format_srt_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp (HH:MM:SS,mmm)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def emit(data: dict) -> None:
    """Write a JSON line to stdout and flush immediately."""
    print(json.dumps(data, ensure_ascii=False), flush=True)


def transcribe_faster_whisper(media_path, model_name, lang, task):
    """Transcribe using faster-whisper (CTranslate2 backend)."""
    from faster_whisper import WhisperModel

    emit({"type": "status", "msg": f"Loading {model_name} model..."})
    model = WhisperModel(model_name, compute_type="int8")

    emit({"type": "status", "msg": "Transcribing..."})
    segments_gen, _info = model.transcribe(
        media_path,
        language=lang,
        task=task,
        beam_size=1,
        vad_filter=True,
        vad_parameters={
            "threshold": 0.05,
            "min_silence_duration_ms": 200,
            "speech_pad_ms": 600,
            "min_speech_duration_ms": 50,
        },
    )

    for seg in segments_gen:
        text = seg.text.strip()
        if text:
            yield {"start": seg.start, "end": seg.end, "text": text}


def transcribe_openai_whisper(media_path, model_name, lang, task):
    """Transcribe using openai-whisper (fallback)."""
    import whisper

    emit({"type": "status", "msg": f"Loading {model_name} model..."})
    model = whisper.load_model(model_name)

    emit({"type": "status", "msg": "Transcribing (batch mode)..."})
    options = {"task": task}
    if lang:
        options["language"] = lang
    result = model.transcribe(media_path, **options)

    for seg in result["segments"]:
        text = seg["text"].strip()
        if text:
            yield {"start": seg["start"], "end": seg["end"], "text": text}


def main():
    if len(sys.argv) < 5:
        emit({"type": "error", "msg": "Usage: aisubs_whisper.py <media> <model> <lang> <task>"})
        sys.exit(1)

    media_path = sys.argv[1]
    model_name = sys.argv[2]
    language = sys.argv[3] if sys.argv[3] != "auto" else None
    task = sys.argv[4]

    if not os.path.isfile(media_path):
        emit({"type": "error", "msg": f"File not found: {media_path}"})
        sys.exit(1)

    # Detect backend
    backend = None
    try:
        import faster_whisper  # noqa: F401
        backend = "faster-whisper"
    except ImportError:
        pass

    if not backend:
        try:
            import whisper  # noqa: F401
            backend = "openai-whisper"
        except ImportError:
            emit({"type": "error", "msg": "No Whisper backend found. Run: pip install faster-whisper"})
            sys.exit(1)

    # Choose transcription function
    if backend == "faster-whisper":
        segments_iter = transcribe_faster_whisper(media_path, model_name, language, task)
    else:
        segments_iter = transcribe_openai_whisper(media_path, model_name, language, task)

    # Stream segments and build SRT
    srt_lines = []
    count = 0

    for seg in segments_iter:
        count += 1
        emit({
            "type": "sub",
            "i": count,
            "start": round(seg["start"], 3),
            "end": round(seg["end"], 3),
            "text": seg["text"],
        })
        srt_lines.append(
            f"{count}\n"
            f"{format_srt_timestamp(seg['start'])} --> {format_srt_timestamp(seg['end'])}\n"
            f"{seg['text']}\n"
        )

    # Write SRT file next to the media
    base, _ = os.path.splitext(media_path)
    srt_path = base + ".srt"
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))

    emit({"type": "done", "segments": count, "srt_path": srt_path})


if __name__ == "__main__":
    main()
