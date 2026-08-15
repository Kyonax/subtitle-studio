"""Fallback engine: plain faster-whisper with native word timestamps.

Slightly looser word timing than WhisperX's forced alignment, but a much smaller
dependency surface — the hedge against whisperx/torch pin breakage.
"""

from __future__ import annotations

from pathlib import Path

from subtitle_studio.asr.engine import AsrResult, ProgressFn
from subtitle_studio.config import Settings
from subtitle_studio.gpu import cuda_available, gpu_model
from subtitle_studio.schema import Segment, Word


class FasterWhisperEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def transcribe(
        self,
        audio_path: Path,
        language: str | None,
        batch_size: int,  # unused: faster-whisper streams sequentially
        on_progress: ProgressFn | None = None,
    ) -> AsrResult:
        from faster_whisper import WhisperModel

        cfg = self.settings.asr
        device = "cuda" if cuda_available() else "cpu"
        compute_type = cfg.compute_type if device == "cuda" else "int8"

        if on_progress:
            on_progress(f"loading whisper {cfg.model} ({compute_type}, {device})", 0.05)
        with gpu_model(lambda: WhisperModel(cfg.model, device=device, compute_type=compute_type)) as model:
            if on_progress:
                on_progress("transcribing", 0.15)
            raw_segments, info = model.transcribe(
                str(audio_path),
                language=language,
                word_timestamps=True,
                vad_filter=True,
                condition_on_previous_text=cfg.condition_on_previous_text,
            )
            segments = [
                Segment(
                    id=i,
                    start=round(seg.start, 3),
                    end=round(seg.end, 3),
                    text=seg.text.strip(),
                    words=[
                        Word(
                            word=w.word.strip(),
                            start=round(w.start, 3),
                            end=round(w.end, 3),
                            score=round(w.probability, 3),
                        )
                        for w in (seg.words or [])
                    ],
                    avg_logprob=seg.avg_logprob,
                    no_speech_prob=seg.no_speech_prob,
                )
                for i, seg in enumerate(raw_segments)
            ]

        if on_progress:
            on_progress("transcription done", 1.0)
        return AsrResult(
            language=info.language,
            language_probability=info.language_probability,
            segments=segments,
            models={"asr": cfg.model, "compute_type": compute_type, "alignment": None},
        )
