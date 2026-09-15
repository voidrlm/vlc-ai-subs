"""NLLB-200 cascade translator — upgrades the WhisperX `translate` task.

Pipeline: WhisperX transcribes in the source language (task="transcribe"),
then each segment's text is translated to English with NLLB-200 via
ctranslate2 (int8). Timestamps are untouched; only `text` changes.

Model: michaelfeil/ct2fast-nllb-200-distilled-1.3B (ctranslate2 int8, 200
languages), installed by install-nllb-model.sh.

LICENSE NOTE: NLLB-200 is CC-BY-NC-4.0 (research / non-commercial). The model
is a separate runtime download — the plugin code stays MIT. `VSCL_AISUBS_NLLB=0`
switches the translate task back to Whisper's built-in translation.

Heavy imports (ctranslate2, transformers) are deferred to NllbTranslator so
this module stays importable in dev venvs without them (unit-testable).
"""

import logging
import os

logger = logging.getLogger(__name__)

# Default install location (matches install-nllb-model.sh).
MODEL_DIR_DEFAULT = os.path.expanduser(
    "~/.local/share/vlc-ai-subs/nllb-200-distilled-1.3B-int8"
)

# Target language for the cascade: English.
TARGET = "eng_Latn"
# M2M-100 (MIT) family uses ISO-639-1 codes instead of FLORES-200.
TARGET_M2M = "en"

# M2M-100 supported languages (ISO 639-1, from the model card). Whisper codes
# absent here are unmapped → fall back to Whisper translate.
M2M_LANGS = frozenset({
    "af", "am", "ar", "ast", "az", "ba", "be", "bg", "bn", "br", "bs", "ca",
    "ceb", "cs", "cy", "da", "de", "el", "en", "es", "et", "fa", "ff", "fi",
    "fr", "fy", "ga", "gd", "gl", "gu", "ha", "he", "hi", "hr", "ht", "hu",
    "hy", "id", "ig", "ilo", "is", "it", "ja", "jv", "ka", "kk", "km", "kn",
    "ko", "lb", "lg", "ln", "lo", "lt", "lv", "mg", "mk", "ml", "mn", "mr",
    "ms", "my", "ne", "nl", "no", "ns", "oc", "or", "pa", "pl", "ps", "pt",
    "ro", "ru", "sd", "si", "sk", "sl", "so", "sq", "sr", "ss", "su", "sv",
    "sw", "ta", "th", "tl", "tn", "tr", "uk", "ur", "uz", "vi", "wo", "xh",
    "yi", "yo", "zh", "zu",
})

# Whisper → M2M code corrections (whisper uses different codes for some langs).
WHISPER_TO_M2M = {"jw": "jv"}

# Whisper language code → NLLB FLORES-200 code. Covers the languages whisper
# users realistically translate; unmapped codes fall back to Whisper translate.
WHISPER_TO_FLORES = {
    "af": "afr_Latn", "am": "amh_Ethi", "ar": "arb_Arab", "as": "asm_Beng",
    "az": "azj_Latn", "ba": "bak_Cyrl", "be": "bel_Cyrl", "bg": "bul_Cyrl",
    "bn": "ben_Beng", "bo": "bod_Tibt", "bs": "bos_Latn", "ca": "cat_Latn",
    "cs": "ces_Latn", "cy": "cym_Latn", "da": "dan_Latn", "de": "deu_Latn",
    "el": "ell_Grek", "en": "eng_Latn", "es": "spa_Latn", "et": "est_Latn",
    "eu": "eus_Latn", "fa": "pes_Arab", "fi": "fin_Latn", "fo": "fao_Latn",
    "fr": "fra_Latn", "gl": "glg_Latn", "gu": "guj_Gujr", "ha": "hau_Latn",
    "he": "heb_Hebr", "hi": "hin_Deva", "hr": "hrv_Latn", "ht": "hat_Latn",
    "hu": "hun_Latn", "hy": "hye_Armn", "id": "ind_Latn", "is": "isl_Latn",
    "it": "ita_Latn", "ja": "jpn_Jpan", "jw": "jav_Latn", "ka": "kat_Geor",
    "kk": "kaz_Cyrl", "km": "khm_Khmr", "kn": "kan_Knda", "ko": "kor_Hang",
    "lb": "ltz_Latn", "ln": "lin_Latn", "lo": "lao_Laoo", "lt": "lit_Latn",
    "lv": "lvs_Latn", "mg": "plt_Latn", "mi": "mri_Latn", "mk": "mkd_Cyrl",
    "ml": "mal_Mlym", "mn": "khk_Cyrl", "mr": "mar_Deva", "ms": "zsm_Latn",
    "mt": "mlt_Latn", "my": "mya_Mymr", "ne": "npi_Deva", "nl": "nld_Latn",
    "nn": "nno_Latn", "no": "nob_Latn", "oc": "oci_Latn", "pa": "pan_Guru",
    "pl": "pol_Latn", "ps": "pbt_Arab", "pt": "por_Latn", "ro": "ron_Latn",
    "ru": "rus_Cyrl", "sa": "san_Deva", "sd": "snd_Arab", "si": "sin_Sinh",
    "sk": "slk_Latn", "sl": "slv_Latn", "sn": "sna_Latn", "so": "som_Latn",
    "sq": "als_Latn", "sr": "srp_Cyrl", "su": "sun_Latn", "sv": "swe_Latn",
    "sw": "swh_Latn", "ta": "tam_Taml", "te": "tel_Telu", "tg": "tgk_Cyrl",
    "th": "tha_Thai", "tk": "tuk_Latn", "tl": "tgl_Latn", "tr": "tur_Latn",
    "tt": "tat_Cyrl", "uk": "ukr_Cyrl", "ur": "urd_Arab", "uz": "uzn_Latn",
    "vi": "vie_Latn", "yi": "ydd_Hebr", "yo": "yor_Latn", "yue": "yue_Hant",
    "zh": "zho_Hans",
}


def flores_code(whisper_code: str | None) -> str | None:
    """Map a whisper language code to an NLLB FLORES-200 code, or None."""
    if not whisper_code:
        return None
    return WHISPER_TO_FLORES.get(whisper_code.strip().lower())


def lang_code(whisper_code: str | None, family: str) -> str | None:
    """Whisper code → the model family's source code, or None if unsupported.

    family="nllb" → FLORES-200 code (eng_Latn, fra_Latn, …);
    family="m2m100" → ISO-639-1 code (en, fr, …), with whisper corrections
    (e.g. whisper "jw" = Javanese → M2M "jv").
    """
    if not whisper_code:
        return None
    code = whisper_code.strip().lower()
    if family == "m2m100":
        code = WHISPER_TO_M2M.get(code, code)
        return code if code in M2M_LANGS else None
    return WHISPER_TO_FLORES.get(code)


def should_cascade(task: str, env_value: str | None) -> bool:
    """Cascade is on for translate unless VSCL_AISUBS_NLLB=0."""
    if task != "translate":
        return False
    return (env_value or "1").strip().lower() not in ("0", "false", "off")


class NllbTranslator:
    """Thin wrapper over ctranslate2's NLLB model + HF tokenizer."""

    def __init__(self, model_dir: str, device: str = "cpu", compute_type: str = "int8"):
        import ctranslate2  # lazy — heavy deps only when translating
        from transformers import AutoTokenizer

        self._ct = ctranslate2.Translator(model_dir, device=device, compute_type=compute_type)
        self._tok = AutoTokenizer.from_pretrained(model_dir, src_lang=TARGET)

    def translate_batch(self, texts: list, src_lang: str, tgt_lang: str = TARGET) -> list:
        """Translate several texts in one model call (much cheaper than N per-call).

        Follows the official ctranslate2 NLLB pattern (docs → Transformers →
        NLLB): tokenize WITH special tokens (the tokenizer adds the source-lang
        token and </s>; ctranslate2 does not add them itself), pass the
        target-lang code WITHOUT "__" delimiters as target_prefix, and strip
        the first output token of each hypothesis — it is the target-lang
        prefix. Raises on failure; callers apply per-segment tolerance.
        """
        self._tok.src_lang = src_lang
        sources = [
            self._tok.convert_ids_to_tokens(
                self._tok(text, add_special_tokens=True)["input_ids"]
            )
            for text in texts
        ]
        results = self._ct.translate_batch(
            sources,
            target_prefix=[[tgt_lang]] * len(sources),
            beam_size=1,
        )
        translated = []
        for r in results:
            out = r.hypotheses[0][1:]  # ctranslate2 ≥4: per-hypothesis list
            translated.append(self._tok.decode(self._tok.convert_tokens_to_ids(out)).strip())
        return translated

    def translate(self, text: str, src_lang: str, tgt_lang: str = TARGET) -> str:
        """Translate a single text (thin wrapper over translate_batch)."""
        return self.translate_batch([text], src_lang, tgt_lang)[0]


class M2M100Translator:
    """M2M-100 (MIT) cascade translator — same interface as NllbTranslator.

    Drop-in for the translate pipeline via try_load_translator(family="m2m100").
    Uses M2M100Tokenizer: source gets the __<src>__ lang token + </s>, and the
    target prefix is lang_code_to_token[tgt] = "__en__".
    """

    def __init__(self, model_dir: str, device: str = "cpu", compute_type: str = "int8"):
        import ctranslate2  # lazy — heavy deps only when translating
        from transformers import M2M100Tokenizer

        self._ct = ctranslate2.Translator(model_dir, device=device, compute_type=compute_type)
        self._tok = M2M100Tokenizer.from_pretrained(
            model_dir, src_lang=TARGET_M2M, tgt_lang=TARGET_M2M
        )

    def translate_batch(self, texts: list, src_lang: str, tgt_lang: str = TARGET_M2M) -> list:
        self._tok.src_lang = src_lang
        self._tok.tgt_lang = tgt_lang
        sources = [
            self._tok.convert_ids_to_tokens(
                self._tok(text, add_special_tokens=True)["input_ids"]
            )
            for text in texts
        ]
        prefix = [self._tok.lang_code_to_token[tgt_lang]]
        results = self._ct.translate_batch(
            sources, target_prefix=[prefix] * len(sources), beam_size=1,
        )
        translated = []
        for r in results:
            out = r.hypotheses[0][1:]  # strip the __<tgt>__ prefix token
            translated.append(self._tok.decode(self._tok.convert_tokens_to_ids(out)).strip())
        return translated

    def translate(self, text: str, src_lang: str, tgt_lang: str = TARGET_M2M) -> str:
        return self.translate_batch([text], src_lang, tgt_lang)[0]


def try_load_translator(
    model_dir: str | None,
    device: str = "cpu",
    compute_type: str = "int8",
    family: str = "nllb",
) -> NllbTranslator | M2M100Translator | None:
    """Load the translator, or None if the model is missing/broken.

    family="nllb" (default) → NLLB-200 (CC-BY-NC-4.0); family="m2m100" →
    M2M-100 (MIT). The caller treats None as 'fall back to Whisper translate'
    — the translate task must never hard-fail because a model is absent.
    """
    if not model_dir or not os.path.isdir(model_dir):
        return None
    try:
        if family == "m2m100":
            return M2M100Translator(model_dir, device=device, compute_type=compute_type)
        return NllbTranslator(model_dir, device=device, compute_type=compute_type)
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        logger.warning("NLLB/M2M model failed to load (%s) — using Whisper translate", exc)
        return None


def translation_viable(before_texts: list, after_texts: list) -> bool:
    """True when the cascade produced usable output.

    Falls back to Whisper translate when there WAS source text to translate
    but nothing came back non-empty (empty output) or nothing changed at all
    (every call raised — source text kept). Partial successes are kept
    (per-segment tolerance); an empty transcript is fine.
    """
    return (not any(before_texts)) or (any(after_texts) and after_texts != before_texts)


BATCH_SIZE = 16  # segment texts per ctranslate2 translate_batch call


def translate_segments(segments: list, src_flores: str, translator: NllbTranslator) -> list:
    """Translate each segment's text to English; timestamps preserved.

    Non-blank segments are translated in batches (one model call per batch —
    hundreds of segments on a movie would otherwise be hundreds of sequential
    calls). A batch that raises falls back to per-segment calls, and a segment
    that still fails keeps its original text (the run continues).
    """
    out = []
    pending_idx: list = []
    pending_text: list = []
    for i, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        if text:
            pending_idx.append(i)
            pending_text.append(text)

    translated: dict = {}
    for start in range(0, len(pending_text), BATCH_SIZE):
        chunk = pending_text[start:start + BATCH_SIZE]
        try:
            if hasattr(translator, "translate_batch"):
                res = translator.translate_batch(chunk, src_flores)
            else:
                res = [translator.translate(t, src_flores) for t in chunk]
        except Exception as exc:  # noqa: BLE001 — retry per segment, keep source
            logger.warning("NLLB batch translate failed (%s) — retrying per segment", exc)
            res = []
            for t in chunk:
                try:
                    res.append(translator.translate(t, src_flores))
                except Exception as exc2:  # noqa: BLE001 — one bad segment ≠ failed run
                    logger.warning("NLLB segment translate failed (%s) — keeping source text", exc2)
                    res.append(None)
        for i, t in zip(pending_idx[start:start + BATCH_SIZE], res):
            if t is not None:
                translated[i] = t

    for i, seg in enumerate(segments):
        text = translated.get(i)
        if text is None:
            text = (seg.get("text") or "").strip()
        out.append({**seg, "text": text})
    return out
