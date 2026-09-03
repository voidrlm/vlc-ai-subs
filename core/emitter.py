"""
Core emitter — writes JSON lines to stdout and optionally mirrors to a file.

The VLC Lua extension polls the mirror file once a second; stdout carries
the definitive stream. This module keeps zero global state.
"""

import json
from typing import Optional, TextIO


class Emitter:
    """Line-buffered JSONL emitter with optional file mirror."""

    def __init__(self, mirror_path: Optional[str] = None):
        self._mirror: Optional[TextIO] = None
        if mirror_path:
            try:
                self._mirror = open(mirror_path, "w", encoding="utf-8", buffering=1)
            except OSError:
                pass

    def emit(self, data: dict) -> None:
        """Write one JSON object to stdout and the mirror (if set)."""
        line = json.dumps(data, ensure_ascii=False)
        print(line, flush=True)
        if self._mirror:
            try:
                self._mirror.write(line + "\n")
                self._mirror.flush()
            except (OSError, ValueError):
                pass

    def close(self) -> None:
        if self._mirror:
            try:
                self._mirror.close()
            except OSError:
                pass
