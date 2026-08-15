"""The transcript JSON contract — the single interface between every pipeline stage.

Version rules:
- SPEAKER_XX keys in `speakers` are stable ids forever; renaming only fills `.name`.
- Translated variants copy timing/speakers verbatim, empty `words`, keep `source_text`.
- Loaders reject unknown schema_version; writes are atomic with a `.bak` of the
  previous version.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from subtitle_studio import __version__

SCHEMA_VERSION = 1


class Word(BaseModel):
    word: str
    start: float
    end: float
    score: float | None = None
    speaker: str | None = None


class Segment(BaseModel):
    id: int
    start: float
    end: float
    speaker: str | None = None
    language: str | None = None  # per-segment detected language (mixed videos)
    text: str
    words: list[Word] = Field(default_factory=list)
    source_text: str | None = None
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


class SpeakerInfo(BaseModel):
    name: str | None = None
    style: str | None = None


class VideoInfo(BaseModel):
    width: int
    height: int
    fps: float


class SourceInfo(BaseModel):
    media_path: str
    audio_path: str | None = None
    duration_s: float | None = None
    video: VideoInfo | None = None


class ToolInfo(BaseModel):
    name: str = "subtitle-studio"
    version: str = __version__


class ModelsInfo(BaseModel):
    asr: str | None = None
    compute_type: str | None = None
    alignment: str | None = None
    diarization: str | None = None
    translation: str | None = None


class Transcript(BaseModel):
    schema_version: int = SCHEMA_VERSION
    tool: ToolInfo = Field(default_factory=ToolInfo)
    created_at: str = Field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    source: SourceInfo
    language: str | None = None
    language_probability: float | None = None
    translated_from: str | None = None
    models: ModelsInfo = Field(default_factory=ModelsInfo)
    speakers: dict[str, SpeakerInfo] = Field(default_factory=dict)
    segments: list[Segment] = Field(default_factory=list)

    def display_name(self, speaker_id: str | None) -> str | None:
        if speaker_id is None:
            return None
        info = self.speakers.get(speaker_id)
        return (info.name if info and info.name else None) or speaker_id


def retime_words(segment: "Segment", new_text: str) -> list[Word]:
    """Word list for edited text: same word count keeps the original timings,
    otherwise the new words share the segment's span proportionally."""
    tokens = new_text.split()
    if len(tokens) == len(segment.words) and segment.words:
        return [
            Word(word=t, start=w.start, end=w.end, score=None, speaker=w.speaker)
            for t, w in zip(tokens, segment.words)
        ]
    count = len(tokens) or 1
    step = (segment.end - segment.start) / count
    return [
        Word(
            word=t,
            start=round(segment.start + i * step, 3),
            end=round(segment.start + (i + 1) * step, 3),
            score=None,
            speaker=segment.speaker,
        )
        for i, t in enumerate(tokens)
    ]


class SchemaVersionError(ValueError):
    pass


def load_transcript(path: str | Path) -> Transcript:
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise SchemaVersionError(
            f"{path}: schema_version {version!r} is not supported by this build "
            f"(expected {SCHEMA_VERSION}). Upgrade subtitle-studio or regenerate the transcript."
        )
    return Transcript.model_validate(raw)


def save_transcript(transcript: Transcript, path: str | Path) -> None:
    """Atomic write (tmp + rename); previous version preserved as `<name>.bak`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)
