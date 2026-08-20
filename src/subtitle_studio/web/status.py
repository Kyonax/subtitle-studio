"""What the page shows: one snapshot of a job's real state, read from disk.

The badges are derived the same way the TUI derives them — files that exist,
plus the recorded input hashes for the stages where staleness matters (Law 3,
the translation staleness chain). Hashing is kept cheap on purpose: transcripts
and styles.toml are small and get hashed, the source video never does — for the
file-sized stages a newer artifact than its input is the honest signal.
"""

from __future__ import annotations

from pathlib import Path

from subtitle_studio import paths
from subtitle_studio.config import Settings
from subtitle_studio.schema import Transcript, load_transcript
from subtitle_studio.state import hash_file, hash_obj, load_state, stage_fresh

LOW_CONFIDENCE = 0.5

# Plain names for the track rail. Unknown codes show the code itself, which is
# still the truth — never a guess at a language.
LANGUAGE_NAMES = {
    "ar": "arabic", "ca": "catalan", "cs": "czech", "da": "danish", "de": "german",
    "el": "greek", "en": "english", "es": "spanish", "eu": "basque", "fa": "persian",
    "fi": "finnish", "fr": "french", "gl": "galician", "he": "hebrew", "hi": "hindi",
    "hu": "hungarian", "id": "indonesian", "it": "italian", "ja": "japanese",
    "ko": "korean", "nl": "dutch", "no": "norwegian", "pl": "polish",
    "pt": "portuguese", "ro": "romanian", "ru": "russian", "sv": "swedish",
    "th": "thai", "tr": "turkish", "uk": "ukrainian", "vi": "vietnamese",
    "zh": "chinese",
}


def language_name(code: str | None) -> str:
    if not code:
        return "unknown"
    return LANGUAGE_NAMES.get(code.lower(), code)

MEDIA_SUFFIXES = {
    ".mkv", ".mp4", ".mov", ".webm", ".avi", ".m4v", ".flv", ".ts",
    ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac",
}


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _newer(artifact: Path, *sources: Path) -> bool:
    """True when `artifact` was written after every source that feeds it."""
    made = _mtime(artifact)
    if made is None:
        return False
    return all((_mtime(src) or 0) <= made for src in sources)


def translate_inputs(workdir: Path, settings: Settings, track: str) -> dict:
    return {
        "transcript": hash_file(paths.transcript_path(workdir)),
        "config:translation": hash_obj(settings.translation.model_dump()),
        "to": track,
        "mode": "swap" if track == "swap" else "invert",
    }


def translate_state(workdir: Path, settings: Settings, track: str | None) -> str:
    """fresh | stale | missing — stale means the source transcript changed
    (an edit, a relisten) after this translation was made."""
    if not track:
        return "missing"
    if not paths.transcript_path(workdir, track).exists():
        return "missing"
    if not paths.transcript_path(workdir).exists():
        return "stale"
    fresh = stage_fresh(load_state(workdir), f"translate:{track}", translate_inputs(workdir, settings, track))
    return "fresh" if fresh else "stale"


def track_language(workdir: Path, track: str | None) -> str:
    """The `.ass` / `.mp4` key for a track: the track name for translations,
    the detected language for the source transcript."""
    if track:
        return track
    transcript_file = paths.transcript_path(workdir)
    if not transcript_file.exists():
        return "und"
    try:
        return load_transcript(transcript_file).language or "und"
    except Exception:
        return "und"


def available_tracks(workdir: Path) -> list[dict]:
    tracks = []
    source = paths.transcript_path(workdir)
    if source.exists():
        try:
            language = load_transcript(source).language or "und"
        except Exception:
            language = "und"
        tracks.append({"id": "", "label": f"source ({language})", "language": language, "kind": "source"})
    for translated in paths.translated_transcripts(workdir):
        name = translated.name[len("transcript.") : -len(".json")]
        label = "swap (bilingual cross)" if name == "swap" else f"translated ({name})"
        tracks.append({"id": name, "label": label, "language": name, "kind": "swap" if name == "swap" else "unify"})
    return tracks


def subtitle_tracks(workdir: Path, settings: Settings, styles_path: Path | None) -> list[dict]:
    """One entry per subtitle this video carries: the source transcript plus
    every translated variant, each with the three states that matter — is the
    text there, are the subtitles built from it, is a burned video newer than
    them. This is what the track rail iterates."""
    source_file = paths.transcript_path(workdir)
    if not source_file.exists():
        return []

    def state_for(track: str | None, transcript_file: Path, language: str) -> dict:
        subs = paths.subs_path(workdir, language)
        render = paths.render_path(workdir, language)
        sources = [transcript_file] + ([styles_path] if styles_path and styles_path.exists() else [])
        try:
            segments = len(load_transcript(transcript_file).segments)
        except Exception:
            segments = 0
        return {
            "id": track or "",
            "language": language,
            "name": language_name(language) if track != "swap" else "bilingual cross",
            "kind": "source" if track is None else ("swap" if track == "swap" else "unify"),
            "segments": segments,
            "translate": "n/a" if track is None else translate_state(workdir, settings, track),
            "styled": ("done" if _newer(subs, *sources) else "stale") if subs.exists() else "pending",
            "burned": ("done" if _newer(render, subs) else "stale") if render.exists() else "pending",
            "paths": {
                "transcript": str(transcript_file),
                "subs": str(subs) if subs.exists() else None,
                "render": str(render) if render.exists() else None,
            },
        }

    try:
        source_language = load_transcript(source_file).language or "und"
    except Exception:
        source_language = "und"

    tracks = [state_for(None, source_file, source_language)]
    for translated in paths.translated_transcripts(workdir):
        track = translated.name[len("transcript.") : -len(".json")]
        tracks.append(state_for(track, translated, track))
    return tracks


def delivery_state(workdir: Path, tracks: list[dict]) -> dict:
    """The one video carrying every track: whether it exists and whether it is
    newer than every subtitle file that went into it."""
    muxed = paths.muxed_path(workdir)
    built = [Path(track["paths"]["subs"]) for track in tracks if track["paths"]["subs"]]
    if not muxed.exists():
        state = "pending"
    else:
        state = "done" if _newer(muxed, *built) else "stale"
    return {
        "path": str(muxed) if muxed.exists() else None,
        "state": state,
        "mtime": _mtime(muxed),
        "tracks_built": [track["id"] for track in tracks if track["paths"]["subs"]],
    }


def _segment_rows(transcript: Transcript) -> list[dict]:
    rows = []
    for seg in transcript.segments:
        scores = [w.score for w in seg.words if w.score is not None]
        rows.append(
            {
                "id": seg.id,
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "speaker": seg.speaker,
                "speaker_name": transcript.display_name(seg.speaker),
                "language": seg.language,
                "text": seg.text,
                "source_text": seg.source_text,
                "words": len(seg.words),
                "low_confidence": any(score < LOW_CONFIDENCE for score in scores),
            }
        )
    return rows


def _speaker_rows(transcript: Transcript) -> list[dict]:
    rows = []
    for speaker_id, info in transcript.speakers.items():
        segments = [s for s in transcript.segments if s.speaker == speaker_id]
        rows.append(
            {
                "id": speaker_id,
                "name": info.name,
                "style": info.style,
                "segments": len(segments),
                "talk_time_s": round(sum(s.end - s.start for s in segments), 1),
            }
        )
    return sorted(rows, key=lambda row: -row["talk_time_s"])


def _language_rows(transcript: Transcript) -> list[dict]:
    totals: dict[str, list[float]] = {}
    for seg in transcript.segments:
        code = seg.language or transcript.language or "und"
        bucket = totals.setdefault(code, [0.0, 0.0])
        bucket[0] += 1
        bucket[1] += seg.end - seg.start
    return sorted(
        ({"code": code, "segments": int(count), "talk_time_s": round(seconds, 1)} for code, (count, seconds) in totals.items()),
        key=lambda row: -row["talk_time_s"],
    )


def styles_info(input_media: Path | None, preset: str | None = None) -> dict:
    from subtitle_studio.stages.style import resolve_styles_path
    from subtitle_studio.subtitles.styleconf import ANCHORS, load_styles

    resolved = resolve_styles_path(None, input_media)
    config = load_styles(resolved)
    active = preset or config.default_preset
    try:
        effective = config.base(active).model_dump()
        error = None
    except ValueError as exc:  # unknown preset name
        effective = config.default.model_dump()
        error = str(exc)
    return {
        "path": str(resolved) if resolved else None,
        "mtime": _mtime(resolved) if resolved else None,
        "presets": config.preset_names(),
        "default_preset": config.default_preset,
        "speakers": sorted(config.speaker),
        "preset": active,
        "effective": effective,
        "default": config.default.model_dump(),
        "anchors": list(ANCHORS),
        "error": error,
    }


def job_state(input_media: Path | None, settings: Settings, track: str | None = None, out: Path | None = None) -> dict:
    """Everything one page render needs: files on disk, stage badges, transcript."""
    state: dict = {
        "input": str(input_media) if input_media else None,
        "name": input_media.name if input_media else None,
        "exists": bool(input_media and input_media.exists()),
        "workdir": None,
        "track": track or "",
        "tracks": [],
        "stages": {},
        "transcript": None,
        "speakers": [],
        "languages": [],
        "artifacts": {},
    }
    if not input_media or not input_media.exists():
        return state

    workdir = paths.studio_dir(input_media, out)
    state["workdir"] = str(workdir)

    audio = paths.audio_path(workdir)
    transcript_file = paths.transcript_path(workdir)
    lang_key = track_language(workdir, track)
    subs = paths.subs_path(workdir, lang_key)
    render = paths.render_path(workdir, lang_key)

    transcript = None
    if transcript_file.exists():
        try:
            transcript = load_transcript(transcript_file)
        except Exception as exc:
            state["transcript_error"] = str(exc)

    shown_file = paths.transcript_path(workdir, track) if track else transcript_file
    shown = transcript
    if track and shown_file.exists():
        try:
            shown = load_transcript(shown_file)
        except Exception as exc:
            state["transcript_error"] = str(exc)
            shown = None

    if transcript is not None:
        state["tracks"] = available_tracks(workdir)
        state["speakers"] = _speaker_rows(transcript)
        state["languages"] = _language_rows(transcript)
    if shown is not None:
        state["transcript"] = {
            "path": str(shown_file),
            "language": shown.language,
            "language_probability": shown.language_probability,
            "translated_from": shown.translated_from,
            "created_at": shown.created_at,
            "models": shown.models.model_dump(),
            "duration_s": shown.source.duration_s,
            "video": shown.source.video.model_dump() if shown.source.video else None,
            "segments": _segment_rows(shown),
            "editable_words": not bool(shown.translated_from),
        }

    styles = styles_info(input_media)
    styles_path = Path(styles["path"]) if styles["path"] else None

    tstate = translate_state(workdir, settings, track or None)
    style_sources = [shown_file] + ([styles_path] if styles_path else [])
    state["stages"] = {
        "extract": {
            "state": "done" if audio.exists() else "pending",
            "path": str(audio) if audio.exists() else None,
        },
        "transcribe": {
            "state": "done" if transcript_file.exists() else "pending",
            "path": str(transcript_file) if transcript_file.exists() else None,
            "detail": f"{len(transcript.segments)} segments" if transcript else None,
        },
        "diarize": {
            "state": "done" if (transcript and transcript.speakers) else "pending",
            "detail": f"{len(transcript.speakers)} speakers" if transcript and transcript.speakers else None,
        },
        "translate": {
            "state": "done" if tstate == "fresh" else ("stale" if tstate == "stale" else "pending"),
            "path": str(paths.transcript_path(workdir, track)) if track and paths.transcript_path(workdir, track).exists() else None,
            "detail": None if track else "pick a track to translate",
        },
        "style": {
            "state": ("done" if _newer(subs, *[p for p in style_sources if p and p.exists()]) else "stale") if subs.exists() else "pending",
            "path": str(subs) if subs.exists() else None,
            "detail": lang_key,
        },
        "render": {
            "state": ("done" if _newer(render, subs) else "stale") if render.exists() else "pending",
            "path": str(render) if render.exists() else None,
        },
    }
    state["artifacts"] = {
        "audio": str(audio) if audio.exists() else None,
        "transcript": str(transcript_file) if transcript_file.exists() else None,
        "subs": str(subs) if subs.exists() else None,
        "render": str(render) if render.exists() else None,
        "render_mtime": _mtime(render),
    }
    state["styles"] = styles
    state["subtitles"] = subtitle_tracks(workdir, settings, styles_path)
    state["delivery"] = delivery_state(workdir, state["subtitles"])
    return state
