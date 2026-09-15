"""Unit tests for core/emitter.py — JSONL stdout + mirror-file contract."""

import json

from core.emitter import Emitter


def test_emit_writes_jsonl_to_stdout(capsys):
    e = Emitter()
    e.emit({"type": "status", "msg": "hi"})
    e.close()
    out = capsys.readouterr().out
    assert json.loads(out) == {"type": "status", "msg": "hi"}


def test_mirror_file_matches_stdout(tmp_path, capsys, monkeypatch):
    mirror = tmp_path / "aisubs_mirror.jsonl"
    e = Emitter(str(mirror))
    e.emit({"type": "sub", "i": 1, "start": 0.5, "end": 1.5, "text": "язык"})
    e.emit({"type": "done", "segments": 1, "srt_path": "/tmp/x.srt"})
    e.close()

    # stdout
    stdout_lines = capsys.readouterr().out.strip().splitlines()
    assert len(stdout_lines) == 2
    assert json.loads(stdout_lines[1])["type"] == "done"

    # mirror
    mirror_lines = mirror.read_text(encoding="utf-8").strip().splitlines()
    assert len(mirror_lines) == 2
    assert json.loads(mirror_lines[0])["text"] == "язык"
    assert json.loads(mirror_lines[1])["type"] == "done"


def test_unicode_not_escaped(tmp_path):
    mirror = tmp_path / "uni.jsonl"
    e = Emitter(str(mirror))
    e.emit({"type": "status", "msg": "日本語"})
    e.close()
    raw = mirror.read_text(encoding="utf-8")
    assert "日本語" in raw  # ensure_ascii=False
    assert "\\u" not in raw


def test_unwritable_mirror_is_silently_ignored(capsys):
    e = Emitter("/nonexistent-dir-xyz/mirror.jsonl")  # open fails -> no mirror
    e.emit({"type": "status", "msg": "ok"})
    e.close()
    assert json.loads(capsys.readouterr().out)["msg"] == "ok"