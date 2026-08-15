"""Stage 1: extract mono 16 kHz PCM audio from the input media with ffmpeg."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from subtitle_studio import paths
from subtitle_studio.state import hash_file, record_stage

ProgressFn = Callable[[str, float], None]  # (message, fraction 0..1)


class FfmpegError(RuntimeError):
    pass


def probe_media(input_media: Path) -> dict:
    """ffprobe the input: duration plus video stream geometry if present."""
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(input_media),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise FfmpegError(f"ffprobe failed on {input_media}: {proc.stderr.strip()}")
    info = json.loads(proc.stdout)
    result: dict = {"duration_s": float(info.get("format", {}).get("duration", 0)) or None, "video": None}
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video" and stream.get("disposition", {}).get("attached_pic", 0) != 1:
            num, _, den = (stream.get("avg_frame_rate") or "0/1").partition("/")
            fps = float(num) / float(den) if den and float(den) else 0.0
            result["video"] = {"width": stream["width"], "height": stream["height"], "fps": round(fps, 3)}
            break
    return result


def run_extract(input_media: Path, workdir: Path, on_progress: ProgressFn | None = None) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    out = paths.audio_path(workdir)
    if on_progress:
        on_progress(f"extracting audio -> {out.name}", 0.0)
    cmd = [
        "ffmpeg", "-y", "-i", str(input_media),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise FfmpegError(f"ffmpeg audio extraction failed: {proc.stderr.strip().splitlines()[-1:]}")
    record_stage(workdir, "extract", {"input": hash_file(input_media)})
    if on_progress:
        on_progress("audio extracted", 1.0)
    return out
