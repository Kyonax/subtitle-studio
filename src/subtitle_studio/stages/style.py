"""Stage 5: transcript JSON + styles.toml -> the styled ASS sidecar."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from subtitle_studio import paths
from subtitle_studio.schema import load_transcript
from subtitle_studio.state import hash_file, record_stage
from subtitle_studio.subtitles.ass_builder import build_ass
from subtitle_studio.subtitles.layout import CPS_WARN_THRESHOLD, segment_events
from subtitle_studio.subtitles.styleconf import load_styles, parse_position

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

    # Two keys, role first: [track.source] / [track.translated] carry the rule
    # that does not care which language it is ("what I am speaking is yellow,
    # the other one is white"), and [track.<lang>] overrides it per language.
    lang_key = transcript.language or "und"
    role = "translated" if transcript.translated_from else "source"
    track_key = (role, lang_key)

    warned = 0
    for segment in transcript.segments:
        _, style = styles.resolve(
            segment.speaker, transcript.display_name(segment.speaker), preset, track_key
        )
        for event in segment_events(segment, style.max_line_chars, style.max_lines, style.max_words):
            if event.cps > CPS_WARN_THRESHOLD:
                warned += 1
    if warned and on_progress:
        on_progress(f"warning: {warned} event(s) above {CPS_WARN_THRESHOLD} chars/sec — hard to read", 0.5)

    document = build_ass(transcript, styles, fonts_dir, preset=preset, track=track_key)
    out = paths.subs_path(workdir, lang_key)
    # Only touch the file when the subtitles actually changed. Previews rebuild
    # the ASS constantly (that is what makes the preview truthful), and a
    # rewrite with identical bytes would age every artifact built from it —
    # the burned video and the muxed one would report themselves stale for no
    # reason at all.
    if not out.exists() or out.read_text(encoding="utf-8") != document:
        out.write_text(document, encoding="utf-8")

    inputs = {
        "transcript": hash_file(transcript_file),
        "style-opts": hash_obj({"preset": preset, "position": position, "track": list(track_key)}),
    }
    if styles_file:
        inputs["styles"] = hash_file(styles_file)
    record_stage(workdir, f"style:{lang_key}", inputs)
    if on_progress:
        on_progress("ASS written", 1.0)
    return out


def combined_document(
    transcripts: list,
    styles,
    fonts_dir: Path | None,
    preset: str | None,
) -> str:
    """The all-languages ASS text, for the preview and the burn alike.

    Both callers go through this one function, so the frame the preview shows
    and the video the burn writes cannot resolve a track differently (Law 4).
    Each segment is keyed by (role, language), so [track.source] and
    [track.translated] apply first and [track.<lang>] overrides them.
    """
    from subtitle_studio.preview import merge_transcripts

    roles = {
        (t.language or "und"): ("translated" if t.translated_from else "source")
        for t in transcripts
    }
    merged, track_by_id = merge_transcripts(transcripts)

    def track_of(segment):
        lang = track_by_id.get(segment.id)
        return (roles.get(lang, "source"), lang) if lang else None

    return build_ass(merged, styles, fonts_dir, preset=preset, track_of=track_of)


def run_style_combined(
    input_media: Path,
    workdir: Path,
    styles_path: Path | None = None,
    fonts_dir: Path | None = None,
    preset: str | None = None,
    position: str | None = None,
    on_progress: ProgressFn | None = None,
) -> Path | None:
    """Every built track in ONE ass -> combined.ass, or None if there is only one.

    This is the document behind both the all-languages preview and the
    all-languages burn, and that is the point: preview truth (Law 4) only holds
    while the thing on screen and the thing burned are the same bytes.

    Each segment keeps its own [track.<lang>] look, and events sharing a
    timespan are separated by the builder's own overlap stacking — the same
    arithmetic a single-language document uses.
    """
    from subtitle_studio.state import hash_obj
    from subtitle_studio.web.status import available_tracks

    entries = available_tracks(workdir)
    transcripts, keys = [], []
    for entry in entries:
        path = paths.transcript_path(workdir, entry["id"] or None)
        try:
            transcripts.append(load_transcript(path))
            keys.append(path)
        except Exception:
            continue  # a half-written or older-schema track must not kill the burn
    if len(transcripts) < 2:
        return None

    styles_file = resolve_styles_path(styles_path, input_media)
    styles = load_styles(styles_file)
    preset = preset or styles.default_preset
    if position:
        styles.default = styles.default.model_copy(update={"position": parse_position(position)})

    if on_progress:
        on_progress(f"building one subtitle from {len(transcripts)} languages", 0.4)

    document = combined_document(transcripts, styles, fonts_dir, preset)
    out = paths.combined_subs_path(workdir)
    if not out.exists() or out.read_text(encoding="utf-8") != document:
        out.write_text(document, encoding="utf-8")

    inputs = {
        "transcripts": hash_obj([hash_file(p) for p in keys]),
        "style-opts": hash_obj({"preset": preset, "position": position}),
    }
    if styles_file:
        inputs["styles"] = hash_file(styles_file)
    record_stage(workdir, "style:combined", inputs)
    if on_progress:
        on_progress("combined subtitle written", 1.0)
    return out
