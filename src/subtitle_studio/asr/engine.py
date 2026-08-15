"""ASR engine interface. WhisperX is the accuracy-first default; plain
faster-whisper is the dependency-churn escape hatch (`[asr] engine` in config).
Both return the same result shape, so downstream only knows the JSON contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from subtitle_studio.config import Settings
from subtitle_studio.schema import Segment

ProgressFn = Callable[[str, float], None]


@dataclass
class AsrResult:
    language: str
    language_probability: float | None
    segments: list[Segment]
    models: dict[str, str | None] = field(default_factory=dict)  # asr / compute_type / alignment


class AsrEngine(Protocol):
    def transcribe(
        self,
        audio_path: Path,
        language: str | None,
        batch_size: int,
        on_progress: ProgressFn | None = None,
    ) -> AsrResult: ...


def get_engine(settings: Settings) -> AsrEngine:
    name = settings.asr.engine
    if name == "whisperx":
        from subtitle_studio.asr.whisperx_engine import WhisperxEngine

        return WhisperxEngine(settings)
    if name == "faster-whisper":
        from subtitle_studio.asr.faster_whisper_engine import FasterWhisperEngine

        return FasterWhisperEngine(settings)
    raise ValueError(f"unknown asr engine {name!r} (expected whisperx | faster-whisper)")
