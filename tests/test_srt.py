"""Unit tests for core/srt.py — timestamp formatting + SRT file writing."""

import pytest

from core.srt import format_timestamp, segments_to_srt, write_srt


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (-1.0, "00:00:00,000"),              # clamped to 0
        (0.0, "00:00:00,000"),
        (1.9999, "00:00:02,000"),            # rounds to nearest ms
        (60.0, "00:01:00,000"),
        (3599.999, "00:59:59,999"),          # float-drift safe (was ,998)
        (3600.0, "01:00:00,000"),
        (3661.789, "01:01:01,789"),          # rollover h/m/s
        (86399.001, "23:59:59,001"),
        (90123.456, "25:02:03,456"),         # beyond 24h (allowed in SRT)
    ],
)
def test_format_timestamp(seconds: float, expected: str):
    assert format_timestamp(seconds) == expected


def test_segments_to_srt_blocks_and_numbering():
    srt = segments_to_srt(
        [
            {"start": 0.0, "end": 2.5, "text": "hello"},
            {"start": 2.5, "end": 5.0, "text": "world"},
        ]
    )
    lines = srt.splitlines()
    assert lines[0] == "1"
    assert lines[1] == "00:00:00,000 --> 00:00:02,500"
    assert lines[2] == "hello"
    assert lines[3] == ""
    assert lines[4] == "2"
    assert lines[5] == "00:00:02,500 --> 00:00:05,000"
    assert lines[6] == "world"
    # SRT files conventionally end with a newline
    assert srt.endswith("\n")


def test_write_srt_explicit_path(tmp_path):
    out = tmp_path / "subs" / "out.srt"
    written = write_srt(
        [{"start": 1.0, "end": 2.0, "text": "hi"}],
        media_path="/unused/movie.mp4",
        srt_path=str(out),
    )
    assert written == str(out)  # used the explicit path (parent dir created)
    assert out.read_text(encoding="utf-8").startswith("1\n00:00:01,000 --> 00:00:02,000\nhi\n")


def test_write_srt_derived_path(tmp_path):
    media = tmp_path / "movie.mkv"
    written = write_srt([{"start": 0.0, "end": 1.0, "text": "t"}], str(media))
    assert written == str(tmp_path / "movie.srt")
    assert (tmp_path / "movie.srt").exists()


def test_write_srt_keeps_unicode(tmp_path):
    out = tmp_path / "uni.srt"
    write_srt([{"start": 0.0, "end": 1.0, "text": "こんにちは — héllo"}], "m.mp4", str(out))
    assert "こんにちは — héllo" in out.read_text(encoding="utf-8")