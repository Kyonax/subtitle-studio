"""The subtitle-studio command surface.

Every command is a thin wrapper over a stages/* function that reads and writes
files in the per-job `<input>.studio/` directory, so stages are individually
invokable, resumable, and shared verbatim with the TUI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from subtitle_studio import __version__, paths
from subtitle_studio.config import load_settings

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich", help="Local transcription, diarization & styled subtitles.")
speakers_app = typer.Typer(no_args_is_help=True, help="Inspect and rename diarized speakers.")
app.add_typer(speakers_app, name="speakers")
console = Console()

ConfigOpt = typer.Option(None, "--config", help="Extra config.toml merged over ~/.config/subtitle-studio/config.toml")
OutOpt = typer.Option(None, "--out", help="Work directory (default: <input>.studio/ next to the input)")


def _version(value: bool) -> None:
    if value:
        console.print(f"subtitle-studio {__version__}")
        raise typer.Exit()


@app.callback()
def main(version: bool = typer.Option(False, "--version", callback=_version, is_eager=True)) -> None:
    pass


def _todo(phase: str) -> None:
    console.print(f"[yellow]Not implemented yet — lands in {phase}.[/yellow]")
    raise typer.Exit(code=2)


@app.command()
def extract(input: Path = typer.Argument(..., exists=True, dir_okay=False), out: Optional[Path] = OutOpt) -> None:
    """Extract mono 16 kHz audio from INPUT into the work directory."""
    from subtitle_studio.stages.extract import run_extract

    workdir = paths.studio_dir(input, out)
    audio = run_extract(input, workdir, on_progress=lambda msg, _: console.print(f"  {msg}"))
    console.print(f"[green]ok[/green] {audio}")


@app.command()
def transcribe(
    input: Path = typer.Argument(..., exists=True, dir_okay=False),
    language: Optional[str] = typer.Option(None, "--language", help="auto (default) | es | en | ..."),
    model: Optional[str] = typer.Option(None, "--model"),
    batch: Optional[int] = typer.Option(None, "--batch"),
    out: Optional[Path] = OutOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """High-accuracy speech-to-text with word-level timestamps -> transcript.json."""
    from subtitle_studio.stages.transcribe import run_transcribe

    settings = load_settings(config)
    if model:
        settings.asr.model = model
    workdir = paths.studio_dir(input, out)
    lang = None if language in (None, "auto") else language
    result = run_transcribe(
        input, workdir, settings,
        language=lang, batch_size=batch,
        on_progress=lambda msg, _: console.print(f"  {msg}"),
    )
    console.print(f"[green]ok[/green] {result}")


@app.command()
def diarize(
    input: Path = typer.Argument(..., exists=True, dir_okay=False),
    min_speakers: Optional[int] = typer.Option(None, "--min-speakers"),
    max_speakers: Optional[int] = typer.Option(None, "--max-speakers"),
    out: Optional[Path] = OutOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Assign speakers to transcript segments/words (pyannote)."""
    from subtitle_studio.stages.diarize import run_diarize

    workdir = paths.studio_dir(input, out)
    result = run_diarize(
        input, workdir, load_settings(config),
        min_speakers=min_speakers, max_speakers=max_speakers,
        on_progress=lambda msg, _: console.print(f"  {msg}"),
    )
    console.print(f"[green]ok[/green] {result}")


@speakers_app.command("list")
def speakers_list(input: Path = typer.Argument(..., exists=True, dir_okay=False), out: Optional[Path] = OutOpt) -> None:
    """List speaker ids, names and talk time."""
    from rich.table import Table

    from subtitle_studio.speakers import list_speakers

    table = Table("id", "name", "segments", "talk time")
    for row in list_speakers(paths.studio_dir(input, out)):
        table.add_row(row.speaker_id, row.name or "[dim]unnamed[/dim]", str(row.segments), f"{row.talk_time_s}s")
    console.print(table)


@speakers_app.command("rename")
def speakers_rename(
    input: Path = typer.Argument(..., exists=True, dir_okay=False),
    speaker_id: str = typer.Argument(..., help="e.g. SPEAKER_00"),
    name: str = typer.Argument(..., help='display name, e.g. "María"'),
    out: Optional[Path] = OutOpt,
) -> None:
    """Map a diarized speaker id to a real name (propagates to translated variants)."""
    from subtitle_studio.speakers import rename_speaker

    touched = rename_speaker(paths.studio_dir(input, out), speaker_id, name)
    for path in touched:
        console.print(f"[green]ok[/green] {speaker_id} -> {name!r} in {path.name}")


@app.command()
def translate(
    input: Path = typer.Argument(..., exists=True, dir_okay=False),
    to: Optional[str] = typer.Option(None, "--to", help="unify: target language code, e.g. en, pt, fr"),
    swap: bool = typer.Option(False, "--swap", help="cross a two-language video: every segment translated to the OTHER language"),
    all: bool = typer.Option(False, "--all", help="with --to: translate every segment, even ones already in the target"),
    provider: Optional[str] = typer.Option(None, "--provider"),
    device: Optional[str] = typer.Option(None, "--device", help="cuda | cpu"),
    out: Optional[Path] = OutOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Translate the transcript. --to LANG unifies into one language (segments
    already in it pass through); --swap crosses a bilingual video (EN speech gets
    ES subs and vice versa) into the `swap` track."""
    from subtitle_studio.stages.translate import run_translate

    if bool(to) == swap:
        console.print("[red]pass exactly one of --to LANG or --swap[/red]")
        raise typer.Exit(code=2)
    settings = load_settings(config)
    if provider:
        settings.translation.provider = provider
    if device:
        settings.translation.device = device
    result = run_translate(
        input, paths.studio_dir(input, out), settings, to, translate_all=all, swap=swap,
        on_progress=lambda msg, _: console.print(f"  {msg}"),
    )
    console.print(f"[green]ok[/green] {result}")


@app.command()
def styles(
    input: Optional[Path] = typer.Argument(None, exists=True, dir_okay=False, help="video: also consider a styles.toml next to it"),
    styles_file: Optional[Path] = typer.Option(None, "--styles", help="explicit styles.toml"),
) -> None:
    """Show which styles.toml is in effect and the presets it configures."""
    from rich.table import Table

    from subtitle_studio.stages.style import resolve_styles_path
    from subtitle_studio.subtitles.styleconf import load_styles

    resolved = resolve_styles_path(styles_file, input)
    if resolved is None:
        console.print("[yellow]no styles.toml found — built-in defaults apply[/yellow]")
        return
    config = load_styles(resolved)
    console.print(f"styles file: [bold]{resolved}[/bold]")
    if config.default_preset:
        console.print(f"default preset (meta): [bold]{config.default_preset}[/bold]")
    table = Table("preset", "changes")
    table.add_row("(default)", "the [default] base look")
    for name in config.preset_names():
        table.add_row(name, ", ".join(sorted(config.presets[name])))
    console.print(table)
    if config.speaker:
        console.print(f"speaker overrides: {', '.join(sorted(config.speaker))}")
    console.print("use with: [bold]--preset NAME[/bold] on style/run, or the TUI dropdown")


@app.command()
def preview(
    preset: Optional[str] = typer.Option(None, "--preset", help="named [style.NAME] preset to preview"),
    position: Optional[str] = typer.Option(None, "--position", help="anchor or 'x,y'"),
    text: Optional[str] = typer.Option(None, "--text", help="sample text to render"),
    res: str = typer.Option("1920x1080", "--res", help="preview frame size WxH"),
    styles_file: Optional[Path] = typer.Option(None, "--styles", help="explicit styles.toml"),
    out: Optional[Path] = typer.Option(None, "--out", help="output PNG (default: temp file)"),
    open_it: bool = typer.Option(False, "--open", help="open the PNG when done"),
) -> None:
    """Render the current style on sample text over a neutral backdrop, no video needed."""
    from subtitle_studio.preview import SAMPLE_TEXT, render_style_preview
    from subtitle_studio.stages.style import resolve_fonts_dir, resolve_styles_path

    settings = load_settings(None)
    resolved = resolve_styles_path(styles_file, None)
    w, _, h = res.lower().partition("x")
    png = render_style_preview(
        resolved, preset=preset, position=position,
        text=text or SAMPLE_TEXT, width=int(w), height=int(h),
        out_png=out, fonts_dir=resolve_fonts_dir(settings.paths.fonts_dir),
    )
    console.print(f"styles file: {resolved or 'built-in defaults'}")
    console.print(f"[green]ok[/green] {png}")
    if open_it:
        import subprocess

        subprocess.Popen(["xdg-open", str(png)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


@app.command()
def languages(input: Path = typer.Argument(..., exists=True, dir_okay=False), out: Optional[Path] = OutOpt) -> None:
    """Per-segment language report for a transcribed video."""
    from rich.table import Table

    from subtitle_studio.langid import annotate_segments
    from subtitle_studio.schema import load_transcript, save_transcript

    transcript_file = paths.transcript_path(paths.studio_dir(input, out))
    transcript = load_transcript(transcript_file)
    talk_time = annotate_segments(transcript)
    save_transcript(transcript, transcript_file)

    table = Table("language", "segments", "talk time")
    for lang, seconds in sorted(talk_time.items(), key=lambda kv: -kv[1]):
        count = sum(1 for s in transcript.segments if s.language == lang)
        table.add_row(lang, str(count), f"{seconds}s")
    console.print(table)
    console.print(f"file-level language: [bold]{transcript.language}[/bold]")


@app.command()
def style(
    input: Path = typer.Argument(..., exists=True, dir_okay=False),
    lang: Optional[str] = typer.Option(None, "--lang", help="translated variant to style (default: source)"),
    styles: Optional[Path] = typer.Option(None, "--styles", help="styles.toml (default: ./styles.toml)"),
    preset: Optional[str] = typer.Option(None, "--preset", help="named [style.NAME] preset from the styles.toml"),
    position: Optional[str] = typer.Option(None, "--position", help="anchor (bottom-center, top-left, ...) or 'x,y'"),
    out: Optional[Path] = OutOpt,
) -> None:
    """Generate the styled ASS sidecar from transcript JSON + styles.toml."""
    from subtitle_studio.stages.style import resolve_fonts_dir, run_style

    settings = load_settings(None)
    if lang:
        from subtitle_studio.state import hash_file, hash_obj, load_state, stage_fresh

        workdir_check = paths.studio_dir(input, out)
        inputs = {
            "transcript": hash_file(paths.transcript_path(workdir_check)),
            "config:translation": hash_obj(settings.translation.model_dump()),
            "to": lang,
            "mode": "swap" if lang == "swap" else "invert",
        }
        if not stage_fresh(load_state(workdir_check), f"translate:{lang}", inputs):
            console.print(
                f"[yellow]warning:[/yellow] the source transcript changed after the {lang} translation, "
                f"run [bold]translate[/bold] again so your edits reach it"
            )
    result = run_style(
        input, paths.studio_dir(input, out),
        lang=lang, styles_path=styles, preset=preset, position=position,
        fonts_dir=resolve_fonts_dir(settings.paths.fonts_dir),
        on_progress=lambda msg, _: console.print(f"  {msg}"),
    )
    console.print(f"[green]ok[/green] {result}")


@app.command()
def render(
    input: Path = typer.Argument(..., exists=True, dir_okay=False),
    lang: Optional[str] = typer.Option(None, "--lang"),
    codec: Optional[str] = typer.Option(None, "--codec"),
    cq: Optional[int] = typer.Option(None, "--cq"),
    out: Optional[Path] = OutOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Burn the styled subtitles into a new video (NVENC)."""
    from subtitle_studio.schema import load_transcript
    from subtitle_studio.stages.render import run_render
    from subtitle_studio.stages.style import resolve_fonts_dir

    settings = load_settings(config)
    if codec:
        settings.render.codec = codec
    if cq is not None:
        settings.render.cq = cq
    workdir = paths.studio_dir(input, out)
    target = lang or (load_transcript(paths.transcript_path(workdir)).language or "und")
    result = run_render(
        input, workdir, settings, target,
        fonts_dir=resolve_fonts_dir(settings.paths.fonts_dir),
        on_progress=lambda msg, frac: console.print(f"  {msg} {frac:.0%}") if frac in (0.0, 1.0) else None,
    )
    console.print(f"[green]ok[/green] {result}")


@app.command()
def run(
    input: Path = typer.Argument(..., exists=True, dir_okay=False),
    to: Optional[str] = typer.Option(None, "--to", help="also translate to this language"),
    swap: bool = typer.Option(False, "--swap", help="cross a two-language video (each part subtitled in the other language)"),
    styles: Optional[Path] = typer.Option(None, "--styles"),
    preset: Optional[str] = typer.Option(None, "--preset", help="named [style.NAME] preset from the styles.toml"),
    position: Optional[str] = typer.Option(None, "--position", help="anchor (bottom-center, top-left, ...) or 'x,y'"),
    burn: bool = typer.Option(False, "--burn", help="also render the burn-in video"),
    force: Optional[str] = typer.Option(None, "--force", help="re-run from this stage onward"),
    no_diarize: bool = typer.Option(False, "--no-diarize", help="skip speaker identification"),
    out: Optional[Path] = OutOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Full pipeline: extract -> transcribe -> diarize [-> translate] -> style [-> render], skipping fresh stages."""
    from subtitle_studio.pipeline import RunPlan, force_from, run_pipeline
    from subtitle_studio.stages.style import resolve_fonts_dir

    settings = load_settings(config)
    workdir = paths.studio_dir(input, out)
    if force:
        force_from(workdir, force)
    plan = RunPlan(
        input_media=input, workdir=workdir, settings=settings,
        to_lang=to, swap=swap, styles_path=styles, preset=preset, position=position,
        fonts_dir=resolve_fonts_dir(settings.paths.fonts_dir),
        burn=burn,
        skip_diarize=no_diarize,
    )
    produced = run_pipeline(plan, on_progress=lambda stage, msg, _: console.print(f"[bold]{stage}[/bold]  {msg}"))
    for stage, path in produced.items():
        console.print(f"[green]ok[/green] {stage}: {path}")


@app.command()
def models(
    component: str = typer.Argument("all", help="asr | diarize | translate | all"),
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Pre-download the (large) model caches with progress."""
    from subtitle_studio.models_pull import pull

    pull(component, load_settings(config), console)


@app.command()
def ui(input: Optional[Path] = typer.Argument(None, exists=True, dir_okay=False)) -> None:
    """Launch the Textual TUI."""
    from subtitle_studio.tui.app import launch

    launch(input)


if __name__ == "__main__":
    app()
