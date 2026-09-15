"""Unit tests for core/blocklist.py — the hallucination phrase filter."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "core.blocklist", Path(__file__).resolve().parent.parent / "core" / "blocklist.py"
)
bl = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bl)


def test_is_blocklisted():
    assert bl.is_blocklisted("Subtitles by the Amara.org community")
    assert bl.is_blocklisted("[Music Playing]")
    assert bl.is_blocklisted("  ♪ ♪ ♪  ")
    assert bl.is_blocklisted("this video is sponsored by")


def test_not_blocklisted_real_dialogue():
    assert not bl.is_blocklisted("Thank you for watching this film with us.")
    assert not bl.is_blocklisted("You")
    assert not bl.is_blocklisted("Music was playing in the background.")
    assert not bl.is_blocklisted("Hello everyone, it's raining in the city.")


def test_blocklist_env_disable(monkeypatch):
    monkeypatch.setenv("VSCL_AISUBS_BLOCKLIST", "0")
    assert not bl.is_blocklisted("subtitles by the amara.org community")
    monkeypatch.delenv("VSCL_AISUBS_BLOCKLIST")
    assert bl.is_blocklisted("subtitles by the amara.org community")


def test_filter_segments():
    segs = [
        {"start": 0.0, "end": 1.0, "text": "Normal dialogue here."},
        {"start": 1.0, "end": 2.0, "text": "[Music playing]"},
        {"start": 2.0, "end": 3.0, "text": "subtitles by the amara.org community"},
    ]
    out = bl.filter_segments(segs)
    assert len(out) == 1
    assert out[0]["text"] == "Normal dialogue here."
