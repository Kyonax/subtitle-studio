"""The subtitle-studio TUI, nano-core HUD edition.

Three tabs. PIPELINE runs the numbered stages, each explained in plain words
with a live status badge and a "next" line that always says the current move.
TRANSCRIPT reads and fixes the text (enter edits, r renames the row's speaker).
STYLE selects a preset and a position from the central styles.toml and shows a
live preview that re-renders on selection changes and on styles.toml saves,
with z zoom (centered on the subtitle) and shift+arrows panning.

Design: the nano-core dashboard laws. #0a0a0a paper, #101010/#161616 surfaces,
1px hairlines #2a2a2a, text #ededed, muted #9a9a9a, dim #5a5a5a, status colors
ok #52e0a3 · warn #e0c052 · danger #e05252, no radius, lowercase mono labels.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Input,
    Label,
    OptionList,
    ProgressBar,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
)
from textual.widgets.option_list import Option
from rich.text import Text as RichText

try:  # probe BEFORE the app owns the terminal, else ghostty's pixel protocol is missed
    from textual_image.widget import Image as PreviewImage
except Exception:  # pragma: no cover
    PreviewImage = None

from subtitle_studio import paths
from subtitle_studio.config import load_settings
from subtitle_studio.schema import load_transcript, save_transcript
from subtitle_studio.subtitles.styleconf import ANCHORS

STAGE_HELP = [
    ("transcribe", "1 transcribe", "Turns the speech into timed text, word by word."),
    ("diarize", "2 diarize", "Detects who speaks when. Optional, needs the free HF token."),
    ("translate", "3 translate", "Rewrites the text in another language, offline. Set 'to' or swap."),
    ("style", "4 style", "Builds the subtitles from styles.toml, burn adds them into a new video."),
]

DONE = "[#52E0A3]● done[/]"
PENDING = "[#5A5A5A]○ pending[/]"
WORKING = "[#E0C052]◍ working[/]"

ZOOM_MODES = ["fit", "full"]


def _pixel_capable() -> bool:
    """True when the terminal can draw real pixels (kitty graphics or sixel)."""
    import os

    term = (os.environ.get("TERM", "") + " " + os.environ.get("TERM_PROGRAM", "")).lower()
    return any(name in term for name in ("kitty", "ghostty", "wezterm", "foot"))


class TextPrompt(ModalScreen[str | None]):
    """One-field modal used for text edits and renames."""

    CSS = """
    TextPrompt { align: center middle; }
    #dialog { width: 80%; max-width: 110; height: auto; border: solid #2A2A2A; padding: 1 2; background: #101010; }
    #dialog Label { color: #9A9A9A; }
    #dialog Input { background: #161616; color: #EDEDED; border: solid #2A2A2A; }
    #dialog Input:focus { border: solid #EDEDED; }
    #dialog Input>.input--cursor { background: #F9CD26; color: #0A0A0A; }
    #dialog Input>.input--selection { background: #4A3D0C; color: #FBFBFB; }
    #buttons { height: auto; align-horizontal: right; margin-top: 1; }
    #buttons Button { height: 1; border: none; background: #161616; color: #EDEDED; padding: 0 2; margin-left: 2; }
    #buttons Button:hover { color: #F9CD26; }
    """

    def __init__(self, title: str, initial: str = "") -> None:
        super().__init__()
        self._title = title
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._title)
            yield Input(value=self._initial, id="value", select_on_focus=False)
            with Horizontal(id="buttons"):
                yield Button("cancel", id="cancel")
                yield Button("save", id="save")

    def on_mount(self) -> None:
        field = self.query_one("#value", Input)
        field.styles.color = "#EDEDED"
        field.styles.background = "#161616"
        field.focus()
        field.cursor_position = len(field.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self.query_one("#value", Input).value if event.button.id == "save" else None)

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self.dismiss(self.query_one("#value", Input).value)


class StudioApp(App):
    TITLE = "SUBTITLE-STUDIO"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: #0A0A0A; color: #EDEDED; scrollbar-size: 1 1; }
    * { scrollbar-size-vertical: 1; scrollbar-size-horizontal: 1;
        scrollbar-color: #2A2A2A; scrollbar-background: #0A0A0A;
        scrollbar-color-hover: #EDEDED; scrollbar-color-active: #EDEDED; }
    Footer { background: #0A0A0A; color: #5A5A5A; }
    Footer > .footer--key { background: #0A0A0A; color: #EDEDED; }
    #hud-title { height: 1; padding: 0 1; }
    #next-hint { height: 1; padding: 0 1; color: #9A9A9A; }
    #activity-row { height: 1; padding: 0 1; display: none; }
    #activity-label { width: auto; min-width: 24; color: #E0C052; text-style: bold; }
    #activity-bar { width: 32; margin: 0 2; }
    #activity-bar Bar > .bar--bar { color: #F9CD26; background: #2A2A2A; }
    #activity-bar Bar > .bar--complete { color: #52E0A3; }
    #activity-bar PercentageStatus { color: #EDEDED; }
    #activity-detail { width: 1fr; color: #9A9A9A; }
    TabPane { padding: 0 1; }
    Tabs Tab { color: #5A5A5A; }
    Tabs Tab.-active { color: #EDEDED; text-style: bold; background: transparent; }
    Tabs Tab:hover { color: #EDEDED; }
    Underline > .underline--bar { color: #EDEDED; background: #2A2A2A; }

    .panel { border: solid #2A2A2A; border-title-color: #9A9A9A; padding: 0 1; }
    .hint { color: #5A5A5A; height: 1; }

    Checkbox > .toggle--button { color: #0A0A0A; background: #161616; }
    Checkbox.-on > .toggle--button { color: #52E0A3; background: #161616; }
    OptionList > .option-list--option-highlighted { background: #161616; color: #EDEDED; text-style: none; }
    OptionList:focus > .option-list--option-highlighted { background: #1E1E1E; color: #F9CD26; }

    #stages-panel { height: auto; }
    .stage-row { height: 1; }
    .stage-row Button { height: 1; width: 16; min-width: 16; border: none; padding: 0;
                        background: transparent; color: #EDEDED; text-style: bold;
                        content-align: left middle; text-align: left; }
    .stage-row Button:hover { background: #161616; color: #F9CD26; }
    .stage-desc { width: 1fr; color: #9A9A9A; }
    .stage-status { width: 10; text-align: right; }
    #options-row { height: 1; margin-top: 1; }
    #transcript-tools { height: 1; }
    .spacer { width: 1fr; }
    #options-row Label { color: #9A9A9A; padding: 0 1 0 0; }
    #options-row Input { width: 8; height: 1; border: none; padding: 0 1; background: #161616; }
    #options-row Checkbox { height: 1; border: none; background: transparent; padding: 0 1; }
    #options-row Checkbox:focus { background: #161616; }
    #btn-run-all { height: 1; width: auto; min-width: 16; border: none; padding: 0 2;
                   background: #161616; color: #F9CD26; text-style: bold; }
    #btn-run-all:hover { background: #F9CD26; color: #0A0A0A; }
    #log { height: 1fr; border: solid #2A2A2A; border-title-color: #9A9A9A; background: #101010; color: #9A9A9A; margin-top: 1; }

    DataTable { height: 1fr; background: #0A0A0A; }
    DataTable > .datatable--header { background: #0A0A0A; color: #9A9A9A; }
    DataTable > .datatable--cursor { background: #161616; }

    #style-left { width: 34; border: solid #2A2A2A; border-title-color: #9A9A9A; padding: 0 1; }
    #preset-list { height: auto; max-height: 12; border: none; background: transparent; }
    #style-right { width: 1fr; border: solid #2A2A2A; border-title-color: #9A9A9A; margin-left: 1; }
    #preview-slot { width: 100%; height: 100%; }
    #preview-slot Image { }
    #style-file { color: #5A5A5A; height: 1; }
    .style-btn { height: 1; width: auto; min-width: 6; border: none; padding: 0 1;
                 background: #161616; color: #EDEDED; margin-right: 1; }
    .style-btn:hover { color: #F9CD26; }
    #style-left Label { color: #9A9A9A; height: 1; }
    Select { border: none; height: 3; width: 26; }
    Select SelectCurrent { border: solid #2A2A2A; background: #101010; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("f5", "refresh", "Reload"),
        Binding("e", "edit_styles", "Edit styles.toml"),
        Binding("p", "preview_now", "Preview"),
        Binding("o", "open_preview", "Open preview"),
        Binding("z", "zoom", "Zoom"),
        Binding("w", "watch_window", "Watch window"),
        Binding("t", "relisten_selected", "Relisten seg"),
        Binding("R", "rerender", "Re-render"),
        Binding("question_mark", "help", "Help", key_display="?"),
        Binding("j", "vim('down')", "Down", show=False),
        Binding("down", "vim('down')", "Down", show=False),
        Binding("up", "vim('up')", "Up", show=False),
        Binding("k", "vim('up')", "Up", show=False),
        Binding("h", "vim('prev_tab')", "Prev tab", show=False),
        Binding("l", "vim('next_tab')", "Next tab", show=False),
        Binding("g", "vim('top')", "Top", show=False),
        Binding("G", "vim('bottom')", "Bottom", show=False),
        Binding("ctrl+d", "vim('half_down')", "Half down", show=False),
        Binding("ctrl+u", "vim('half_up')", "Half up", show=False),
        Binding("shift+up", "pan('up')", "Pan", show=False),
        Binding("shift+down", "pan('down')", "Pan", show=False),
        Binding("shift+left", "pan('left')", "Pan", show=False),
        Binding("shift+right", "pan('right')", "Pan", show=False),
    ]

    def __init__(self, input_media: Path | None = None) -> None:
        super().__init__()
        self.input_media = input_media
        self.settings = load_settings(None)
        self.workdir = paths.studio_dir(input_media) if input_media else None
        self._styles_mtime: float | None = None
        self._preview_timer = None
        self._preview_full: Path | None = None  # full-res render, crops derive from it
        self._last_preview: Path | None = None  # what is on screen (crop or full)
        self._zoom = 0  # index into ZOOM_MODES
        self._preview_seg_id: int | None = None  # preview renders THIS segment's moment
        self._last_preview_at: float | None = None  # frame time actually rendered
        self._busy: str | None = None  # label of the running stage, drives the spinner
        self._busy_detail: str = ""
        self._spin = 0
        self._watch_proc: subprocess.Popen | None = None
        self._auto_watch_done = False
        self._live_png = Path(tempfile.gettempdir()) / "subtitle-studio-live.png"

    # ---------- layout ----------

    def compose(self) -> ComposeResult:
        name = self.input_media.name if self.input_media else "style mode"
        yield Static(f"[bold #F9CD26]▮[/] [bold #EDEDED]subtitle-studio[/] [#5A5A5A]//[/] [#9A9A9A]{name}[/]", id="hud-title")
        yield Static("", id="next-hint")
        with Horizontal(id="activity-row"):
            yield Static("", id="activity-label")
            yield ProgressBar(total=100, show_eta=False, id="activity-bar")
            yield Static("", id="activity-detail")
        with TabbedContent():
            with TabPane("pipeline", id="tab-run"):
                with Vertical(id="stages-panel", classes="panel") as panel:
                    panel.border_title = "stages"
                    for stage_id, label, help_text in STAGE_HELP:
                        with Horizontal(classes="stage-row"):
                            yield Button(label, id=f"btn-{stage_id}")
                            yield Static(help_text, classes="stage-desc")
                            yield Static(PENDING, classes="stage-status", id=f"status-{stage_id}")
                with Horizontal(id="options-row"):
                    yield Label("to")
                    yield Input(placeholder="en", id="to-lang")
                    yield Checkbox("swap", id="chk-swap")
                    yield Checkbox("burn", id="chk-burn")
                    yield Checkbox("speakers", id="chk-diarize")
                    yield Static("", classes="spacer")
                    yield Button("▶ run pipeline", id="btn-run-all")
                log = RichLog(id="log", markup=True, wrap=True)
                log.border_title = "log"
                yield log
            with TabPane("transcript", id="tab-transcript"):
                yield Static("enter edit in your editor · p preview the selected row · r rename speaker · f5 reload", classes="hint")
                with Horizontal(id="transcript-tools"):
                    yield Button("↻ relisten segment", id="btn-relisten-seg", classes="style-btn")
                    yield Button("↻ relisten all", id="btn-relisten", classes="style-btn")
                    yield Static("segment = only the selected row's audio · all = the whole file, previous kept as .bak", classes="hint")
                yield DataTable(id="segments", cursor_type="row")
            with TabPane("style", id="tab-style"):
                with Horizontal():
                    with Vertical(id="style-left") as left:
                        left.border_title = "look"
                        yield Static("", id="style-file")
                        yield Label("preset")
                        yield OptionList(id="preset-list")
                        yield Label("position")
                        yield Select(((k, k) for k in ANCHORS), id="st-position", allow_blank=False, value="bottom-center")
                        with Horizontal():
                            yield Button("edit", id="btn-edit-styles", classes="style-btn")
                            yield Button("apply", id="btn-apply-style", classes="style-btn")
                        yield Static("file watched, saves refresh", classes="hint")
                        yield Static("z zoom · shift+arrows move · o full size", classes="hint")
                    with Vertical(id="style-right") as right:
                        right.border_title = "preview · fit"
                        with ScrollableContainer(id="preview-slot"):
                            yield Static("rendering preview…", id="preview-empty")
        yield Footer()

    # ---------- mount & refresh ----------

    def on_mount(self) -> None:
        table = self.query_one("#segments", DataTable)
        table.add_columns("start", "end", "speaker", "lang", "text")
        if self.input_media is None:
            self.log_line("[#E0C052]no video loaded[/] — pipeline is disabled, style works with sample text")
        self.action_refresh()
        self.set_interval(1.0, self._watch_styles)
        self.set_interval(0.15, self._tick_busy)
        self._schedule_preview()

    def action_refresh(self) -> None:
        self._load_styles_panel()
        self._refresh_statuses()
        if not self.workdir:
            return
        transcript_file = paths.transcript_path(self.workdir)
        table = self.query_one("#segments", DataTable)
        table.clear()
        if transcript_file.exists():
            transcript = load_transcript(transcript_file)
            for seg in transcript.segments:
                low_conf = any(w.score is not None and w.score < 0.5 for w in seg.words)
                text = f"[#E0C052]{seg.text}[/]" if low_conf else seg.text
                table.add_row(
                    f"{seg.start:7.2f}", f"{seg.end:7.2f}",
                    transcript.display_name(seg.speaker) or "-",
                    seg.language or "-", text,
                    key=str(seg.id),
                )

    def _translate_inputs(self, track: str) -> dict:
        from subtitle_studio.state import hash_file, hash_obj

        return {
            "transcript": hash_file(paths.transcript_path(self.workdir)),
            "config:translation": hash_obj(self.settings.translation.model_dump()),
            "to": track,
            "mode": "swap" if track == "swap" else "invert",
        }

    def _translate_state(self, track: str) -> str:
        """fresh | stale | missing — stale means the source transcript changed
        (an edit, a relisten) after this translation was made."""
        translated = paths.transcript_path(self.workdir, track)
        if not translated.exists():
            return "missing"
        from subtitle_studio.state import load_state, stage_fresh

        return (
            "fresh"
            if stage_fresh(load_state(self.workdir), f"translate:{track}", self._translate_inputs(track))
            else "stale"
        )

    def _track(self) -> str | None:
        if self.query_one("#chk-swap", Checkbox).value:
            return "swap"
        to_lang = self.query_one("#to-lang", Input).value.strip()
        return to_lang or None

    def _refresh_statuses(self) -> None:
        hint = self.query_one("#next-hint", Static)
        if not self.workdir:
            for stage_id, *_ in STAGE_HELP:
                self.query_one(f"#status-{stage_id}", Static).update("[#5A5A5A]—[/]")
            hint.update(RichText.from_markup("[#EDEDED]style mode ▸ [/]tweak styles.toml in your editor, the preview follows, o opens it full size"))
            return
        transcript_file = paths.transcript_path(self.workdir)
        has_transcript = transcript_file.exists()
        speakers_done = False
        source_lang = None
        if has_transcript:
            t = load_transcript(transcript_file)
            speakers_done = bool(t.speakers)
            source_lang = t.language
        track = self._track() or source_lang or "und"
        translate_state = self._translate_state(self._track()) if (self._track() and has_transcript) else "missing"
        states = {
            "transcribe": has_transcript,
            "diarize": speakers_done,
            "translate": translate_state == "fresh",
            "style": paths.subs_path(self.workdir, track).exists(),
        }
        for stage_id, done in states.items():
            self.query_one(f"#status-{stage_id}", Static).update(DONE if done else PENDING)
        if translate_state == "stale":
            self.query_one("#status-translate", Static).update("[#E0C052]◐ stale[/]")
        if not states["transcribe"]:
            hint.update(RichText.from_markup("[#EDEDED]next ▸ [/]press 1 transcribe, it makes the timed text everything else uses"))
        elif not states["style"]:
            hint.update(RichText.from_markup("[#EDEDED]next ▸ [/]2 and 3 are optional, press 4 style to build the subtitles, tick burn for a video"))
        else:
            hint.update(RichText.from_markup(f"[#EDEDED]done ▸ [/]files live in {self.workdir.name}, change styles.toml or translate and press 4 again"))

    def log_line(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)

    SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def _tick_busy(self) -> None:
        if self._busy is None:
            return
        self._spin = (self._spin + 1) % len(self.SPINNER)
        frame = self.SPINNER[self._spin]
        self.query_one("#activity-label", Static).update(f"{frame} {self._busy}")

    # ---------- stage workers ----------

    def _run_stage(self, stage_id: str, label: str, fn) -> None:
        self.query_one(f"#status-{stage_id}", Static).update(WORKING)
        self._busy = label
        self._busy_detail = "starting…"
        self.query_one("#activity-row").display = True
        self.query_one("#activity-detail", Static).update("starting…")
        self.query_one("#activity-bar", ProgressBar).update(total=100, progress=0)

        def work() -> None:
            try:
                result = fn()
                self.call_from_thread(self.log_line, f"[#52E0A3]ok[/] {result}")
            except Exception as exc:
                self.call_from_thread(self.log_line, f"[#E05252]error:[/] {exc}")
                self.call_from_thread(self.notify, str(exc), severity="error", timeout=6)
            finally:
                self._busy = None
                self._busy_detail = ""
                self.call_from_thread(self._hide_activity)
                self.call_from_thread(self.action_refresh)
                self.call_from_thread(self._schedule_preview)

        self.run_worker(work, thread=True, exclusive=True, group="stages", description=label)

    def _progress(self, stage: str):
        def cb(msg: str, frac: float) -> None:
            self._busy_detail = msg
            self.call_from_thread(self._set_activity, msg, frac)
            self.call_from_thread(self.log_line, f"[bold #EDEDED]{stage}[/] [#9A9A9A]{msg}[/]")

        return cb

    def _set_activity(self, msg: str, frac: float) -> None:
        self.query_one("#activity-detail", Static).update(msg)
        bar = self.query_one("#activity-bar", ProgressBar)
        bar.update(progress=max(0.0, min(frac, 1.0)) * 100)

    def _hide_activity(self) -> None:
        self.query_one("#activity-row").display = False

    def _preview_activity_done(self) -> None:
        if self._busy is None:  # a running stage owns the row otherwise
            self.query_one("#activity-row").display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id or ""
        if button == "btn-edit-styles":
            self.action_edit_styles()
            return
        if button == "btn-apply-style":
            self._apply_style()
            return
        if self.input_media is None or self.workdir is None:
            self.log_line("[#E0C052]load a video first:[/] subtitle-studio ui VIDEO")
            return
        media, workdir, settings = self.input_media, self.workdir, self.settings
        if button == "btn-transcribe":
            from subtitle_studio.stages.transcribe import run_transcribe

            self._run_stage("transcribe", "transcribe",
                            lambda: run_transcribe(media, workdir, settings, on_progress=self._progress("transcribe")))
        elif button == "btn-diarize":
            from subtitle_studio.stages.diarize import run_diarize

            self._run_stage("diarize", "diarize",
                            lambda: run_diarize(media, workdir, settings, on_progress=self._progress("diarize")))
        elif button == "btn-translate":
            from subtitle_studio.stages.translate import run_translate

            swap = self.query_one("#chk-swap", Checkbox).value
            to_lang = self.query_one("#to-lang", Input).value.strip() or None
            if not swap and not to_lang:
                self.log_line("[#E0C052]set 'to' (like en) or tick swap first[/]")
                return
            self._run_stage("translate", "translate",
                            lambda: run_translate(media, workdir, settings, to_lang, swap=swap,
                                                  on_progress=self._progress("translate")))
        elif button == "btn-relisten-seg":
            self.action_relisten_selected()
        elif button == "btn-relisten":
            from subtitle_studio.stages.transcribe import run_transcribe

            self.log_line("[#E0C052]relistening[/], the audio is transcribed again, previous transcript kept as .bak")
            self._run_stage("transcribe", "relisten",
                            lambda: run_transcribe(media, workdir, settings, on_progress=self._progress("transcribe")))
        elif button == "btn-style":
            self._apply_style()
        elif button == "btn-run-all":
            self._run_all()

    def _style_opts(self) -> tuple[str | None, str | None]:
        preset_list = self.query_one("#preset-list", OptionList)
        selected = preset_list.highlighted
        preset = None
        if selected is not None and preset_list.option_count:
            option = preset_list.get_option_at_index(selected)
            preset = None if option.id == "__default__" else option.id
        position = self.query_one("#st-position", Select).value or None
        return preset, position

    def _apply_style(self) -> None:
        if self.input_media is None or self.workdir is None:
            self.log_line("[#E0C052]no video loaded, the preview is the output here[/]")
            return
        from subtitle_studio.schema import load_transcript as load_t
        from subtitle_studio.stages.render import run_render
        from subtitle_studio.stages.style import resolve_fonts_dir, run_style

        media, workdir, settings = self.input_media, self.workdir, self.settings
        track = self._track()
        burn = self.query_one("#chk-burn", Checkbox).value
        fonts_dir = resolve_fonts_dir(settings.paths.fonts_dir)
        preset, position = self._style_opts()

        def work():
            if track:
                state = self._translate_state(track)
                if state != "fresh":
                    reason = "the source transcript changed" if state == "stale" else "no translation yet"
                    self.call_from_thread(
                        self.log_line, f"[#E0C052]translating first[/], {reason}, your edits flow into the {track} track"
                    )
                    from subtitle_studio.stages.translate import run_translate

                    run_translate(media, workdir, settings,
                                  None if track == "swap" else track, swap=(track == "swap"),
                                  on_progress=self._progress("translate"))
            subs = run_style(media, workdir, lang=track, fonts_dir=fonts_dir,
                             preset=preset, position=position, on_progress=self._progress("style"))
            if burn:
                lang = track or (load_t(paths.transcript_path(workdir)).language or "und")
                return run_render(media, workdir, settings, lang, fonts_dir=fonts_dir,
                                  on_progress=self._progress("render"))
            return subs

        self._run_stage("style", "style", work)

    def _run_all(self) -> None:
        from subtitle_studio.pipeline import RunPlan, run_pipeline
        from subtitle_studio.stages.style import resolve_fonts_dir

        media, workdir, settings = self.input_media, self.workdir, self.settings
        preset, position = self._style_opts()
        swap = self.query_one("#chk-swap", Checkbox).value
        plan = RunPlan(
            input_media=media, workdir=workdir, settings=settings,
            to_lang=None if swap else (self.query_one("#to-lang", Input).value.strip() or None),
            swap=swap,
            fonts_dir=resolve_fonts_dir(settings.paths.fonts_dir),
            preset=preset, position=position,
            burn=self.query_one("#chk-burn", Checkbox).value,
            skip_diarize=not self.query_one("#chk-diarize", Checkbox).value,
        )

        def work():
            produced = run_pipeline(plan, on_progress=lambda stage, msg, _f: self.call_from_thread(
                self.log_line, f"[bold #EDEDED]{stage}[/] [#9A9A9A]{msg}[/]"))
            return " · ".join(f"{k}: {v.name}" for k, v in produced.items())

        self._run_stage("style", "run all", work)

    def action_vim(self, motion: str) -> None:
        """Vim everywhere: j/k move in lists AND between controls, h/l switch
        tabs, g/G jump, typing in fields is never touched."""
        if motion in ("prev_tab", "next_tab"):
            tabs = self.query_one(TabbedContent)
            order = ["tab-run", "tab-transcript", "tab-style"]
            index = order.index(tabs.active) if tabs.active in order else 0
            tabs.active = order[(index + (1 if motion == "next_tab" else -1)) % len(order)]
            return
        focused = self.focused
        if isinstance(focused, DataTable):
            if motion == "up" and focused.cursor_row == 0:
                self.action_focus_previous()  # climb out of the table to the controls above
                return
            actions = {
                "down": focused.action_cursor_down, "up": focused.action_cursor_up,
                "top": lambda: focused.move_cursor(row=0),
                "bottom": lambda: focused.move_cursor(row=max(0, focused.row_count - 1)),
                "half_down": focused.action_page_down, "half_up": focused.action_page_up,
            }
        elif isinstance(focused, OptionList):
            at_top = (focused.highlighted or 0) == 0
            at_bottom = (focused.highlighted or 0) >= focused.option_count - 1
            if motion == "up" and at_top:
                self.action_focus_previous()
                return
            if motion == "down" and at_bottom:
                self.action_focus_next()  # continue down into position and the buttons
                return
            actions = {
                "down": focused.action_cursor_down, "up": focused.action_cursor_up,
                "top": focused.action_first, "bottom": focused.action_last,
                "half_down": focused.action_page_down, "half_up": focused.action_page_up,
            }
        else:
            # any other control (buttons, selects, checkboxes): j/k walk the tab
            if motion in ("down", "half_down"):
                self.action_focus_next()
            elif motion in ("up", "half_up"):
                self.action_focus_previous()
            return
        action = actions.get(motion)
        if action:
            action()

    # ---------- transcript editing ----------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "segments":
            self._edit_segment(str(event.row_key.value))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "segments" and event.row_key is not None:
            try:
                self._preview_seg_id = int(str(event.row_key.value))
            except (TypeError, ValueError):
                return

    def _selected_segment_id(self) -> int | None:
        table = self.query_one("#segments", DataTable)
        if not table.row_count:
            return None
        try:
            return int(str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value))
        except (TypeError, ValueError):
            return None

    def action_relisten_selected(self) -> None:
        if self.input_media is None:
            self.log_line("[#E0C052]load a video first[/]")
            return
        seg_id = self._selected_segment_id()
        if seg_id is None:
            self.log_line("[#E0C052]no transcript rows yet, run 1 transcribe first[/]")
            return
        self._relisten_segment(seg_id)

    def on_key(self, event) -> None:
        focused = self.focused
        if event.key == "r" and isinstance(focused, DataTable) and focused.id == "segments" and focused.row_count:
            seg_id = str(focused.coordinate_to_cell_key(focused.cursor_coordinate).row_key.value)
            transcript = load_transcript(paths.transcript_path(self.workdir))
            seg = next(s for s in transcript.segments if str(s.id) == seg_id)
            if seg.speaker:
                self._rename_speaker(seg.speaker)
            else:
                self.log_line("[#E0C052]this row has no speaker, run 2 diarize first[/]")

    def _relisten_segment(self, seg_id: int) -> None:
        from subtitle_studio.stages.transcribe import relisten_segment

        media, workdir, settings = self.input_media, self.workdir, self.settings
        self._preview_seg_id = seg_id
        self.log_line(f"[#E0C052]relistening segment {seg_id}[/], only that audio range is heard again")
        self._run_stage(
            "transcribe", f"relistening segment {seg_id}",
            lambda: relisten_segment(media, workdir, settings, seg_id, on_progress=self._progress("relisten")),
        )

    def _edit_segment(self, seg_id: str) -> None:
        transcript_file = paths.transcript_path(self.workdir)
        transcript = load_transcript(transcript_file)
        seg = next(s for s in transcript.segments if str(s.id) == seg_id)

        def apply(new_text: str) -> None:
            new_text = " ".join(new_text.split())
            if not new_text or new_text == seg.text:
                return
            seg.text = new_text
            from subtitle_studio.schema import retime_words

            seg.words = retime_words(seg, new_text)
            save_transcript(transcript, transcript_file)
            self.log_line(f"[#52E0A3]edited[/] segment {seg.id}")
            self._preview_seg_id = seg.id
            self.action_refresh()
            self._schedule_preview(now=True)

        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if editor is None:
            import shutil

            for candidate in ("nvim", "vim", "nano"):
                if shutil.which(candidate):
                    editor = candidate
                    break
        if editor is None or self.is_headless:
            def done(value: str | None) -> None:
                if value is not None:
                    apply(value)

            self.push_screen(TextPrompt(f"edit segment {seg.id}", seg.text), done)
            return

        tmp = Path(tempfile.gettempdir()) / f"subtitle-studio-segment-{seg.id}.txt"
        tmp.write_text(seg.text + "\n", encoding="utf-8")
        with self.suspend():
            subprocess.run([*shlex.split(editor), str(tmp)])
        try:
            apply(tmp.read_text(encoding="utf-8"))
        finally:
            tmp.unlink(missing_ok=True)

    def _rename_speaker(self, speaker_id: str) -> None:
        from subtitle_studio.speakers import rename_speaker

        def done(value: str | None) -> None:
            if not value:
                return
            rename_speaker(self.workdir, speaker_id, value)
            self.log_line(f"[#52E0A3]renamed[/] {speaker_id} -> {value!r}")
            self.action_refresh()

        self.push_screen(TextPrompt(f"rename {speaker_id}", ""), done)

    # ---------- style selection & live preview ----------

    def _styles_file(self) -> Path | None:
        from subtitle_studio.stages.style import resolve_styles_path

        return resolve_styles_path(None, self.input_media)

    def _load_styles_panel(self) -> None:
        import tomllib

        styles_file = self._styles_file()
        label = self.query_one("#style-file", Static)
        preset_list = self.query_one("#preset-list", OptionList)
        highlighted = preset_list.highlighted
        preset_list.clear_options()
        names: list[str] = []
        if styles_file is None:
            label.update("no styles.toml found, built-in defaults")
        else:
            label.update(f"…/{styles_file.parent.name}/{styles_file.name}")
            with open(styles_file, "rb") as f:
                names = sorted(tomllib.load(f).get("style", {}))
        preset_list.add_options([Option("(default)", id="__default__")] +
                                [Option(n, id=n) for n in names])
        preset_list.highlighted = highlighted if highlighted is not None and highlighted < preset_list.option_count else 0
        self._styles_mtime = styles_file.stat().st_mtime if styles_file else None

    def _watch_styles(self) -> None:
        styles_file = self._styles_file()
        mtime = styles_file.stat().st_mtime if styles_file else None
        if mtime != self._styles_mtime:
            self._styles_mtime = mtime
            self.log_line("[#EDEDED]styles.toml changed[/], reloading")
            self._load_styles_panel()
            self._schedule_preview()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "preset-list":
            self._schedule_preview()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "st-position":
            self._schedule_preview()

    def action_rerender(self) -> None:
        """styles.toml changed: rebuild the subtitles (and the video when burn is
        ticked) for the current track with the freshest styles, then preview."""
        if self.input_media is None:
            self.log_line("[#E0C052]no video loaded[/], the preview already follows styles.toml saves")
            self._schedule_preview(now=True)
            return
        self._load_styles_panel()
        self.log_line("[#EDEDED]re-rendering[/] with the current styles.toml")
        self._apply_style()

    def action_preview_now(self) -> None:
        target = f"segment {self._preview_seg_id}" if self._preview_seg_id is not None else "the current look"
        self.log_line(f"[#EDEDED]rendering preview[/] of {target}")
        self._schedule_preview(now=True)

    def action_edit_styles(self) -> None:
        styles_file = self._styles_file()
        if styles_file is None:
            self.log_line("[#E0C052]no styles.toml to edit yet[/]")
            return
        subprocess.Popen(["xdg-open", str(styles_file)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        self.log_line(f"[#EDEDED]opened[/] {styles_file}")

    def action_open_preview(self) -> None:
        png = self._preview_full or self._last_preview
        if png is None or not png.exists():
            self.log_line("[#E0C052]no preview rendered yet[/]")
            return
        subprocess.Popen(["xdg-open", str(png)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        self.log_line(f"[#EDEDED]opened[/] {png}")

    # ----- zoom: fit <-> full native size, moving = scrolling the container -----

    def action_zoom(self) -> None:
        self._zoom = (self._zoom + 1) % len(ZOOM_MODES)
        self._update_preview_title()
        self._remount_preview()

    def action_pan(self, direction: str) -> None:
        if ZOOM_MODES[self._zoom] != "full":
            self.log_line("[#5A5A5A]press z for full size first, then shift+arrows or the mouse wheel move[/]")
            return
        slot = self.query_one("#preview-slot", ScrollableContainer)
        dx, dy = {"left": (-12, 0), "right": (12, 0), "up": (0, -6), "down": (0, 6)}[direction]
        slot.scroll_relative(x=dx, y=dy, animate=False)

    def _anchor_focus(self) -> tuple[float, float]:
        """Normalized (x, y) of the subtitle anchor, full-size opens there."""
        position = self.query_one("#st-position", Select).value or "bottom-center"
        col = {"left": 0.18, "center": 0.5, "right": 0.82}
        row = {"bottom": 0.95, "middle": 0.5, "top": 0.05}
        if position == "center":
            return 0.5, 0.5
        vert, _, horiz = position.partition("-")
        return col.get(horiz, 0.5), row.get(vert, 0.95)

    def _update_preview_title(self) -> None:
        panel = self.query_one("#style-right", Vertical)
        mode = ZOOM_MODES[self._zoom]
        panel.border_title = "preview · fit" if mode == "fit" else "preview · full size, scroll to move"

    def _scroll_to_anchor(self) -> None:
        slot = self.query_one("#preview-slot", ScrollableContainer)
        fx, fy = self._anchor_focus()
        slot.scroll_to(x=fx * slot.max_scroll_x, y=fy * slot.max_scroll_y, animate=False)

    def _remount_preview(self) -> None:
        png = self._preview_full
        if png is None or not png.exists():
            return
        self._last_preview = png
        self._mirror_live(png)
        self._maybe_auto_watch()
        slot = self.query_one("#preview-slot", ScrollableContainer)
        slot.remove_children()
        if PreviewImage is None:
            slot.mount(Static(f"preview written to {png}, press o to open it"))
            return
        image = PreviewImage(png)
        if ZOOM_MODES[self._zoom] == "fit":
            image.styles.width = "100%"
            image.styles.height = "100%"
        # full: natural size, the container scrolls over the ORIGINAL pixels
        slot.mount(image)
        if ZOOM_MODES[self._zoom] == "full":
            self.call_after_refresh(self._scroll_to_anchor)

    def _schedule_preview(self, now: bool = False) -> None:
        if self._preview_timer is not None:
            self._preview_timer.stop()
        self._preview_timer = self.set_timer(0.05 if now else 0.5, self._refresh_preview)

    def _refresh_preview(self) -> None:
        from subtitle_studio.stages.style import resolve_fonts_dir

        fonts_dir = resolve_fonts_dir(self.settings.paths.fonts_dir)
        preset, position = self._style_opts()
        media, workdir = self.input_media, self.workdir
        have_transcript = workdir is not None and paths.transcript_path(workdir).exists()
        if self._busy is None:
            self.query_one("#activity-row").display = True
            self.query_one("#activity-label", Static).update("◍ rendering preview")
            self.query_one("#activity-detail", Static).update(
                f"segment {self._preview_seg_id}" if (have_transcript and self._preview_seg_id is not None) else "sample text"
            )
            self.query_one("#activity-bar", ProgressBar).update(total=None)

        def work():
            try:
                if have_transcript:
                    from subtitle_studio.stages.render import escape_filter_path
                    from subtitle_studio.stages.style import run_style

                    subs = run_style(media, workdir, fonts_dir=fonts_dir, preset=preset, position=position)
                    transcript = load_transcript(paths.transcript_path(workdir))
                    target = next((sg for sg in transcript.segments if sg.id == self._preview_seg_id), None)
                    if target is None and transcript.segments:
                        target = transcript.segments[0]
                    at = (target.start + target.end) / 2 if target else 1.0
                    if target is not None:
                        # the frame must show THIS row's text: aim at the midpoint of the
                        # row's FIRST on-screen chunk, computed with the same layout laws
                        from subtitle_studio.stages.style import resolve_styles_path
                        from subtitle_studio.subtitles.layout import segment_events
                        from subtitle_studio.subtitles.styleconf import load_styles

                        styles_cfg = load_styles(resolve_styles_path(None, media))
                        _, eff = styles_cfg.resolve(
                            target.speaker, transcript.display_name(target.speaker),
                            preset or styles_cfg.default_preset,
                        )
                        events = segment_events(target, eff.max_line_chars, eff.max_lines, eff.max_words)
                        if events:
                            at = (events[0].start + events[0].end) / 2
                    self._last_preview_at = at
                    out = Path(tempfile.gettempdir()) / "subtitle-studio-preview.png"
                    vf = f"ass={escape_filter_path(subs)}" + (f":fontsdir={escape_filter_path(fonts_dir)}" if fonts_dir else "")
                    subprocess.run(
                        ["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-copyts", "-i", str(media),
                         "-vf", vf, "-frames:v", "1", str(out)],
                        check=True, capture_output=True, stdin=subprocess.DEVNULL,
                    )
                else:
                    from subtitle_studio.preview import render_style_preview
                    from subtitle_studio.stages.style import resolve_styles_path

                    out = render_style_preview(resolve_styles_path(None, media),
                                               preset=preset, position=position, fonts_dir=fonts_dir)
                self._preview_full = out
                self.call_from_thread(self._remount_preview)
                stamp = f" at {self._last_preview_at:.2f}s" if self._last_preview_at is not None else ""
                self.call_from_thread(
                    self.log_line,
                    "[#52E0A3]preview updated[/] "
                    + (f"segment {self._preview_seg_id}{stamp}" if have_transcript and self._preview_seg_id is not None else "(sample text)"),
                )
            except Exception as exc:
                self.call_from_thread(self.log_line, f"[#E05252]preview error:[/] {exc}")
            finally:
                self.call_from_thread(self._preview_activity_done)

        self.run_worker(work, thread=True, exclusive=True, group="preview", description="preview")


    # ----- full-quality live window (imv auto-refreshed on every preview) -----

    def _mirror_live(self, png: Path) -> None:
        import shutil

        try:
            shutil.copyfile(png, self._live_png)
        except OSError:
            return
        if self._watch_proc is not None and self._watch_proc.poll() is None:
            pid = str(self._watch_proc.pid)
            for command in (["close"], ["open", str(self._live_png)]):
                subprocess.run(["imv-msg", pid, *command], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _maybe_auto_watch(self) -> None:
        """No pixel graphics in this terminal: open the full-quality window alone."""
        import shutil

        if self._auto_watch_done or self.is_headless or _pixel_capable():
            return
        if self._watch_proc is not None and self._watch_proc.poll() is None:
            return
        if shutil.which("imv-wayland") is None and shutil.which("imv") is None:
            return
        self._auto_watch_done = True
        self.log_line("[#E0C052]this terminal cannot draw real pixels[/], opening the full-quality watch window")
        self.action_watch_window()

    def action_watch_window(self) -> None:
        import shutil

        if self._watch_proc is not None and self._watch_proc.poll() is None:
            self.log_line("[#9A9A9A]watch window already open[/]")
            return
        source = self._last_preview or self._preview_full
        if source is None or not source.exists():
            self.log_line("[#E0C052]no preview yet, it renders first[/]")
            return
        shutil.copyfile(source, self._live_png)
        viewer = shutil.which("imv-wayland") or shutil.which("imv")
        if viewer is None:
            subprocess.Popen(["xdg-open", str(self._live_png)], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            self.log_line("[#E0C052]imv not found[/], opened once without live refresh")
            return
        self._watch_proc = subprocess.Popen([viewer, str(self._live_png)], stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            start_new_session=True)
        self.log_line("[#52E0A3]watch window open[/], full quality, refreshes with every preview")

    def action_help(self) -> None:
        self.push_screen(HelpScreen())



class HelpScreen(ModalScreen[None]):
    """All keybindings on one card, any key closes it."""

    CSS = """
    HelpScreen { align: center middle; }
    #help-card { width: 74; height: auto; border: solid #2A2A2A; border-title-color: #9A9A9A;
                 padding: 1 2; background: #101010; }
    .help-section { height: 1; color: #EDEDED; text-style: bold; margin-top: 1; }
    .help-row { height: 1; }
    .help-key { width: 16; color: #F9CD26; }
    .help-desc { width: 1fr; color: #9A9A9A; }
    .help-close { height: 1; color: #5A5A5A; margin-top: 1; }
    """

    SECTIONS = [
        ("everywhere", [
            ("q", "quit"),
            ("f5", "reload the tables and the styles file"),
            ("j / k", "move in lists AND walk between controls, no tab key needed"),
            ("h / l", "previous / next tab"),
            ("g / G", "jump to top / bottom"),
            ("ctrl+d / ctrl+u", "half page down / up"),
            ("?", "this help"),
        ]),
        ("pipeline · 1 to 4 in order, 2 and 3 are optional", [
            ("click a stage", "runs that stage"),
            ("▶ run pipeline", "runs everything with that row's options"),
        ]),
        ("transcript", [
            ("enter", "open the row's text in your editor, save+quit applies"),
            ("r", "rename the speaker of the selected row"),
            ("t", "relisten ONLY the selected segment (same as ↻ relisten segment)"),
            ("p", "preview the SELECTED row, rendering is only on ask"),
            ("↻ relisten", "re-transcribe everything from the audio"),
        ]),
        ("style · preset list and position drive the preview live", [
            ("e", "edit styles.toml, saves refresh the preview"),
            ("p", "render the preview now"),
            ("z", "zoom fit / 2x / 3x, centered on the subtitle"),
            ("shift+arrows", "move around while zoomed"),
            ("R", "re-render subs (and video with burn) after styles.toml changes"),
            ("w", "watch window, full quality, live refresh"),
            ("o", "open the current preview once"),
        ]),
    ]

    def compose(self) -> ComposeResult:
        card = Vertical(id="help-card")
        card.border_title = "keys"
        with card:
            for section, rows in self.SECTIONS:
                yield Static(section, classes="help-section")
                for key, desc in rows:
                    with Horizontal(classes="help-row"):
                        yield Static(key, classes="help-key")
                        yield Static(desc, classes="help-desc")
            yield Static("press any key to close", classes="help-close")

    def on_key(self, _event) -> None:
        self.dismiss(None)


def launch(input_media: Path | None) -> None:
    StudioApp(input_media).run()
