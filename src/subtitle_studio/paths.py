"""Per-job work directory layout.

For an input `interview.mkv` all artifacts live in `interview.studio/` next to it
(overridable with --out). Stages read/write these files so every stage is
individually invokable and resumable.
"""

from __future__ import annotations

from pathlib import Path

STUDIO_SUFFIX = ".studio"


def studio_dir(input_media: str | Path, out: str | Path | None = None) -> Path:
    if out is not None:
        return Path(out)
    input_media = Path(input_media)
    return input_media.parent / f"{input_media.stem}{STUDIO_SUFFIX}"


def audio_path(workdir: Path) -> Path:
    return workdir / "audio.wav"


def state_path(workdir: Path) -> Path:
    return workdir / "state.json"


def transcript_path(workdir: Path, lang: str | None = None) -> Path:
    """Source transcript, or the translated variant for `lang`."""
    return workdir / ("transcript.json" if lang is None else f"transcript.{lang}.json")


def translated_transcripts(workdir: Path) -> list[Path]:
    return sorted(p for p in workdir.glob("transcript.*.json") if not p.name.endswith(".bak"))


def subs_path(workdir: Path, lang: str) -> Path:
    return workdir / f"subs.{lang}.ass"


def render_path(workdir: Path, lang: str, ext: str = "mp4") -> Path:
    return workdir / f"render.{lang}.{ext}"
