"""Per-segment language identification (fasttext lid.176, offline, <1MB).

Whisper detects ONE language per file; mixed-language videos (code-switching)
need to know each segment's language so translation can pass through segments
already in the target language ("invert" a bilingual video into one language).
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from subtitle_studio.config import CACHE_DIR
from subtitle_studio.schema import Transcript

LID_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"
LID_PATH = CACHE_DIR / "models" / "lid.176.ftz"

# below this confidence (or fewer than MIN_WORDS words) we keep the transcript's
# file-level language instead of trusting the detector on a tiny snippet
MIN_CONFIDENCE = 0.55
MIN_WORDS = 2

_model = None


def ensure_lid_model() -> Path:
    if not LID_PATH.exists():
        LID_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = LID_PATH.with_suffix(".tmp")
        urllib.request.urlretrieve(LID_URL, tmp)
        tmp.replace(LID_PATH)
    return LID_PATH


def _load():
    global _model
    if _model is None:
        import fasttext

        _model = fasttext.load_model(str(ensure_lid_model()))
    return _model


def detect_language(text: str) -> tuple[str, float]:
    """-> (iso code like 'en'/'es', confidence 0..1)."""
    labels, probs = _load().predict(text.replace("\n", " ").strip(), k=1)
    code = labels[0].removeprefix("__label__") if labels else "und"
    return code, float(probs[0]) if len(probs) else 0.0


def annotate_segments(transcript: Transcript) -> dict[str, float]:
    """Fill each segment's `language`; -> {lang: talk_time_seconds} summary.

    Short/low-confidence segments inherit the transcript's file-level language.
    """
    talk_time: dict[str, float] = {}
    fallback = transcript.language or "und"
    for segment in transcript.segments:
        code, confidence = detect_language(segment.text)
        if confidence < MIN_CONFIDENCE or len(segment.text.split()) < MIN_WORDS:
            code = segment.language or fallback
        segment.language = code
        talk_time[code] = round(talk_time.get(code, 0.0) + (segment.end - segment.start), 1)
    return talk_time
