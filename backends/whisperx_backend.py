"""
WhisperX backend — word-level alignment via separate Python 3.12 venv.

WhisperX requires Python <3.14, so it runs in its own venv (created by
`uv venv --python 3.12 venv-whisperx && uv pip install whisperx`).
The plugin calls `whisperx_runner.py` as a subprocess — same contract
as the main JSONL interface.
"""

import os
import subprocess
from typing import Iterable

from .base import TranscriptionBackend

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root or install dir
_RUNNER = os.path.join(_BASE, "whisperx_runner.py")
_VENV = os.path.join(_BASE, "venv-whisperx")

# Fallback to the standard install location (~/.local/share/vlc-ai-subs)
# when running from a clone without a local venv-whisperx.
if not (os.path.isfile(_RUNNER) and os.path.isdir(_VENV)):
    _SHARE = os.path.expanduser("~/.local/share/vlc-ai-subs")
    _RUNNER = os.path.join(_SHARE, "whisperx_runner.py")
    _VENV = os.path.join(_SHARE, "venv-whisperx")

_PYTHON = None
for _cand in (
    os.path.join(_VENV, "bin", "python3"),
    os.path.join(_VENV, "bin", "python"),
    os.path.join(_VENV, "Scripts", "python.exe"),  # Windows
):
    if os.path.isfile(_cand):
        _PYTHON = _cand
        break


class WhisperXBackend(TranscriptionBackend):
    """Transcribe with WhisperX — word-aligned segments, optional speakers."""

    def __init__(self, align: bool = True):
        self._align = align

    @classmethod
    def detect(cls) -> "WhisperXBackend | None":
        """Return instance if the Python 3.12 venv + runner script exist."""
        if _PYTHON and os.path.isfile(_PYTHON) and os.path.isfile(_RUNNER):
            return cls(align=True)
        return None

    def transcribe(
        self, media_path: str, model_name: str, language: str | None, task: str
    ) -> Iterable[dict]:
        cmd = [
            _PYTHON, "-u", _RUNNER,
            media_path, model_name, language or "auto", task,
        ]
        # Run with clean PYTHONPATH — a stray local module (or a foreign
        # PYTHONPATH export in the user's shell) must never shadow the
        # pip-installed packages inside venv-whisperx.
        env = {**os.environ, "PYTHONPATH": ""}
        debug = env.get("VSCL_AISUBS_DEBUG") == "1"
        # translate runs the NLLB cascade after transcribing — give it room.
        timeout = 2400 if task == "translate" else 1200
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env,
        )
        if debug:
            # Full dump for forensics — survives the subprocess either way.
            import sys as _sys
            try:
                with open("/tmp/aisubs_whisperx.log", "a", encoding="utf-8") as f:
                    f.write(f"--- run: {media_path} {model_name} ---\n")
                    f.write("STDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr + "\n")
            except OSError:
                pass
            for _l in (proc.stdout + proc.stderr).splitlines():
                _sys.stderr.write(f"[whisperx] {_l}\n")

        if proc.returncode != 0:
            tail = (
                "stdout: " + proc.stdout.strip().splitlines()[-1][:300]
                if proc.stdout.strip() else ""
            )
            raise RuntimeError(
                "WhisperX failed (rc={}): {}{}{}".format(
                    proc.returncode,
                    (proc.stderr or "").strip()[-500:],
                    "\n" + tail if tail else "",
                    "\nFull output: /tmp/aisubs_whisperx.log (run with VSCL_AISUBS_DEBUG=1)"
                    if not debug else "",
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
                raise RuntimeError(obj.get("msg", "WhisperX error"))
            elif obj.get("type") == "status" and debug:
                import sys as _sys
                _sys.stderr.write(f"[whisperx] {obj.get('msg', '')}\n")

    @staticmethod
    def name() -> str:
        return "whisperx (aligned)"
