"""CLI contract tests — error semantics of aisubs_whisper.py.

Real transcription is out of scope for unit tests (needs WhisperX + model
download). These cover argument parsing, missing-file errors, JSONL error
emission, and exit codes.
"""

import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(REPO, "aisubs_whisper.py")
PY = sys.executable  # this test runs under the project venv


def run_cli(args, timeout=60):
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": ""}
    return subprocess.run(
        [PY, CLI, *args],
        capture_output=True, text=True, timeout=timeout, env=env,
    )


def test_too_few_args_exits_1():
    proc = run_cli(["only-one-arg"])
    assert proc.returncode == 1
    assert "Usage" in (proc.stderr or "")


def test_missing_file_emits_error_on_stdout():
    proc = run_cli(["/nonexistent/movie.mp4", "tiny", "en", "transcribe"])
    assert proc.returncode == 1
    line = json.loads(proc.stdout.strip().splitlines()[-1])
    assert line["type"] == "error"
    assert "File not found" in line["msg"]


def test_missing_file_writes_error_to_mirror(tmp_path):
    mirror = tmp_path / "mirror.jsonl"
    proc = run_cli(
        ["/nonexistent/movie.mp4", "tiny", "en", "transcribe", str(mirror)]
    )
    assert proc.returncode == 1
    lines = mirror.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[-1])["type"] == "error"


def test_backend_failure_emits_json_error_instead_of_traceback(monkeypatch, capsys):
    """If resolve_backend() raises, the CLI must turn it into a JSONL error
    line with exit code 1 — never a raw Python traceback on stdout."""
    import aisubs_whisper

    def boom():
        raise RuntimeError(
            "WhisperX is not available. Install it with:\n  uv venv --python 3.12 ..."
        )

    monkeypatch.setattr(aisubs_whisper, "resolve_backend", boom)
    media = os.path.abspath(__file__)  # a file that exists
    monkeypatch.setattr(
        sys, "argv", ["aisubs_whisper.py", media, "tiny", "en", "transcribe"]
    )
    with pytest.raises(SystemExit) as exc:
        aisubs_whisper.main()
    assert exc.value.code == 1

    out = capsys.readouterr().out
    last = json.loads(out.strip().splitlines()[-1])
    assert last["type"] == "error"
    assert "WhisperX is not available" in last["msg"]
    assert "Traceback" not in out


class _FakeBackend:
    def __init__(self, segments):
        self._segments = segments

    def name(self):
        return "fake"

    def transcribe(self, media_path, model_name, language, task):
        yield from self._segments


def test_srt_write_failure_falls_back_to_temp(monkeypatch, capsys, tmp_path):
    """Media dir read-only: first SRT write fails → temp fallback + status
    warning + done with the fallback path (exit 0, never an abort)."""
    import aisubs_whisper

    monkeypatch.setattr(
        aisubs_whisper, "resolve_backend",
        lambda: _FakeBackend([{"start": 0.0, "end": 1.0, "text": "Hi"}]),
    )
    media = tmp_path / "ro.mp4"
    media.write_bytes(b"junk")

    calls = {"n": 0}

    def flaky_write(segments, media_path, srt_requested):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("Read-only file system")
        with open(srt_requested, "w", encoding="utf-8") as f:
            f.write("ok\n")
        return srt_requested

    monkeypatch.setattr(aisubs_whisper, "write_srt", flaky_write)
    monkeypatch.setattr(
        sys, "argv", ["aisubs_whisper.py", str(media), "tiny", "en", "transcribe"]
    )
    aisubs_whisper.main()  # no SystemExit → exit 0

    lines = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines()]
    last = lines[-1]
    assert last["type"] == "done"
    assert last["segments"] == 1
    assert last["srt_path"] and last["srt_path"] != str(media) + ".srt"
    assert os.path.isfile(last["srt_path"])
    assert any(l["type"] == "status" and "wrote" in l["msg"] for l in lines)
    os.remove(last["srt_path"])


def test_srt_write_failure_both_paths_errors(monkeypatch, capsys, tmp_path):
    """Media dir and temp dir both unwritable → clean JSONL error, exit 1."""
    import aisubs_whisper

    monkeypatch.setattr(
        aisubs_whisper, "resolve_backend",
        lambda: _FakeBackend([{"start": 0.0, "end": 1.0, "text": "Hi"}]),
    )
    media = tmp_path / "ro.mp4"
    media.write_bytes(b"junk")

    def always_fail(segments, media_path, srt_requested):
        raise OSError("Read-only file system")

    monkeypatch.setattr(aisubs_whisper, "write_srt", always_fail)
    monkeypatch.setattr(
        sys, "argv", ["aisubs_whisper.py", str(media), "tiny", "en", "transcribe"]
    )
    with pytest.raises(SystemExit) as exc:
        aisubs_whisper.main()
    assert exc.value.code == 1

    lines = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines()]
    assert lines[-1]["type"] == "error"
    assert "Could not write SRT" in lines[-1]["msg"]