"""Stage 3: speaker diarization (pyannote) merged onto the transcript.

Segments get a `speaker` (max temporal overlap with diarization turns), words get
their own assignment, and segments whose words disagree with the segment speaker
are honest about it — the disagreement is preserved for TUI review instead of
being smoothed over.

Setup (one-time, free): HuggingFace account, accept terms on BOTH
  https://huggingface.co/pyannote/speaker-diarization-3.1
  https://huggingface.co/pyannote/segmentation-3.0
then `export HF_TOKEN=hf_...` (or `[auth] hf_token` in config.toml).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from subtitle_studio import paths
from subtitle_studio.config import Settings
from subtitle_studio.gpu import cuda_available, gpu_model
from subtitle_studio.schema import SpeakerInfo, Transcript, load_transcript, save_transcript
from subtitle_studio.state import hash_file, hash_obj, record_stage

ProgressFn = Callable[[str, float], None]


class DiarizationAuthError(RuntimeError):
    pass


def _load_pipeline(settings: Settings):
    from pyannote.audio import Pipeline

    token = settings.hf_token()
    if not token:
        raise DiarizationAuthError(
            "diarization needs a (free) HuggingFace token for the gated pyannote models: "
            "create one at https://huggingface.co/settings/tokens, accept the terms on "
            "pyannote/speaker-diarization-3.1 AND pyannote/segmentation-3.0, then "
            "export HF_TOKEN=hf_... (or set [auth] hf_token in config.toml)."
        )
    try:  # pyannote >= 4
        pipeline = Pipeline.from_pretrained(settings.diarization.model, token=token)
    except TypeError:  # pyannote 3.x signature
        pipeline = Pipeline.from_pretrained(settings.diarization.model, use_auth_token=token)
    if pipeline is None:
        raise DiarizationAuthError(
            f"could not load {settings.diarization.model} — has this HF account accepted "
            "the model terms for it (and for pyannote/segmentation-3.0)?"
        )
    if cuda_available():
        import torch

        pipeline.to(torch.device("cuda"))
    return pipeline


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _best_speaker(start: float, end: float, turns: list[tuple[float, float, str]]) -> str | None:
    scores: dict[str, float] = {}
    for t_start, t_end, speaker in turns:
        ov = _overlap(start, end, t_start, t_end)
        if ov > 0:
            scores[speaker] = scores.get(speaker, 0.0) + ov
    return max(scores, key=scores.get) if scores else None


def run_diarize(
    input_media: Path,
    workdir: Path,
    settings: Settings,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    audio = paths.audio_path(workdir)
    transcript_file = paths.transcript_path(workdir)
    transcript = load_transcript(transcript_file)

    if on_progress:
        on_progress("loading diarization pipeline", 0.05)
    kwargs: dict = {}
    if min_speakers or settings.diarization.min_speakers:
        kwargs["min_speakers"] = min_speakers or settings.diarization.min_speakers
    if max_speakers or settings.diarization.max_speakers:
        kwargs["max_speakers"] = max_speakers or settings.diarization.max_speakers

    with gpu_model(lambda: _load_pipeline(settings)) as pipeline:
        if on_progress:
            on_progress("diarizing", 0.2)
        annotation = pipeline(str(audio), **kwargs)

    turns = [
        (turn.start, turn.end, speaker)
        for turn, _, speaker in annotation.itertracks(yield_label=True)
    ]

    if on_progress:
        on_progress("assigning speakers to words", 0.9)
    speaker_ids = sorted({speaker for *_, speaker in turns})
    transcript.speakers = {
        sid: transcript.speakers.get(sid, SpeakerInfo()) for sid in speaker_ids
    }
    for segment in transcript.segments:
        segment.speaker = _best_speaker(segment.start, segment.end, turns)
        for word in segment.words:
            word.speaker = _best_speaker(word.start, word.end, turns) or segment.speaker

    transcript.models.diarization = settings.diarization.model
    save_transcript(transcript, transcript_file)
    record_stage(
        workdir,
        "diarize",
        {
            "audio": hash_file(audio),
            "config:diarization": hash_obj(settings.diarization.model_dump()),
        },
    )
    if on_progress:
        on_progress("diarization done", 1.0)
    return transcript_file
