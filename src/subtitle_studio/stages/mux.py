"""Stage 7: put every subtitle track INTO the video, switchable.

Burning paints one language into the picture forever. Muxing carries all of
them as selectable tracks the player switches between, which is what a
multi-language video actually wants. Matroska is the container because it
stores ASS verbatim — every box, glow and position survives — and because the
streams are copied, not re-encoded: a 100 MB video is done in seconds with no
quality loss.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from subtitle_studio import paths
from subtitle_studio.stages.extract import FfmpegError
from subtitle_studio.state import hash_file, record_stage

ProgressFn = Callable[[str, float], None]

# ISO 639-1 -> 639-2/B, the codes players read. Anything unknown is passed
# through untouched: ffmpeg accepts it and the title still names the track.
ISO_639_2 = {
    "ar": "ara", "ca": "cat", "cs": "ces", "da": "dan", "de": "deu", "el": "ell",
    "en": "eng", "es": "spa", "eu": "eus", "fa": "fas", "fi": "fin", "fr": "fra",
    "gl": "glg", "he": "heb", "hi": "hin", "hu": "hun", "id": "ind", "it": "ita",
    "ja": "jpn", "ko": "kor", "nl": "nld", "no": "nor", "pl": "pol", "pt": "por",
    "ro": "ron", "ru": "rus", "sv": "swe", "th": "tha", "tr": "tur", "uk": "ukr",
    "vi": "vie", "zh": "zho",
}
SWAP_TAG = "mul"  # "multiple languages", the honest tag for a crossed track


def language_tag(track: str) -> str:
    if track == "swap":
        return SWAP_TAG
    return ISO_639_2.get(track.lower(), track.lower())


def track_title(track: str) -> str:
    return "bilingual cross" if track == "swap" else track


def available_subtitles(workdir: Path) -> list[tuple[str, Path]]:
    """(track, .ass file) for every subtitle built in this work directory."""
    found = []
    for candidate in sorted(workdir.glob("subs.*.ass")):
        track = candidate.name[len("subs.") : -len(".ass")]
        found.append((track, candidate))
    return found


def build_mux_command(input_media: Path, subtitles: list[tuple[str, Path]], out: Path) -> list[str]:
    """The ffmpeg call, built on its own so the mapping is testable without
    running anything: video and audio copied from the source, one subtitle
    stream per track, each tagged with its language and named for the picker."""
    command = ["ffmpeg", "-y", "-v", "error", "-i", str(input_media)]
    for _, ass in subtitles:
        command += ["-i", str(ass)]

    command += ["-map", "0:v:0", "-map", "0:a?"]
    for index in range(len(subtitles)):
        command += ["-map", f"{index + 1}:0"]

    command += ["-c:v", "copy", "-c:a", "copy", "-c:s", "copy"]
    for index, (track, _) in enumerate(subtitles):
        command += [
            f"-metadata:s:s:{index}", f"language={language_tag(track)}",
            f"-metadata:s:s:{index}", f"title={track_title(track)}",
        ]
    if subtitles:
        command += ["-disposition:s:0", "default"]
    command += [str(out)]
    return command


def run_mux(
    input_media: Path,
    workdir: Path,
    tracks: list[str] | None = None,
    out_file: Path | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Write one video carrying every requested subtitle track."""
    subtitles = available_subtitles(workdir)
    if tracks:
        wanted = list(dict.fromkeys(tracks))  # keep the caller's order, drop repeats
        by_track = dict(subtitles)
        missing = [track for track in wanted if track not in by_track]
        if missing:
            raise FileNotFoundError(
                f"no subtitles built for {', '.join(missing)} — build them first"
            )
        subtitles = [(track, by_track[track]) for track in wanted]
    if not subtitles:
        raise FileNotFoundError(f"no subs.*.ass in {workdir} — build subtitles first")

    out = out_file or paths.muxed_path(workdir)
    if on_progress:
        names = ", ".join(track for track, _ in subtitles)
        on_progress(f"putting {len(subtitles)} subtitle track(s) into the video ({names})", 0.2)

    result = subprocess.run(
        build_mux_command(input_media, subtitles, out),
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        tail = result.stderr.strip().splitlines()[-1:] or ["ffmpeg error"]
        raise FfmpegError(f"mux failed: {tail[0]}")

    record_stage(
        workdir,
        "mux",
        {
            "input": str(input_media),
            "tracks": ",".join(track for track, _ in subtitles),
            **{f"subs:{track}": hash_file(ass) for track, ass in subtitles},
        },
    )
    if on_progress:
        on_progress(f"video written with {len(subtitles)} switchable track(s)", 1.0)
    return out
