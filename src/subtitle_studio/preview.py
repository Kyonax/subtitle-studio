"""Style preview without a video: sample text styled by the resolved styles.toml,
rendered over a neutral gradient into one PNG. Judge a look before any pipeline run."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from subtitle_studio.schema import Segment, SourceInfo, Transcript, VideoInfo
from subtitle_studio.stages.extract import FfmpegError
from subtitle_studio.stages.render import escape_filter_path
from subtitle_studio.subtitles.ass_builder import build_ass
from subtitle_studio.subtitles.styleconf import parse_position
from subtitle_studio.subtitles.styleconf import load_styles

SAMPLE_TEXT = "Así se ven los subtítulos con este estilo, this is how your subtitles look."
BACKDROP = "gradients=s={w}x{h}:c0=0x1A2432:c1=0x46586E:x0=0:y0=0:x1={w}:y1={h}:d=1"


def render_style_preview(
    styles_path: Path | None,
    preset: str | None = None,
    position: str | None = None,
    text: str = SAMPLE_TEXT,
    width: int = 1920,
    height: int = 1080,
    out_png: Path | None = None,
    fonts_dir: Path | None = None,
) -> Path:
    styles = load_styles(styles_path)
    preset = preset or styles.default_preset
    if position:
        styles.default = styles.default.model_copy(update={"position": parse_position(position)})

    # trim the sample to ONE full subtitle under the active limits, so the
    # preview always shows a complete subtitle exactly as configured
    effective = styles.base(preset)
    cap_chars = effective.max_line_chars * effective.max_lines
    words = text.split()
    cap_words = effective.max_words if effective.max_words > 0 else len(words)
    kept: list[str] = []
    for word in words:
        candidate = " ".join(kept + [word])
        if kept and (len(candidate) > cap_chars or len(kept) >= cap_words):
            break
        kept.append(word)
    text = " ".join(kept)

    transcript = Transcript(
        source=SourceInfo(media_path="preview", video=VideoInfo(width=width, height=height, fps=30)),
        language="und",
        segments=[Segment(id=0, start=0.0, end=1.0, text=text)],
    )
    document = build_ass(transcript, styles, fonts_dir, preset=preset)

    out = out_png or Path(tempfile.gettempdir()) / "subtitle-studio-style-preview.png"
    with tempfile.NamedTemporaryFile("w", suffix=".ass", delete=False, encoding="utf-8") as f:
        f.write(document)
        ass_path = Path(f.name)
    try:
        vf = f"ass={escape_filter_path(ass_path)}"
        if fonts_dir:
            vf += f":fontsdir={escape_filter_path(fonts_dir)}"
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", BACKDROP.format(w=width, h=height),
            "-vf", vf, "-frames:v", "1", str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if proc.returncode != 0:
            raise FfmpegError(f"preview render failed: {proc.stderr.strip().splitlines()[-1:]}")
    finally:
        ass_path.unlink(missing_ok=True)
    return out
