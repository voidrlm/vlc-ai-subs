"""
Backend registry — WhisperX is the default engine.

WhisperX (https://github.com/m-bain/whisperX) provides word-level aligned
timestamps (ideal for movie subtitles) in its own Python 3.12 venv
(whisperX requires <3.14); see whisperx_backend.py.

Optional engine — `VSCL_AISUBS_BACKEND=parakeet`: NVIDIA Parakeet-TDT-0.6B-v2
via sherpa-onnx (English-only, native word timestamps, ~10x faster, CC-BY-4.0).
WhisperX remains the fallback for non-English/translate.
"""

import logging
import os

logger = logging.getLogger(__name__)

_ENGINES = {
    "parakeet": ("backends.parakeet", "ParakeetBackend", "Parakeet"),
}


from backends.base import TranscriptionBackend


def resolve_backend() -> TranscriptionBackend:
    """Return the WhisperX backend (default), or the parakeet opt-in."""
    forced = os.environ.get("VSCL_AISUBS_BACKEND", "").strip().lower()

    if forced in _ENGINES:
        mod_name, cls_name, label = _ENGINES[forced]
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            be = getattr(mod, cls_name).detect()
            if be:
                return be
        except Exception as exc:
            logger.debug("%s: %s", label, exc)
        raise RuntimeError(
            f"{label} backend is not available. Install it with: "
            f"./install-parakeet-model.sh "
            f"&& uv pip install --python ~/.local/share/vlc-ai-subs/venv-whisperx/bin/python sherpa-onnx"
        )

    # Default + any legacy/unknown env value → WhisperX
    from backends.whisperx_backend import WhisperXBackend

    try:
        be = WhisperXBackend.detect()
    except Exception as exc:
        logger.debug("whisperx: %s", exc)
        be = None
    if be:
        return be

    raise RuntimeError(
        "WhisperX is not available. Install it with:\n"
        "  uv venv --python 3.12 ~/.local/share/vlc-ai-subs/venv-whisperx\n"
        "  uv pip install --python ~/.local/share/vlc-ai-subs/venv-whisperx/bin/python whisperx\n"
        "or re-run ./install.sh"
    )
