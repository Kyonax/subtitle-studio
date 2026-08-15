"""`subtitle-studio models pull` — pre-download the large model caches explicitly
so the first real run isn't a surprise multi-GB download.

Whisper CT2 weights + wav2vec2 alignment models land in the HuggingFace/torch
caches; pyannote (Phase 2) and MADLAD (Phase 4) add their own pullers here.
"""

from __future__ import annotations

from rich.console import Console

from subtitle_studio.config import Settings

ALIGN_PULL_LANGS = ["en", "es"]


def pull_asr(settings: Settings, console: Console) -> None:
    from faster_whisper.utils import download_model

    console.print(f"[bold]whisper[/bold] {settings.asr.model} (CTranslate2 weights, ~3.1GB for large-v3)")
    download_model(settings.asr.model)
    console.print("  [green]ok[/green]")

    import whisperx

    from subtitle_studio.asr.whisperx_engine import ALIGN_MODEL_OVERRIDES

    for lang in ALIGN_PULL_LANGS:
        name = ALIGN_MODEL_OVERRIDES.get(lang, "whisperx default")
        console.print(f"[bold]alignment[/bold] {lang}: {name}")
        model, _meta = whisperx.load_align_model(
            language_code=lang, device="cpu", model_name=ALIGN_MODEL_OVERRIDES.get(lang)
        )
        del model
        console.print("  [green]ok[/green]")


def pull_diarize(settings: Settings, console: Console) -> None:
    from subtitle_studio.stages.diarize import DiarizationAuthError, _load_pipeline

    console.print(f"[bold]diarization[/bold] {settings.diarization.model} (gated — needs HF_TOKEN)")
    try:
        pipeline = _load_pipeline(settings)
        del pipeline
        console.print("  [green]ok[/green]")
    except DiarizationAuthError as exc:
        console.print(f"  [yellow]skipped:[/yellow] {exc}")


def pull_translate(settings: Settings, console: Console) -> None:
    from subtitle_studio.langid import ensure_lid_model
    from subtitle_studio.translate.madlad import CT2_REPO, MadladProvider

    console.print("[bold]language-id[/bold] fasttext lid.176 (<1MB)")
    ensure_lid_model()
    console.print("  [green]ok[/green]")
    console.print(f"[bold]translation[/bold] {CT2_REPO} (~3GB)")
    MadladProvider(settings).ensure_model()
    console.print("  [green]ok[/green]")


PULLERS = {"asr": pull_asr, "diarize": pull_diarize, "translate": pull_translate}


def pull(component: str, settings: Settings, console: Console) -> None:
    if component == "all":
        for fn in PULLERS.values():
            fn(settings, console)
        return
    if component not in PULLERS:
        raise ValueError(f"unknown component {component!r} (expected asr | diarize | translate | all)")
    PULLERS[component](settings, console)
