"""Parakeet backend — NVIDIA Parakeet-TDT-0.6B-v2 (English) via sherpa-onnx.

Runs inside the shared Python 3.12 venv (`venv-whisperx`), same subprocess
+ JSONL pattern as whisperx_backend. Selected explicitly via
VSCL_AISUBS_BACKEND=parakeet — WhisperX remains the default engine.

2026-08 research: WER 6.05 (beats Whisper large-v3 7.44), native word-level
timestamps, ~0.7GB int8, CC-BY-4.0, transducer = no hallucination loops.
"""

import os
import subprocess
from typing import Iterable

from .base import TranscriptionBackend

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUNNER = os.path.join(_BASE, "parakeet_runner.py")
_VENV = os.path.join(_BASE, "venv-whisperx")

if not (os.path.isfile(_RUNNER) and os.path.isdir(_VENV)):
    _SHARE = os.path.expanduser("~/.local/share/vlc-ai-subs")
    _RUNNER = os.path.join(_SHARE, "parakeet_runner.py")
    _VENV = os.path.join(_SHARE, "venv-whisperx")

_PYTHON = None
for _cand in (
    os.path.join(_VENV, "bin", "python3"),
    os.path.join(_VENV, "bin", "python"),
    os.path.join(_VENV, "Scripts", "python.exe"),
):
    if os.path.isfile(_cand):
        _PYTHON = _cand
        break


class ParakeetBackend(TranscriptionBackend):
    """Transcribe with Parakeet-TDT-0.6B-v2 — English, CPU, word timestamps."""

    def __init__(self) -> None:
        pass

    @classmethod
    def detect(cls) -> "ParakeetBackend | None":
        """Instance exists if runner + 3.12 venv are installed."""
        if _PYTHON and os.path.isfile(_PYTHON) and os.path.isfile(_RUNNER):
            return cls()
        return None

    def transcribe(
        self, media_path: str, model_name: str, language: str | None, task: str
    ) -> Iterable[dict]:
        cmd = [
            _PYTHON, "-u", _RUNNER,
            media_path, model_name, language or "auto", task,
        ]
        env = {**os.environ, "PYTHONPATH": ""}
        debug = env.get("VSCL_AISUBS_DEBUG") == "1"
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=3600, env=env,
        )
        if debug:
            import sys as _sys
            try:
                with open("/tmp/aisubs_parakeet.log", "a", encoding="utf-8") as f:
                    f.write(f"--- run: {media_path} {model_name} ---\n")
                    f.write("STDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr + "\n")
            except OSError:
                pass
            for _l in (proc.stdout + proc.stderr).splitlines():
                _sys.stderr.write(f"[parakeet] {_l}\n")

        if proc.returncode != 0:
            tail = (
                "stdout: " + proc.stdout.strip().splitlines()[-1][:300]
                if proc.stdout.strip() else ""
            )
            raise RuntimeError(
                "Parakeet failed (rc={}): {}{}".format(
                    proc.returncode, (proc.stderr or "").strip()[-500:],
                    "\n" + tail if tail else "",
                )
            )

        import json
        for line in proc.stdout.strip().splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("type") == "sub":
                yield {"start": obj["start"], "end": obj["end"], "text": obj["text"]}
            elif obj.get("type") == "error":
                raise RuntimeError(obj.get("msg", "Parakeet error"))
            elif obj.get("type") == "status" and debug:
                import sys as _sys
                _sys.stderr.write(f"[parakeet] {obj.get('msg', '')}\n")

    @staticmethod
    def name() -> str:
        return "parakeet (en, fast)"