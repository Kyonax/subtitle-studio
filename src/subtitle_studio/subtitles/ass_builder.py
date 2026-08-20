"""Transcript JSON + styles.toml -> a complete .ass document.

Square background boxes use libass BorderStyle 3/4 (cheap). Rounded backgrounds
and glow are LAYERED events: a `{\\p1}` rounded-rect drawing (layer 0, sized by
measuring the real font's glyph advances), an optional blurred glow copy of the
text (layer 1), and the crisp text (layer 2) — all pinned with explicit \\pos so
libass collision handling never shifts one layer away from another.
"""

from __future__ import annotations

from pathlib import Path

from subtitle_studio.schema import Transcript
from subtitle_studio.subtitles.colors import parse_hex, to_ass
from subtitle_studio.subtitles.fonts import line_height, measure_line, resolve_font
from subtitle_studio.subtitles.layout import Event, segment_events
from subtitle_studio.subtitles.styleconf import StyleDef, StylesConfig

STYLE_FORMAT = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
    "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
)
EVENT_FORMAT = "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"

TRANSPARENT = "&HFF000000"


def _timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("{", r"\{").replace("}", r"\}")


def _fmt_num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _alpha_tag(color: str) -> str:
    """ASS inline alpha override for a #RRGGBB[AA] color."""
    *_rgb, a = parse_hex(color)
    return f"&H{255 - a:02X}&"


def _color_tag(color: str) -> str:
    """ASS inline color override (BGR, no alpha) for \\1c/\\3c."""
    r, g, b, _a = parse_hex(color)
    return f"&H{b:02X}{g:02X}{r:02X}&"


def _style_line(name: str, style: StyleDef, fonts_dir: Path | None) -> str:
    family = resolve_font(style.font, fonts_dir)
    bg = style.background
    shadow_offset = style.shadow.offset if style.shadow.enabled else 0.0
    if bg.enabled and bg.rounded:
        # box drawn separately -> the text keeps its real stroke
        border_style, outline = 1, style.stroke.effective_width()
        outline_color = to_ass(style.stroke.color)
        back_color = to_ass(style.shadow.color) if style.shadow.enabled else TRANSPARENT
    elif bg.enabled and bg.mode == "box":
        border_style, outline = 4, float(bg.padding.x)
        outline_color, back_color = TRANSPARENT, to_ass(bg.color)
        shadow_offset = 0.0
    elif bg.enabled:
        border_style, outline = 3, float(bg.padding.x)
        outline_color, back_color = to_ass(bg.color), to_ass(bg.color)
        shadow_offset = 0.0
    else:
        border_style, outline = 1, style.stroke.effective_width()
        outline_color = to_ass(style.stroke.color)
        back_color = to_ass(style.shadow.color) if style.shadow.enabled else TRANSPARENT
    fields = [
        name, family, str(style.size),
        to_ass(style.color), "&H000000FF", outline_color, back_color,
        "-1" if style.bold else "0", "-1" if style.italic else "0", "0", "0",
        str(style.scale_x), str(style.scale_y), _fmt_num(style.letter_spacing), "0",
        str(border_style), _fmt_num(outline), _fmt_num(shadow_offset),
        str(style.alignment()),
        str(style.margin.left), str(style.margin.right), str(style.margin.vertical), "1",
    ]
    return "Style: " + ",".join(fields)


def play_res(transcript: Transcript, styles: StylesConfig) -> tuple[int, int]:
    if isinstance(styles.play_res, list) and len(styles.play_res) == 2:
        return int(styles.play_res[0]), int(styles.play_res[1])
    video = transcript.source.video
    if video:
        return video.width, video.height
    return 1920, 1080


def _anchor_point(style: StyleDef, res_x: int, res_y: int) -> tuple[float, float]:
    """The \\pos point for this style's alignment + margins."""
    pos = style.pos_override()
    if pos:
        return float(pos[0]), float(pos[1])
    an = style.alignment()
    col = (an - 1) % 3  # 0 left, 1 center, 2 right
    row = (an - 1) // 3  # 0 bottom, 1 middle, 2 top
    x = {0: float(style.margin.left), 1: res_x / 2, 2: float(res_x - style.margin.right)}[col]
    y = {0: float(res_y - style.margin.vertical), 1: res_y / 2, 2: float(style.margin.vertical)}[row]
    return x, y


def _rounded_rect_path(w: float, h: float, radius: float) -> str:
    r = max(1.0, min(radius, w / 2, h / 2))
    # The origin corner is written literally as `0` in the path below, so only
    # the far corner needs naming.
    x1, y1 = w, h
    f = _fmt_num
    return (
        f"m {f(r)} 0 "
        f"l {f(x1 - r)} 0 b {f(x1)} 0 {f(x1)} 0 {f(x1)} {f(r)} "
        f"l {f(x1)} {f(y1 - r)} b {f(x1)} {f(y1)} {f(x1)} {f(y1)} {f(x1 - r)} {f(y1)} "
        f"l {f(r)} {f(y1)} b 0 {f(y1)} 0 {f(y1)} 0 {f(y1 - r)} "
        f"l 0 {f(r)} b 0 0 0 0 {f(r)} 0"
    )


class _Block:
    """Geometry of one on-screen subtitle block (text + optional drawn box)."""

    def __init__(self, style: StyleDef, event: Event, fonts_dir: Path | None, res: tuple[int, int]):
        self.style = style
        self.event = event
        family = resolve_font(style.font, fonts_dir)
        self.lines = [line.upper() for line in event.lines] if style.uppercase else event.lines
        widths = [
            measure_line(line, family, style.size, style.letter_spacing, fonts_dir) * style.scale_x / 100
            for line in self.lines
        ] or [0.0]
        self.text_w = max(widths)
        self.line_h = line_height(family, style.size, fonts_dir) * style.scale_y / 100
        self.text_h = self.line_h * max(len(self.lines), 1)
        self.anchor = _anchor_point(style, *res)
        self.y_shift = 0.0  # stacking offset applied when events overlap in time

    def needs_pos(self) -> bool:
        bg = self.style.background
        return (bg.enabled and bg.rounded) or self.style.glow.enabled or self.style.pos_override() is not None

    def pos(self) -> tuple[float, float]:
        x, y = self.anchor
        return x, y + self.y_shift

    def box_geometry(self) -> tuple[float, float, float, float]:
        """-> (left, top, width, height) of the background box."""
        pad = self.style.background.padding
        w = self.text_w + 2 * pad.x
        h = self.text_h + 2 * pad.y
        x, y = self.pos()
        an = self.style.alignment()
        col, row = (an - 1) % 3, (an - 1) // 3
        left = {0: x - pad.x, 1: x - w / 2, 2: x + pad.x - w}[col]
        top = {0: y - self.text_h - pad.y, 1: y - self.text_h / 2 - pad.y, 2: y - pad.y}[row]
        return left, top, w, h

    def block_height(self) -> float:
        pad = self.style.background.padding
        return self.text_h + (2 * pad.y if self.style.background.enabled else 0) + 6


def build_ass(
    transcript: Transcript,
    styles: StylesConfig,
    fonts_dir: Path | None,
    preset: str | None = None,
) -> str:
    res = play_res(transcript, styles)
    res_x, res_y = res

    # Styles: Default (base+preset) + one per speaker override key in the config.
    base = styles.base(preset)
    style_lines = [_style_line("Default", base, fonts_dir)]
    speaker_styles: dict[str, tuple[str, StyleDef]] = {}
    for speaker_id in transcript.speakers:
        display = transcript.display_name(speaker_id)
        name, style = styles.resolve(speaker_id, display, preset)
        if name != "Default":
            speaker_styles[speaker_id] = (name, style)
    seen: set[str] = set()
    for name, style in speaker_styles.values():
        if name not in seen:
            seen.add(name)
            style_lines.append(_style_line(name, style, fonts_dir))

    # Blocks in start order, with deterministic stacking for time-overlaps.
    blocks: list[tuple[str, _Block]] = []
    for segment in transcript.segments:
        style_name, style = speaker_styles.get(segment.speaker, ("Default", base))
        for event in segment_events(segment, style.max_line_chars, style.max_lines, style.max_words):
            blocks.append((style_name, _Block(style, event, fonts_dir, res)))
    blocks.sort(key=lambda item: item[1].event.start)

    dialogue_lines: list[str] = []
    for i, (style_name, block) in enumerate(blocks):
        margin_v = 0
        for prev_name, prev in blocks[:i]:
            overlaps = prev.event.end > block.event.start and prev.event.start < block.event.end
            if not (overlaps and prev.style.alignment() == block.style.alignment()):
                continue
            if block.needs_pos():
                row = (block.style.alignment() - 1) // 3
                block.y_shift += -prev.block_height() if row == 0 else prev.block_height()
            else:
                margin_v = block.style.margin.vertical + int(prev.block_height()) * len(prev.lines)

        start, end = _timestamp(block.event.start), _timestamp(block.event.end)
        speaker_name = transcript.display_name(block.event.speaker) or ""
        text_body = r"\N".join(_escape(line) for line in block.lines)
        pos_tag = ""
        if block.needs_pos():
            x, y = block.pos()
            pos_tag = f"{{\\pos({_fmt_num(round(x, 1))},{_fmt_num(round(y, 1))})}}"

        bg = block.style.background
        if bg.enabled and bg.rounded:
            left, top, w, h = block.box_geometry()
            box_tags = (
                f"{{\\an7\\pos({_fmt_num(round(left, 1))},{_fmt_num(round(top, 1))})"
                f"\\1c{_color_tag(bg.color)}\\1a{_alpha_tag(bg.color)}"
                f"\\bord0\\shad0\\p1}}"
            )
            dialogue_lines.append(
                f"Dialogue: 0,{start},{end},{style_name},{speaker_name}-box,0,0,0,,"
                f"{box_tags}{_rounded_rect_path(w, h, bg.radius)}"
            )

        glow = block.style.glow
        if glow.enabled:
            glow_tags = (
                f"{pos_tag}{{\\bord{_fmt_num(block.style.stroke.effective_width() + glow.size)}"
                f"\\3c{_color_tag(glow.color)}\\3a{_alpha_tag(glow.color)}"
                f"\\1a&HFF&\\blur{_fmt_num(glow.radius)}\\shad0}}"
            )
            dialogue_lines.append(
                f"Dialogue: 1,{start},{end},{style_name},{speaker_name}-glow,0,0,0,,"
                f"{glow_tags}{text_body}"
            )

        dialogue_lines.append(
            f"Dialogue: 2,{start},{end},{style_name},{speaker_name},0,0,{margin_v},,{pos_tag}{text_body}"
        )

    return "\n".join(
        [
            "[Script Info]",
            "; Generated by subtitle-studio",
            "ScriptType: v4.00+",
            f"PlayResX: {res_x}",
            f"PlayResY: {res_y}",
            "ScaledBorderAndShadow: yes",
            "WrapStyle: 2",
            "Collisions: Normal",
            "",
            "[V4+ Styles]",
            STYLE_FORMAT,
            *style_lines,
            "",
            "[Events]",
            EVENT_FORMAT,
            *dialogue_lines,
            "",
        ]
    )
