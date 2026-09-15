"""
Abstract backend interface.

Every backend yields a sequence of ``{start: float, end: float, text: str}``
dictionaries. The caller handles SRT writing and JSONL emission.
"""

import abc
from typing import Iterable


class TranscriptionBackend(abc.ABC):
    """Transcribe a media file and yield timestamped text segments."""

    @abc.abstractmethod
    def transcribe(
        self,
        media_path: str,
        model_name: str,
        language: str | None,
        task: str,
    ) -> Iterable[dict]:
        """Yield ``{start, end, text}`` dicts.  Can be a generator."""
        ...
