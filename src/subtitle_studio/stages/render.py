"""Stage 6: burn the ASS sidecar into a new video (NVENC encode, audio copied)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from subtitle_studio import paths
from subtitle_studio.config import Settings
from subtitle_studio.stages.extract import FfmpegError, probe_media
from subtitle_studio.state import hash_file, hash_obj, record_stage

ProgressFn = Callable[[str, float], None]

# x264/x265 name their presets; NVENC uses p1..p7. A config carrying one
# family's name must not be handed to the other -- ffmpeg rejects it outright.
X26X_PRESETS = {
    "ultrafast", "superfast", "veryfast", "faster", "fast",
    "medium", "slow", "slower", "veryslow", "placebo",
}
DEFAULT_X26X_PRESET = "slow"


def _preset_for(codec: str, preset: str) -> str:
    if codec.endswith("_nvenc"):
        return preset if preset.startswith("p") else "p5"
    return preset if preset in X26X_PRESETS else DEFAULT_X26X_PRESET


def escape_filter_path(path: str | Path) -> str:
    r"""Escape a path for use inside an ffmpeg filtergraph argument.

    Filtergraph parsing eats `\`, `'`, `:`, `,`, `;`, `[`, `]` — the classic
    source of "No such file" bugs on real-world filenames.
    """
    out = str(path)
    for ch in ("\\", "'", ":", ",", ";", "[", "]"):
        out = out.replace(ch, "\\" + ch)
    return out


def run_render(
    input_media: Path,
    workdir: Path,
    settings: Settings,
    lang: str,
    fonts_dir: Path | None = None,
    on_progress: ProgressFn | None = None,
    subs: Path | None = None,
) -> Path:
    """Burn one subtitle document into the picture.

    `subs` overrides which document is burned, which is how the all-languages
    export works: it passes combined.ass, the same bytes the preview rendered,
    so every language is painted in at once with its own [track.<lang>] look.
    """
    subs = subs or paths.subs_path(workdir, lang)
    if not subs.exists():
        raise FileNotFoundError(f"{subs} not found — run `subtitle-studio style` first")
    out = paths.render_path(workdir, lang)

    vf = f"ass={escape_filter_path(subs)}"
    if fonts_dir:
        vf += f":fontsdir={escape_filter_path(fonts_dir)}"

    render = settings.render
    cmd = [
        "ffmpeg", "-y", "-i", str(input_media),
        "-vf", vf,
        "-c:v", render.codec, "-pix_fmt", render.pix_fmt,
        *(["-preset", _preset_for(render.codec, render.preset),
           "-rc", "vbr", "-cq", str(render.cq), "-b:v", "0"]
          if render.codec.endswith("_nvenc")
          else ["-preset", _preset_for(render.codec, render.preset), "-crf", str(render.cq)]),
        "-c:a", "copy", "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        str(out),
    ]

    duration = probe_media(input_media)["duration_s"] or 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL)
    assert proc.stdout is not None
    for line in proc.stdout:
        if on_progress and line.startswith("out_time_us=") and duration:
            try:
                done = int(line.split("=", 1)[1]) / 1_000_000 / duration
            except ValueError:
                continue
            on_progress("rendering", min(done, 1.0))
    proc.wait()
    if proc.returncode != 0:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise FfmpegError(f"ffmpeg render failed: {stderr.strip().splitlines()[-1:]}")

    record_stage(
        workdir,
        f"render:{lang}",
        {"subs": hash_file(subs), "input": hash_file(input_media), "config:render": hash_obj(render.model_dump())},
    )
    if on_progress:
        on_progress("render done", 1.0)
    return out
