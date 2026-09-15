"""Unit tests for nllb_translate.py (imported standalone — no heavy deps).

The heavy imports (ctranslate2, transformers) only happen inside
NllbTranslator.__init__, so the pure logic is testable in the dev venv.
"""

import importlib.util
from pathlib import Path

_RUNNER = Path(__file__).resolve().parent.parent / "nllb_translate.py"
_spec = importlib.util.spec_from_file_location("nllb_translate", _RUNNER)
nllb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nllb)


def test_flores_code_common_languages():
    assert nllb.flores_code("en") == "eng_Latn"
    assert nllb.flores_code("fr") == "fra_Latn"
    assert nllb.flores_code("zh") == "zho_Hans"
    assert nllb.flores_code("ja") == "jpn_Jpan"
    assert nllb.flores_code("ru") == "rus_Cyrl"
    assert nllb.flores_code("hi") == "hin_Deva"
    assert nllb.flores_code("ar") == "arb_Arab"


def test_flores_code_unmapped_and_case():
    assert nllb.flores_code("haw") is None  # Hawaiian not in NLLB-200
    assert nllb.flores_code("br") is None
    assert nllb.flores_code(None) is None
    assert nllb.flores_code("FR") == "fra_Latn"  # case-insensitive
    assert nllb.flores_code(" en ") == "eng_Latn"


def test_should_cascade():
    assert nllb.should_cascade("translate", "1") is True
    assert nllb.should_cascade("translate", None) is True
    assert nllb.should_cascade("translate", "0") is False
    assert nllb.should_cascade("translate", "false") is False
    assert nllb.should_cascade("transcribe", "1") is False
    assert nllb.should_cascade("transcribe", "0") is False


def test_try_load_translator_missing_dir_returns_none():
    assert nllb.try_load_translator("/nonexistent/nllb-model") is None
    assert nllb.try_load_translator(None) is None


def test_m2m_lang_code():
    assert nllb.lang_code("fr", "m2m100") == "fr"
    assert nllb.lang_code("en", "m2m100") == "en"
    assert nllb.lang_code("jw", "m2m100") == "jv"    # whisper → ISO correction
    assert nllb.lang_code("FR", "m2m100") == "fr"    # case-insensitive
    assert nllb.lang_code("yue", "m2m100") is None   # Cantonese not in M2M-100
    assert nllb.lang_code("haw", "m2m100") is None   # Hawaiian not in M2M-100
    assert nllb.lang_code(None, "m2m100") is None


def test_lang_code_family_routing():
    assert nllb.lang_code("fr", "nllb") == "fra_Latn"
    assert nllb.lang_code("fr", "m2m100") == "fr"
    assert nllb.lang_code("zh", "nllb") == "zho_Hans"
    assert nllb.lang_code("zh", "m2m100") == "zh"
    assert nllb.lang_code("haw", "nllb") is None
    assert nllb.lang_code("haw", "m2m100") is None


def test_try_load_translator_missing_dir_both_families():
    assert nllb.try_load_translator("/nonexistent/x", family="nllb") is None
    assert nllb.try_load_translator("/nonexistent/x", family="m2m100") is None
    assert nllb.try_load_translator("/nonexistent/x", family="bogus") is None  # → nllb path


class _FakeTranslator:
    def __init__(self, fail_on=None):
        self._fail = fail_on

    def translate(self, text, src_lang):
        if self._fail and self._fail in text:
            raise RuntimeError("boom")
        return "[TR] " + text


def test_translate_segments_preserves_timestamps():
    segs = [
        {"start": 0.4, "end": 3.52, "text": "Bonjour tout le monde"},
        {"start": 3.68, "end": 4.64, "text": "Au revoir"},
    ]
    out = nllb.translate_segments(segs, "fra_Latn", _FakeTranslator())
    assert [s["start"] for s in out] == [0.4, 3.68]
    assert [s["end"] for s in out] == [3.52, 4.64]
    assert out[0]["text"] == "[TR] Bonjour tout le monde"
    assert out[1]["text"] == "[TR] Au revoir"


def test_translate_segments_keeps_source_on_failure():
    segs = [
        {"start": 0.0, "end": 1.0, "text": "Bad text"},
        {"start": 1.0, "end": 2.0, "text": "ok"},
    ]
    out = nllb.translate_segments(segs, "fra_Latn", _FakeTranslator(fail_on="Bad"))
    assert out[0]["text"] == "Bad text"  # failed segment keeps source text
    assert out[0]["start"] == 0.0        # timestamps untouched
    assert out[1]["text"] == "[TR] ok"   # the run continues


def test_translate_segments_skips_blank():
    segs = [
        {"start": 0.0, "end": 1.0, "text": "  "},
        {"start": 1.0, "end": 2.0, "text": "Hi"},
    ]
    out = nllb.translate_segments(segs, "fra_Latn", _FakeTranslator())
    assert out[0]["text"] == ""
    assert out[1]["text"] == "[TR] Hi"


def test_translation_viable():
    assert nllb.translation_viable(["a", "b"], ["x", "y"]) is True   # full success
    assert nllb.translation_viable(["a", "b"], ["x", ""]) is True    # partial OK
    assert nllb.translation_viable(["a", "b"], ["", ""]) is False    # total failure
    assert nllb.translation_viable(["a", "b"], ["a", "b"]) is False  # all raised → unchanged
    assert nllb.translation_viable([], []) is True                   # empty transcript
    assert nllb.translation_viable(["", ""], ["", ""]) is True       # nothing to do


class _FakeBatchedTranslator:
    """Mimics NllbTranslator.translate_batch (the real one is lazy-loaded)."""

    def __init__(self, fail_batch=False, fail_on=None):
        self._fail_batch = fail_batch
        self._fail_on = fail_on

    def translate_batch(self, texts, src_lang):
        if self._fail_batch:
            raise RuntimeError("batch boom")
        out = []
        for t in texts:
            if self._fail_on and self._fail_on in t:
                raise RuntimeError("boom")
            out.append("[TR] " + t)
        return out

    def translate(self, text, src_lang):
        if self._fail_on and self._fail_on in text:
            raise RuntimeError("boom")
        return "[TR] " + text


def test_translate_segments_batches():
    segs = [
        {"start": 0.4, "end": 3.52, "text": "Bonjour"},
        {"start": 3.68, "end": 4.64, "text": "Au revoir"},
        {"start": 4.96, "end": 7.04, "text": "Merci"},
    ]
    out = nllb.translate_segments(segs, "fra_Latn", _FakeBatchedTranslator())
    assert [s["text"] for s in out] == ["[TR] Bonjour", "[TR] Au revoir", "[TR] Merci"]
    assert [s["start"] for s in out] == [0.4, 3.68, 4.96]  # timestamps preserved


def test_translate_segments_batch_failure_falls_back_per_segment():
    segs = [
        {"start": 0.0, "end": 1.0, "text": "Good text"},
        {"start": 1.0, "end": 2.0, "text": "Bad text"},
        {"start": 2.0, "end": 3.0, "text": "Fine"},
    ]
    t = _FakeBatchedTranslator(fail_batch=True, fail_on="Bad")
    out = nllb.translate_segments(segs, "fra_Latn", t)
    # batch raised → per-segment retry; "Bad text" still fails → source kept
    assert out[0]["text"] == "[TR] Good text"
    assert out[1]["text"] == "Bad text"
    assert out[2]["text"] == "[TR] Fine"


def test_translate_segments_multiple_batches_preserve_order():
    """> BATCH_SIZE segments → multiple translate_batch calls, order preserved."""
    n = nllb.BATCH_SIZE * 2 + 3
    segs = [{"start": float(i), "end": float(i) + 1.0, "text": f"Phrase {i}"} for i in range(n)]
    out = nllb.translate_segments(segs, "fra_Latn", _FakeBatchedTranslator())
    assert [s["text"] for s in out] == [f"[TR] Phrase {i}" for i in range(n)]
    assert [s["start"] for s in out] == [float(i) for i in range(n)]
