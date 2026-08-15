"""MADLAD-400-3B-MT via CTranslate2 int8 — local, free, Apache 2.0, 400+ languages.

Weights: pre-converted CT2 repo (Nextcloud-AI/madlad400-3b-mt-ct2-int8, ~3GB) pulled
into the models cache on first use. Convention: the target language is a sentence
prefix token, `<2pt> Hola` -> Portuguese.
"""

from __future__ import annotations

from pathlib import Path

import difflib
import re

from subtitle_studio.config import Settings
from subtitle_studio.gpu import cuda_available

CT2_REPO = "Nextcloud-AI/madlad400-3b-mt-ct2-int8"

_SPLIT_POINTS = re.compile(r"[.,;:!?…]+\s+")


def _normalize(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text).casefold().strip()


def collapse_repetition(text: str) -> str:
    """MADLAD-3B often doubles short outputs ('Exactly. Exactly.'). Collapse a
    translation made of two near-identical halves, and consecutive duplicate
    sentences. The source text survives in the JSON, so this is safe to apply."""
    # two near-identical halves split at any punctuation boundary
    for m in _SPLIT_POINTS.finditer(text):
        left, right = text[: m.start()], text[m.end():]
        if not left or not right:
            continue
        if difflib.SequenceMatcher(None, _normalize(left), _normalize(right)).ratio() > 0.85:
            boundary = text[m.start():m.end()].rstrip()
            ending = text.rstrip()[-1:] if text.rstrip()[-1:] in ".!?…" else "."
            return left + (boundary if boundary in (".", "!", "?", "…") else ending)
    # consecutive duplicate sentences
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    kept: list[str] = []
    for sentence in sentences:
        if kept and _normalize(sentence) == _normalize(kept[-1]):
            continue
        kept.append(sentence)
    return " ".join(kept)


class MadladProvider:
    name = "madlad"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._translator = None
        self._sp = None

    def model_dir(self) -> Path:
        return Path(self.settings.paths.models_dir).expanduser() / "madlad400-3b-mt-ct2-int8"

    def ensure_model(self) -> Path:
        target = self.model_dir()
        if not (target / "model.bin").exists():
            from huggingface_hub import snapshot_download

            snapshot_download(CT2_REPO, local_dir=target)
        return target

    def _load(self) -> None:
        if self._translator is not None:
            return
        import ctranslate2
        import sentencepiece

        model_dir = self.ensure_model()
        use_cuda = self.settings.translation.device == "cuda" and cuda_available()
        self._translator = ctranslate2.Translator(
            str(model_dir),
            device="cuda" if use_cuda else "cpu",
            compute_type="int8_float16" if use_cuda else "int8",
        )
        self._sp = sentencepiece.SentencePieceProcessor(model_file=str(model_dir / "spiece.model"))

    def unload(self) -> None:
        self._translator = None
        self._sp = None

    def supports(self, code: str) -> bool:
        self._load()
        return self._sp.piece_to_id(f"<2{code}>") != self._sp.unk_id()

    def language_error(self, code: str) -> str:
        return (
            f"language {code!r} is not a MADLAD-400 target (token <2{code}> unknown). "
            "Use ISO codes like en, es, pt, fr, de, it, ja, ko, zh, ru, ar, hi …"
        )

    def translate_batch(self, texts: list[str], src: str, tgt: str) -> list[str]:
        self._load()
        cfg = self.settings.translation
        if not self.supports(tgt):
            raise ValueError(self.language_error(tgt))

        tokenized = [self._sp.encode(f"<2{tgt}> {text}", out_type=str) for text in texts]
        results = self._translator.translate_batch(
            tokenized,
            beam_size=cfg.beam_size,
            max_batch_size=cfg.batch_size,
            max_decoding_length=512,
        )
        return [collapse_repetition(self._sp.decode(r.hypotheses[0])) for r in results]
