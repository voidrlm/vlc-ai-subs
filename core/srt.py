"""
Core SRT module — timestamp formatting and file writing.

Produced SRT files follow the standard SubRip spec with millisecond-precision
timestamps and blank-line separators.
"""

import os
from typing import Iterable


def format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp (HH:MM:SS,mmm).

    Rounds to the nearest millisecond from total-ms math — robust against
    float representation drift (e.g. 3599.999 stored as 3598.99899...).
    """
    total_ms = max(0, round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: Iterable[dict]) -> str:
    """Build a complete SRT file body from {start, end, text} segments."""
    blocks = []
    for i, seg in enumerate(segments, 1):
        blocks.append(
            f"{i}\n"
            f"{format_timestamp(seg['start'])} --> {format_timestamp(seg['end'])}\n"
            f"{seg['text']}\n"
        )
    return "\n".join(blocks)


def write_srt(
    segments: list[dict],
    media_path: str,
    srt_path: str | None = None,
) -> str | None:
    """Write SRT to disk and return the path used, or None if nothing written.

    If *srt_path* is given it is used exactly; otherwise it is derived from
    the media filename (``<media>.srt``). Parent directories are created as
    needed when an explicit path is provided.

    Empty output is skipped (no 0-byte SRTs). An explicit path that is a
    symlink is never written through (temp-name swap attack) — a fresh
    unique path is used instead; regular files still overwrite.
    """
    if not segments:
        return None
    actual = srt_path or (os.path.splitext(media_path)[0] + ".srt")
    if srt_path and os.path.islink(srt_path):
        import tempfile
        fd, actual = tempfile.mkstemp(prefix="aisubs_", suffix=".srt")
        os.close(fd)
    os.makedirs(os.path.dirname(actual) or ".", exist_ok=True)
    with open(actual, "w", encoding="utf-8") as f:
        f.write(segments_to_srt(segments))
    return actual
