"""Tests for backend resolution.

- WhisperX is the DEFAULT engine (VSCL_AISUBS_BACKEND unset or legacy).
- `VSCL_AISUBS_BACKEND=parakeet` opts into the Parakeet backend (English).
- Any other value is ignored → WhisperX.
"""

import pytest

from backends import resolve_backend


def _fake_whisperx_backend(monkeypatch, tmp_path):
    """Point the whisperx backend at fake-but-existing files so the resolution
    tests are hermetic (they must pass on a fresh machine with no runtime dir,
    e.g. CI)."""
    import backends.whisperx_backend as wx

    runner = tmp_path / "whisperx_runner.py"
    runner.write_text("")
    venv = tmp_path / "venv-whisperx"
    (venv / "bin").mkdir(parents=True)
    py = venv / "bin" / "python3"
    py.write_text("")
    monkeypatch.setattr(wx, "_RUNNER", str(runner))
    monkeypatch.setattr(wx, "_VENV", str(venv))
    monkeypatch.setattr(wx, "_PYTHON", str(py))
    return wx


def test_resolve_returns_whisperx_by_default(monkeypatch, tmp_path):
    _fake_whisperx_backend(monkeypatch, tmp_path)
    be = resolve_backend()
    assert be is not None
    assert "whisperx" in be.name().lower()


def test_legacy_env_values_are_ignored(monkeypatch, tmp_path):
    """whisper_cpp/moonshine/... must fall through to WhisperX."""
    _fake_whisperx_backend(monkeypatch, tmp_path)
    monkeypatch.setenv("VSCL_AISUBS_BACKEND", "whisper_cpp")
    be = resolve_backend()
    assert "whisperx" in be.name().lower()


def test_parakeet_env_returns_parakeet_backend(monkeypatch):
    """The opt-in path; if sherpa-onnx is installed it resolves to Parakeet."""
    monkeypatch.setenv("VSCL_AISUBS_BACKEND", "parakeet")
    be = None
    try:
        be = resolve_backend()
    except RuntimeError:
        pytest.skip("Parakeet backend not installed on this machine")
    assert be is not None
    assert "parakeet" in be.name().lower()


def test_parakeet_missing_raises_helpful_error(monkeypatch):
    """VSCL_AISUBS_BACKEND=parakeet without the backend → actionable error."""
    import backends.parakeet as pk

    monkeypatch.setenv("VSCL_AISUBS_BACKEND", "parakeet")
    monkeypatch.setattr(pk.ParakeetBackend, "detect", classmethod(lambda cls: None))
    with pytest.raises(RuntimeError) as exc:
        resolve_backend()
    msg = str(exc.value)
    assert "Parakeet backend is not available" in msg
    assert "install-parakeet-model.sh" in msg  # points at the fix


def test_missing_whisperx_raises_helpful_error(monkeypatch):
    import backends.whisperx_backend as wx

    monkeypatch.setattr(wx.WhisperXBackend, "detect", classmethod(lambda cls: None))
    with pytest.raises(RuntimeError) as exc:
        resolve_backend()
    msg = str(exc.value)
    assert "WhisperX is not available" in msg
    assert "venv-whisperx" in msg  # points at the fix


def test_detect_false_when_venv_missing(monkeypatch, tmp_path):
    """detect() returns None when the 3.12 venv/runner are not installed."""
    import backends.whisperx_backend as wx

    monkeypatch.setattr(wx, "_RUNNER", str(tmp_path / "nope" / "whisperx_runner.py"))
    monkeypatch.setattr(wx, "_VENV", str(tmp_path / "nope" / "venv-whisperx"))
    monkeypatch.setattr(wx, "_PYTHON", None)
    assert wx.WhisperXBackend.detect() is None


def test_runner_and_venv_required_for_detect(monkeypatch, tmp_path):
    """detect() must require BOTH the runner script and the venv python."""
    import backends.whisperx_backend as wx

    venv = tmp_path / "venv-whisperx"
    (venv / "bin").mkdir(parents=True)
    py = venv / "bin" / "python3"
    py.write_text("#!/bin/sh\necho fake\n")  # any file is enough for isfile()

    monkeypatch.setattr(wx, "_VENV", str(venv))
    monkeypatch.setattr(wx, "_RUNNER", str(tmp_path / "missing" / "runner.py"))
    monkeypatch.setattr(wx, "_PYTHON", str(py))

    assert wx.WhisperXBackend.detect() is None