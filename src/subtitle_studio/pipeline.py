"""The `run` orchestrator: chain stages, skipping the ones whose recorded input
hashes are unchanged. Shared by the CLI and the TUI (same functions, same
progress callback shape)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from subtitle_studio import paths
from subtitle_studio.config import Settings
from subtitle_studio.schema import load_transcript
from subtitle_studio.state import hash_file, hash_obj, invalidate_from, load_state, stage_fresh

ProgressFn = Callable[[str, str, float], None]  # (stage, message, fraction)

STAGE_ORDER = ["extract", "transcribe", "diarize", "translate", "style", "render"]


@dataclass
class RunPlan:
    input_media: Path
    workdir: Path
    settings: Settings
    to_lang: str | None = None
    swap: bool = False
    styles_path: Path | None = None
    fonts_dir: Path | None = None
    preset: str | None = None
    position: str | None = None
    burn: bool = False
    skip_diarize: bool = False


def run_pipeline(plan: RunPlan, on_progress: ProgressFn | None = None) -> dict[str, Path]:
    """Returns {stage: produced_path} for every stage that ran or was fresh."""
    def progress(stage: str):
        return (lambda msg, frac: on_progress(stage, msg, frac)) if on_progress else None

    def notify_skip(stage: str):
        if on_progress:
            on_progress(stage, "up to date — skipped", 1.0)

    produced: dict[str, Path] = {}
    workdir = plan.workdir
    settings = plan.settings
    state = load_state(workdir)

    # extract
    audio = paths.audio_path(workdir)
    if audio.exists() and stage_fresh(state, "extract", {"input": hash_file(plan.input_media)}):
        notify_skip("extract")
    else:
        from subtitle_studio.stages.extract import run_extract

        run_extract(plan.input_media, workdir, progress("extract"))
    produced["extract"] = audio

    # transcribe
    transcribe_inputs = {"audio": hash_file(audio), "config:asr": hash_obj(settings.asr.model_dump())}
    transcript_file = paths.transcript_path(workdir)
    if transcript_file.exists() and stage_fresh(load_state(workdir), "transcribe", transcribe_inputs):
        notify_skip("transcribe")
    else:
        from subtitle_studio.stages.transcribe import run_transcribe

        run_transcribe(plan.input_media, workdir, settings, on_progress=progress("transcribe"))
    produced["transcribe"] = transcript_file

    # diarize
    if not plan.skip_diarize:
        diarize_inputs = {
            "audio": hash_file(audio),
            "config:diarization": hash_obj(settings.diarization.model_dump()),
        }
        if load_transcript(transcript_file).speakers and stage_fresh(load_state(workdir), "diarize", diarize_inputs):
            notify_skip("diarize")
        else:
            from subtitle_studio.stages.diarize import run_diarize

            run_diarize(plan.input_media, workdir, settings, on_progress=progress("diarize"))
        produced["diarize"] = transcript_file

    # translate (optional): --to unify, or --swap cross
    track = "swap" if plan.swap else plan.to_lang
    if track:
        from subtitle_studio.stages.translate import run_translate

        translated = paths.transcript_path(workdir, track)
        translate_inputs = {
            "transcript": hash_file(transcript_file),
            "config:translation": hash_obj(settings.translation.model_dump()),
            "to": track,
            "mode": "swap" if plan.swap else "invert",
        }
        if translated.exists() and stage_fresh(load_state(workdir), f"translate:{track}", translate_inputs):
            notify_skip("translate")
        else:
            run_translate(
                plan.input_media, workdir, settings, plan.to_lang, swap=plan.swap,
                on_progress=progress("translate"),
            )
        produced["translate"] = translated

    # style (+ optional burn-in) for the requested track: translated/swap, else source
    from subtitle_studio.stages.style import run_style

    target_lang = track or (load_transcript(transcript_file).language or "und")
    produced["style"] = run_style(
        plan.input_media, workdir,
        lang=track,  # None = source transcript
        styles_path=plan.styles_path, fonts_dir=plan.fonts_dir,
        preset=plan.preset, position=plan.position,
        on_progress=progress("style"),
    )
    if plan.burn:
        from subtitle_studio.stages.render import run_render

        produced["render"] = run_render(
            plan.input_media, workdir, settings, target_lang,
            fonts_dir=plan.fonts_dir, on_progress=progress("render"),
        )
    return produced


def force_from(workdir: Path, stage: str) -> None:
    invalidate_from(workdir, stage, STAGE_ORDER)
