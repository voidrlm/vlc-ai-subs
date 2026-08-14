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


_out_file = None  # optional output file set in main()

def emit(data: dict) -> None:
    """Write a JSON line to stdout and to the output file if set."""
    line = json.dumps(data, ensure_ascii=False)
    try:
        print(line, flush=True)
    except Exception:
        # Launched hidden from VLC there may be no usable stdout, and a legacy
        # console codepage cannot encode non-ASCII text. Never let that kill
        # the run: the output file below is what the extension actually reads.
        pass
    if _out_file:
        try:
            _out_file.write(line + "\n")
            _out_file.flush()
        except Exception:
            pass


def transcribe_faster_whisper(media_path, model_name, lang, task):
    """Transcribe using faster-whisper (CTranslate2 backend)."""
    from faster_whisper import WhisperModel

    emit({"type": "status", "msg": f"Loading {model_name} model..."})
    model = WhisperModel(model_name, device="cpu", compute_type="float32")

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


def read_job_file(path):
    """Read arguments from a UTF-8 job file, one value per line.

    The Windows launcher cannot pass non-ASCII paths on the command line: the
    .vbs helper it writes is read back by wscript in the ANSI codepage, which
    corrupts UTF-8 bytes. Routing arguments through this file keeps them intact.
    """
    with open(path, "r", encoding="utf-8") as f:
        values = [line.rstrip("\r\n") for line in f]
    while len(values) < 5:
        values.append("")
    return values[:5]


def main():
    global _out_file

    if len(sys.argv) >= 3 and sys.argv[1] == "--job":
        try:
            media_path, model_name, language, task, out_path = read_job_file(sys.argv[2])
        except Exception as e:
            emit({"type": "error", "msg": f"Cannot read job file {sys.argv[2]}: {e}"})
            sys.exit(1)
    elif len(sys.argv) >= 5:
        media_path = sys.argv[1]
        model_name = sys.argv[2]
        language = sys.argv[3]
        task = sys.argv[4]
        # Optional output file — passed so output is captured without redirection
        out_path = sys.argv[5] if len(sys.argv) > 5 else None
    else:
        emit({"type": "error", "msg": "Usage: aisubs_whisper.py <media> <model> <lang> <task> [out_file]  |  --job <file>"})
        sys.exit(1)

    if language == "auto":
        language = None

    if out_path:
        # The Windows launcher starts this process hidden and without a console,
        # so the inherited stdout/stderr are dead handles: the first print() or
        # traceback would raise OSError and kill the run silently, leaving an
        # empty output file behind. Point both streams at a log file up front so
        # nothing can write into the void - and so crashes stay diagnosable.
        try:
            log = open(out_path + ".log", "w", encoding="utf-8", buffering=1)
            sys.stdout = log
            sys.stderr = log
        except Exception:
            pass

        try:
            _out_file = open(out_path, "w", encoding="utf-8", buffering=1)
        except Exception:
            pass  # if we can't open it, stdout-only mode

    # Written before any heavy import so a crash while loading the backend can
    # be told apart from the process never starting at all.
    emit({"type": "status", "msg": "Starting..."})

    if not os.path.isfile(media_path):
        emit({"type": "error", "msg": f"File not found: {media_path}"})
        sys.exit(1)

    # Detect backend. Catch Exception rather than ImportError: a broken native
    # dependency (ctranslate2 / onnxruntime DLLs) can surface as OSError, and
    # swallowing that would report a misleading "no backend found" instead.
    emit({"type": "status", "msg": "Loading backend..."})
    backend = None
    first_error = None
    try:
        import faster_whisper  # noqa: F401
        backend = "faster-whisper"
    except Exception as e:
        first_error = f"{type(e).__name__}: {e}"

    if not backend:
        try:
            import whisper  # noqa: F401
            backend = "openai-whisper"
        except Exception as e:
            emit({"type": "error", "msg":
                  f"No Whisper backend available.\nfaster-whisper: {first_error}\nopenai-whisper: {type(e).__name__}: {e}"})
            sys.exit(1)

    # Choose transcription function
    if backend == "faster-whisper":
        segments_iter = transcribe_faster_whisper(media_path, model_name, language, task)
    else:
        segments_iter = transcribe_openai_whisper(media_path, model_name, language, task)

    # Stream segments and build SRT
    srt_lines = []
    count = 0

    try:
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
    except Exception as e:
        import traceback
        emit({"type": "error", "msg": f"Transcription failed: {e}\n{traceback.format_exc()}"})
        sys.exit(1)

    # Write SRT file next to the media
    base, _ = os.path.splitext(media_path)
    srt_path = base + ".srt"
    try:
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_lines))
    except Exception as e:
        emit({"type": "error", "msg": f"Could not write SRT: {e}"})
        sys.exit(1)

    emit({"type": "done", "segments": count, "srt_path": srt_path})

    if _out_file:
        _out_file.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        emit({"type": "error", "msg": str(e) + "\n" + traceback.format_exc()})
        if _out_file:
            _out_file.close()
        sys.exit(1)
