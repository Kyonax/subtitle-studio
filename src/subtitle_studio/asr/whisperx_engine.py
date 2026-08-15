"""WhisperX: faster-whisper inference + VAD chunking + wav2vec2 forced alignment.

VRAM law: the whisper model and the alignment model are loaded sequentially,
never together (6GB ceiling).
"""

from __future__ import annotations

from pathlib import Path

from subtitle_studio.asr.engine import AsrResult, ProgressFn
from subtitle_studio.config import Settings
from subtitle_studio.gpu import cuda_available, gpu_model, with_oom_backoff
from subtitle_studio.schema import Segment, Word

# Non-default alignment models we prefer over whisperx's builtin table
# (accuracy-first: large variants over whisperx's base defaults).
ALIGN_MODEL_OVERRIDES: dict[str, str] = {
    "en": "WAV2VEC2_ASR_LARGE_LV60K_960H",
    "es": "jonatasgrosman/wav2vec2-large-xlsr-53-spanish",
}


class WhisperxEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def transcribe(
        self,
        audio_path: Path,
        language: str | None,
        batch_size: int,
        on_progress: ProgressFn | None = None,
    ) -> AsrResult:
        import whisperx

        cfg = self.settings.asr
        device = "cuda" if cuda_available() else "cpu"
        compute_type = cfg.compute_type if device == "cuda" else "int8"

        audio = whisperx.load_audio(str(audio_path))

        if on_progress:
            on_progress(f"loading whisper {cfg.model} ({compute_type}, {device})", 0.05)
        with gpu_model(
            lambda: whisperx.load_model(
                cfg.model,
                device,
                compute_type=compute_type,
                language=language,
                asr_options={"condition_on_previous_text": cfg.condition_on_previous_text},
            )
        ) as model:
            if on_progress:
                on_progress("transcribing", 0.15)
            raw = with_oom_backoff(
                lambda bs: model.transcribe(audio, batch_size=bs, language=language),
                batch_size,
            )
        detected = raw["language"]

        align_model_name = ALIGN_MODEL_OVERRIDES.get(detected)
        if on_progress:
            on_progress(f"aligning word timestamps ({detected})", 0.7)
        try:
            with gpu_model(
                lambda: whisperx.load_align_model(language_code=detected, device=device, model_name=align_model_name)
            ) as (align_model, align_meta):
                aligned = whisperx.align(
                    raw["segments"], align_model, align_meta, audio, device, return_char_alignments=False
                )
            segments_raw = aligned["segments"]
            alignment_used = align_model_name or f"whisperx-default:{detected}"
        except ValueError:
            # No alignment model exists for this language — fall back to whisper timings.
            segments_raw = raw["segments"]
            alignment_used = None

        segments = [
            Segment(
                id=i,
                start=round(float(seg["start"]), 3),
                end=round(float(seg["end"]), 3),
                text=str(seg["text"]).strip(),
                words=[
                    Word(
                        word=w["word"],
                        start=round(float(w["start"]), 3) if "start" in w else -1.0,
                        end=round(float(w["end"]), 3) if "end" in w else -1.0,
                        score=round(float(w["score"]), 3) if "score" in w else None,
                    )
                    for w in seg.get("words", [])
                ],
                avg_logprob=seg.get("avg_logprob"),
                no_speech_prob=seg.get("no_speech_prob"),
            )
            for i, seg in enumerate(segments_raw)
        ]

        if on_progress:
            on_progress("transcription done", 1.0)
        return AsrResult(
            language=detected,
            language_probability=raw.get("language_probability"),
            segments=segments,
            models={"asr": cfg.model, "compute_type": compute_type, "alignment": alignment_used},
        )
