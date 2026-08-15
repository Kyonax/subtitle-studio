"""Stage 5: transcript JSON + styles.toml -> the styled ASS sidecar."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from subtitle_studio import paths
from subtitle_studio.schema import load_transcript
from subtitle_studio.state import hash_file, record_stage
from subtitle_studio.subtitles.ass_builder import build_ass
from subtitle_studio.subtitles.layout import CPS_WARN_THRESHOLD, segment_events
from subtitle_studio.subtitles.styleconf import load_styles

ProgressFn = Callable[[str, float], None]


def project_root() -> Path | None:
    """The subtitle-studio checkout root (walks up to pyproject.toml)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return None


def user_styles_path() -> Path:
    import os

    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "subtitle-studio" / "styles.toml"


def resolve_styles_path(explicit: Path | None, input_media: Path | None) -> Path | None:
    """The styles file every command and the TUI agree on.

    Order: --styles PATH, a styles.toml next to the input (per-video override),
    THE project styles.toml inside subtitle-studio, the user config file,
    else None (built-in defaults).
    """
    root = project_root()
    candidates = [
        explicit,
        input_media.parent / "styles.toml" if input_media else None,
        root / "styles.toml" if root else None,
        user_styles_path(),
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


def resolve_fonts_dir(configured: str | None) -> Path | None:
    for candidate in [Path(configured).expanduser() if configured else None, Path("fonts")]:
        if candidate and candidate.is_dir():
            return candidate
    return None


def run_style(
    input_media: Path,
    workdir: Path,
    lang: str | None = None,
    styles_path: Path | None = None,
    fonts_dir: Path | None = None,
    preset: str | None = None,
    position: str | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    from subtitle_studio.state import hash_obj
    from subtitle_studio.subtitles.styleconf import parse_position

    transcript_file = paths.transcript_path(workdir, lang)
    transcript = load_transcript(transcript_file)
    styles_file = resolve_styles_path(styles_path, input_media)
    styles = load_styles(styles_file)
    preset = preset or styles.default_preset  # meta default_preset when none passed
    if position:
        styles.default = styles.default.model_copy(update={"position": parse_position(position)})

    if on_progress:
        label = styles_file.name if styles_file else "default styles"
        on_progress(f"building ASS ({label}{f', preset {preset}' if preset else ''})", 0.3)

    warned = 0
    for segment in transcript.segments:
        _, style = styles.resolve(segment.speaker, transcript.display_name(segment.speaker), preset)
        for event in segment_events(segment, style.max_line_chars, style.max_lines, style.max_words):
            if event.cps > CPS_WARN_THRESHOLD:
                warned += 1
    if warned and on_progress:
        on_progress(f"warning: {warned} event(s) above {CPS_WARN_THRESHOLD} chars/sec — hard to read", 0.5)

    document = build_ass(transcript, styles, fonts_dir, preset=preset)
    out = paths.subs_path(workdir, transcript.language or "und")
    out.write_text(document, encoding="utf-8")

    inputs = {
        "transcript": hash_file(transcript_file),
        "style-opts": hash_obj({"preset": preset, "position": position}),
    }
    if styles_file:
        inputs["styles"] = hash_file(styles_file)
    record_stage(workdir, f"style:{transcript.language or 'und'}", inputs)
    if on_progress:
        on_progress("ASS written", 1.0)
    return out
