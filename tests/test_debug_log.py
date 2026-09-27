"""Unit tests for core/debug_log.py — private-dir logging, symlink refusal."""

import os

from core.debug_log import append_debug_log, debug_log_path


def test_debug_log_path_uses_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("VSCL_AISUBS_LOG_DIR", str(tmp_path / "logs"))
    path = debug_log_path("x.log")
    assert path == str(tmp_path / "logs" / "x.log")
    assert os.path.isdir(tmp_path / "logs")


def test_append_debug_log_writes_and_appends(tmp_path, monkeypatch):
    monkeypatch.setenv("VSCL_AISUBS_LOG_DIR", str(tmp_path))
    append_debug_log("a.log", "first\n")
    append_debug_log("a.log", "second\n")
    assert (tmp_path / "a.log").read_text() == "first\nsecond\n"


def test_append_debug_log_refuses_symlink(tmp_path, monkeypatch):
    """A pre-planted symlink at the log path must not be followed — the
    append is silently dropped rather than writing into the symlink target."""
    monkeypatch.setenv("VSCL_AISUBS_LOG_DIR", str(tmp_path))
    victim = tmp_path.parent / "victim.txt"
    victim.write_text("untouched")
    link = tmp_path / "a.log"
    link.symlink_to(victim)
    append_debug_log("a.log", "attacker-controlled line\n")
    assert victim.read_text() == "untouched"
