"""Font resolution: libass matches by *family name*, not filename, so we read the
real family name out of each font file with fontTools and resolve config values
against family names AND filename stems.

Two catalogues feed a style: the fonts bundled in `fonts/`, which travel with the
project, and whatever fontconfig knows about on this machine. libass reads both,
so both are offered and both resolve -- a name in neither is still a hard error,
because a typo that silently falls back to a default look is the worse failure."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

FONT_EXTS = {".ttf", ".otf", ".ttc"}
_FAMILY_ID, _FULL_NAME_ID = 1, 4

# Aliases fontconfig resolves itself; they name no file, so no catalogue lists
# them and they must never be mistaken for a typo.
GENERIC_FAMILIES = {"sans-serif", "sans serif", "serif", "monospace", "cursive", "fantasy", "system-ui"}


@dataclass
class FontEntry:
    path: Path
    family: str


class FontNotFoundError(ValueError):
    pass


def scan_fonts(fonts_dir: Path | None) -> list[FontEntry]:
    if fonts_dir is None or not fonts_dir.is_dir():
        return []
    from fontTools.ttLib import TTFont

    entries = []
    for path in sorted(fonts_dir.iterdir()):
        if path.suffix.lower() not in FONT_EXTS:
            continue
        try:
            font = TTFont(path, fontNumber=0, lazy=True)
            name = font["name"].getDebugName(_FAMILY_ID) or path.stem
            font.close()
        except Exception:
            name = path.stem
        entries.append(FontEntry(path=path, family=name))
    return entries


_system_cache: list[str] | None = None


def system_fonts(refresh: bool = False) -> list[str]:
    """Family names fontconfig can serve, sorted, deduped.

    `fc-list : family` prints one line per face with the family and its aliases
    comma-separated, so the same family arrives many times over. Absent
    fontconfig (or a failure of it) is not an error: the bundled fonts still
    work and the picker simply has less to offer."""
    global _system_cache
    if _system_cache is not None and not refresh:
        return _system_cache

    families: set[str] = set()
    if shutil.which("fc-list"):
        try:
            out = subprocess.run(
                ["fc-list", ":", "family"],
                capture_output=True,
                text=True,
                timeout=10,
                stdin=subprocess.DEVNULL,
                check=False,
            ).stdout
            for line in out.splitlines():
                for alias in line.split(","):
                    name = alias.strip()
                    if name:
                        families.add(name)
        except (OSError, subprocess.SubprocessError):
            families = set()

    _system_cache = sorted(families, key=str.casefold)
    return _system_cache


def available_fonts(fonts_dir: Path | None) -> list[dict]:
    """Everything selectable, bundled first -> [{family, source}].

    Bundled families win the dedupe: they are the copy that ships with the
    project, so that is the one a style should name."""
    seen: set[str] = set()
    catalogue: list[dict] = []
    for entry in scan_fonts(fonts_dir):
        key = entry.family.casefold()
        if key not in seen:
            seen.add(key)
            catalogue.append({"family": entry.family, "source": "bundled"})
    for family in system_fonts():
        if family.casefold() not in seen:
            seen.add(family.casefold())
            catalogue.append({"family": family, "source": "system"})
    return catalogue


_measure_cache: dict[str, tuple] = {}


def _font_metrics(family_or_stem: str, fonts_dir: Path | None):
    """-> (advances_by_codepoint, units_per_em, ascent, descent) or None."""
    key = f"{fonts_dir}:{family_or_stem}"
    if key in _measure_cache:
        return _measure_cache[key]
    result = None
    want = family_or_stem.casefold()
    for entry in scan_fonts(fonts_dir):
        if entry.family.casefold() == want or entry.path.stem.casefold() == want:
            from fontTools.ttLib import TTFont

            font = TTFont(entry.path, fontNumber=0, lazy=True)
            try:
                upem = font["head"].unitsPerEm
                hhea = font["hhea"]
                cmap = font.getBestCmap()
                hmtx = font["hmtx"]
                advances = {cp: hmtx[glyph][0] for cp, glyph in cmap.items()}
                result = (advances, upem, hhea.ascent, hhea.descent)
            finally:
                font.close()
            break
    _measure_cache[key] = result
    return result


def measure_line(text: str, family: str, size: int, letter_spacing: float, fonts_dir: Path | None) -> float:
    """Pixel width of one subtitle line at `size` — real glyph advances when the
    font file is available, a 0.52em average fallback otherwise."""
    metrics = _font_metrics(family, fonts_dir)
    if metrics is None:
        width = len(text) * size * 0.52
    else:
        advances, upem, _asc, _desc = metrics
        average = sum(advances.values()) / max(len(advances), 1)
        units = sum(advances.get(ord(ch), average) for ch in text)
        width = units * size / upem
    return width + letter_spacing * max(len(text) - 1, 0)


def line_height(family: str, size: int, fonts_dir: Path | None) -> float:
    metrics = _font_metrics(family, fonts_dir)
    if metrics is None:
        return size * 1.2
    _advances, upem, asc, desc = metrics
    return (asc - desc) * size / upem


def resolve_font(requested: str, fonts_dir: Path | None) -> str:
    """-> the family name to put in the ASS Style line.

    Matches family name or filename stem (case-insensitive) inside fonts_dir
    first, then any family fontconfig can serve -- libass reads both, so both
    are legitimate answers and the picker offers both. Generic CSS aliases pass
    through for fontconfig to resolve.

    Unmatched names pass through unchanged ONLY if no fonts dir is configured
    (system font fallback); with a fonts dir present, unknown names are a hard
    error, because a typo silently falling back to a default look is the
    failure this guard exists to prevent."""
    entries = scan_fonts(fonts_dir)
    want = requested.casefold()
    for e in entries:
        if e.family.casefold() == want or e.path.stem.casefold() == want:
            return e.family
    installed = system_fonts()
    for family in installed:
        if family.casefold() == want:
            return family
    if want in GENERIC_FAMILIES or not entries:
        return requested

    bundled = ", ".join(sorted({e.family for e in entries}))
    raise FontNotFoundError(
        f"font {requested!r} not found in {fonts_dir} — available families: {bundled}"
        + (f"; nor among the {len(installed)} installed on this system" if installed else "")
    )
