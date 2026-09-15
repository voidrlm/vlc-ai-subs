"""Unit tests for the VRAM-aware "Recommended" model picker.

Boundary cases are asserted exactly — these tests caught a real bug: with a
GPU present but < 2 GB VRAM the picker used to fall through to the RAM path
and could recommend `medium` for a card that can only run `base`.

2026-08: ≥4GB VRAM now recommends large-v3-turbo (809M — near-large accuracy,
~4x faster, ~1.5-1.8GB int8), which fits this machine's GTX 1650.
"""

import pytest

import aisubs_whisper


@pytest.mark.parametrize(
    ("vram_mb", "ram_gb", "expected"),
    [
        # GPU path (CTranslate2 / int8_float16 ≈ 2x GGML footprint)
        (8192, 0, "large"),
        (8000, 0, "large"),
        (4096, 0, "large-v3-turbo"),   # GTX 1650 — this box
        (4000, 0, "large-v3-turbo"),
        (3999, 0, "small"),            # just under the turbo tier
        (2049, 0, "small"),
        (2000, 0, "small"),
        (1999, 0, "base"),             # just under the small tier
        (1024, 0, "base"),             # small GPU must NOT borrow the RAM path
        (4096, 16, "large-v3-turbo"),  # GPU present -> RAM is ignored
        # CPU path — no usable GPU (vram == 0), sized by system RAM
        (0, 16, "medium"),
        (0, 8, "medium"),
        (0, 4, "small"),
        (0, 1, "base"),
    ],
)
def test_recommend_model(monkeypatch, vram_mb: int, ram_gb: int, expected: str):
    monkeypatch.setattr(aisubs_whisper, "_detect_vram_mb", lambda: vram_mb)
    monkeypatch.setattr(aisubs_whisper, "_detect_ram_gb", lambda: ram_gb)
    assert aisubs_whisper._recommend_model() == expected


def test_recommend_is_backend_independent(monkeypatch):
    """The backend_name arg is vestigial — sizing is engine-independent
    (Parakeet ignores the model anyway; the picker is shared)."""
    monkeypatch.setattr(aisubs_whisper, "_detect_vram_mb", lambda: 4096)
    monkeypatch.setattr(aisubs_whisper, "_detect_ram_gb", lambda: 16)
    assert aisubs_whisper._recommend_model("whisperx") == "large-v3-turbo"
    assert aisubs_whisper._recommend_model("parakeet") == "large-v3-turbo"