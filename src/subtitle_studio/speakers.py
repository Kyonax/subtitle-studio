"""Speaker map operations: list talk time, rename ids to real names.

Renames touch `transcript.json` AND every `transcript.<lang>.json` sibling so
translated variants never drift from the source (single-authority rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from subtitle_studio import paths
from subtitle_studio.schema import load_transcript, save_transcript


@dataclass
class SpeakerRow:
    speaker_id: str
    name: str | None
    segments: int
    talk_time_s: float


def list_speakers(workdir: Path) -> list[SpeakerRow]:
    transcript = load_transcript(paths.transcript_path(workdir))
    rows = []
    for sid, info in transcript.speakers.items():
        segs = [s for s in transcript.segments if s.speaker == sid]
        rows.append(
            SpeakerRow(
                speaker_id=sid,
                name=info.name,
                segments=len(segs),
                talk_time_s=round(sum(s.end - s.start for s in segs), 1),
            )
        )
    return rows


def rename_speaker(workdir: Path, speaker_id: str, name: str) -> list[Path]:
    """Set the display name for a stable speaker id in all transcript variants."""
    targets = [paths.transcript_path(workdir), *paths.translated_transcripts(workdir)]
    touched = []
    for target in targets:
        if not target.exists():
            continue
        transcript = load_transcript(target)
        if speaker_id not in transcript.speakers:
            known = ", ".join(transcript.speakers) or "none (run diarize first)"
            raise KeyError(f"{speaker_id!r} not in {target.name} — known speakers: {known}")
        transcript.speakers[speaker_id].name = name
        save_transcript(transcript, target)
        touched.append(target)
    return touched
