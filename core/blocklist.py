"""Whisper hallucination blocklist — research-backed post-filter.

Reference: .research/final_report.md §2.2 — 40.3% of non-speech audio files
hallucinate (9.1% loop), and 67% of hallucinations come from ~1,270 recurring
phrases; a known-phrase blocklist "is cheap and strips most music/silence
garbage". This is a deliberately small, high-precision set — only distinctive
recurring phrases, never short generic ones that occur in real dialogue
("thank you", "you", …). Disable with VSCL_AISUBS_BLOCKLIST=0.
"""

import os
import re

# Lowercase, whitespace-normalized distinctive hallucination phrases.
HALLUCINATION_PHRASES = frozenset({
    "subtitles by the amara.org community",
    "subtitles by the amara.org community - youtube",
    "subtitles by the amara.org community and",
    "this video is sponsored by",
    "if you enjoyed this video, please subscribe",
    "please subscribe to my channel and like this video",
    "like, share and subscribe to my channel",
    "thank you for watching, please subscribe",
    "thanks for watching, please subscribe",
    "[music playing]",
    "[applause]",
    "[laughing]",
    "[background music]",
    "[no music]",
    "foreign music",
    "music playing",
    "♪ ♪ ♪",
    "♪♪♪",
})

_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub(" ", text or "").strip().lower()


def is_blocklisted(text: str) -> bool:
    """True when the segment is a known hallucination (high-precision set)."""
    if os.environ.get("VSCL_AISUBS_BLOCKLIST", "1").strip().lower() in ("0", "false", "off"):
        return False
    return _normalize(text) in HALLUCINATION_PHRASES


def filter_segments(segments: list) -> list:
    """Drop segments whose whole text is a known hallucination phrase."""
    return [seg for seg in segments if not is_blocklisted(seg.get("text") or "")]
