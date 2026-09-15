"""Unit tests for whisperx_runner.py (loaded as a standalone module).

The runner lives outside a package, so tests import it by path via
importlib.util — mirroring how the backend spawns it as a subprocess.
"""

import importlib.util
import os
import sys

import pytest

_RUNNER = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "whisperx_runner.py")


@pytest.fixture(scope="module")
def runner():
    spec = importlib.util.spec_from_file_location("whisperx_runner_test", _RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_usage_error_emits_error_jsonl(runner, capsys, monkeypatch):
    # Deterministic argv — the test must not depend on how pytest was invoked
    # (pytest's own argv can be ≥5 entries, which would skip the usage branch).
    monkeypatch.setattr(sys, "argv", ["runner"])
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert '"type": "error"' in out
    assert '"msg": "Usage: runner' in out


def test_missing_media_emits_error_jsonl(runner, capsys, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["runner", "/nonexistent/file.mp4", "tiny", "en", "transcribe"]
    )
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert '"type": "error"' in out
    assert "File not found" in out


# ── SRT writing via shared core.srt.write_srt (was runner.write_srt_if_requested) ──
# write_srt_if_requested lived in both runners and duplicated core/srt.py; it was
# removed in favor of core.srt.write_srt, which keeps the same explicit-path /
# empty-drop / symlink-refusal semantics. These tests pin that shared behavior.

def test_write_srt_writes_when_requested(tmp_path):
    from core.srt import write_srt
    srt = tmp_path / "out.srt"
    segs = [{"start": 0.0, "end": 1.0, "text": "Hi"}]
    assert write_srt(segs, "/unused/movie.mp4", str(srt)) == str(srt)
    assert "Hi" in srt.read_text()


def test_write_srt_skips_when_not_requested(tmp_path):
    from core.srt import write_srt
    media = tmp_path / "m.mp4"
    media.write_bytes(b"x")
    # No explicit path + no segments would derive <media>.srt; with no
    # segments nothing is written (no 0-byte SRTs next to media).
    assert write_srt([], str(media)) is None
    assert not (tmp_path / "m.srt").exists()


def test_write_srt_refuses_symlink(tmp_path):
    from core.srt import write_srt
    target = tmp_path / "victim.txt"
    target.write_text("do not clobber")
    link = tmp_path / "out.srt"
    link.symlink_to(target)
    path = write_srt([{"start": 0.0, "end": 1.0, "text": "line"}], "m.mp4", str(link))
    assert path is not None and path != str(link)
    assert target.read_text() == "do not clobber"  # symlink target untouched
    assert os.path.isfile(path)


# ── device / compute resolution (VSCL_AISUBS_DEVICE / VSCL_AISUBS_COMPUTE) ──

def test_resolve_device_defaults(runner, monkeypatch):
    monkeypatch.delenv("VSCL_AISUBS_DEVICE", raising=False)
    assert runner.resolve_device(True) == "cuda"
    assert runner.resolve_device(False) == "cpu"


def test_resolve_device_env_override(runner, monkeypatch):
    monkeypatch.setenv("VSCL_AISUBS_DEVICE", "cpu")
    assert runner.resolve_device(True) == "cpu"
    monkeypatch.setenv("VSCL_AISUBS_DEVICE", "cuda")
    assert runner.resolve_device(False) == "cuda"


def test_resolve_device_invalid_falls_back(runner, monkeypatch):
    monkeypatch.setenv("VSCL_AISUBS_DEVICE", "bogus")
    assert runner.resolve_device(False) == "cpu"


def test_resolve_compute_defaults_and_override(runner, monkeypatch):
    monkeypatch.delenv("VSCL_AISUBS_COMPUTE", raising=False)
    assert runner.resolve_compute("cuda") == "int8_float16"
    assert runner.resolve_compute("cpu") == "float32"
    monkeypatch.setenv("VSCL_AISUBS_COMPUTE", "int8")
    assert runner.resolve_compute("cuda") == "int8"
    assert runner.resolve_compute("cpu") == "int8"
    # CUDA-only compute types must be rejected on CPU (they crash faster-whisper)
    monkeypatch.setenv("VSCL_AISUBS_COMPUTE", "int8_float16")
    assert runner.resolve_compute("cpu") == "float32"
    assert runner.resolve_compute("cuda") == "int8_float16"
    monkeypatch.setenv("VSCL_AISUBS_COMPUTE", "bogus")
    assert runner.resolve_compute("cuda") == "int8_float16"


def test_hardened_asr_options(runner):
    """Research-backed decode hardening (§2.2) must stay in force."""
    opts = runner.hardened_asr_options()
    assert opts["beam_size"] == 1
    assert opts["condition_on_previous_text"] is False
    assert opts["temperatures"] == [0.0]
    assert opts["hallucination_silence_threshold"] == 2.0
    assert opts["no_speech_threshold"] >= 0.6