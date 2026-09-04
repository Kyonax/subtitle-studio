"""styles.toml parsing: base style, named presets, per-track and per-speaker overrides.

Resolution order (later wins):
    [default] <- [style.<preset>] <- [track.<lang>] <- [speaker.<key>]

The track layer is what lets one video carry several languages at once without
them fighting over one look: `[track.es]` restyles the Spanish subtitle and
touches nothing else, so moving it, recolouring it or shrinking it leaves the
English exactly where it was.

Position intentionally does NOT live in the TOML — it comes from the CLI/TUI
(`--position`), though per-track and per-speaker `position` overrides are still
honored, and a per-track one is the normal way to keep two languages off each
other on the frame.
"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

# named anchor -> ASS numpad Alignment
ANCHORS = {
    "bottom-left": 1, "bottom-center": 2, "bottom-right": 3,
    "middle-left": 4, "center": 5, "middle-right": 6,
    "top-left": 7, "top-center": 8, "top-right": 9,
}
DEFAULT_POSITION = "bottom-center"

# A track style is addressed by one key or an ordered several: the ROLE the
# track plays ("source" / "translated") then its language, so a rule can be
# written for the role and still overridden for one language.
TrackKey = Sequence[str] | str | None


class Stroke(BaseModel):
    enabled: bool = True
    color: str = "#000000"
    width: float = 3.0

    def effective_width(self) -> float:
        return self.width if self.enabled else 0.0


class Glow(BaseModel):
    enabled: bool = False
    color: str = "#00D5FF"
    radius: float = 6.0   # blur radius of the glow layer
    size: float = 2.0     # extra outline thickness feeding the glow


class Shadow(BaseModel):
    enabled: bool = False
    color: str = "#000000AA"
    offset: float = 2.0


class Padding(BaseModel):
    x: int = 12
    y: int = 8


class Background(BaseModel):
    enabled: bool = True
    color: str = "#000000AA"
    padding: Padding = Field(default_factory=Padding)
    rounded: bool = False
    radius: float = 16.0  # corner radius when rounded
    mode: str = "box"     # box | opaque-per-line (square modes)

    @field_validator("padding", mode="before")
    @classmethod
    def _int_padding_shorthand(cls, value):
        if isinstance(value, int):
            return {"x": value, "y": max(2, int(value * 0.66))}
        return value


class Margin(BaseModel):
    left: int = 80
    right: int = 80
    vertical: int = 60


class StyleDef(BaseModel):
    font: str = "sans-serif"
    size: int = 56
    color: str = "#FFFFFF"
    bold: bool = False
    italic: bool = False
    uppercase: bool = False
    # Subtitle house style drops the full stop that ends a sentence: the cut to
    # the next card already says the sentence ended, so the dot is noise. Only a
    # single trailing "." goes — "?", "!" and "..." carry meaning and stay.
    end_period: bool = False
    letter_spacing: float = 0.0  # px between glyphs (ASS Spacing)
    scale_x: int = 100
    scale_y: int = 100
    stroke: Stroke = Field(default_factory=Stroke)
    glow: Glow = Field(default_factory=Glow)
    shadow: Shadow = Field(default_factory=Shadow)
    background: Background = Field(default_factory=Background)
    position: str | dict = DEFAULT_POSITION  # set by CLI/TUI, not the TOML
    margin: Margin = Field(default_factory=Margin)
    max_line_chars: int = 42
    max_lines: int = 2
    max_words: int = 0  # words per subtitle event; 0 = unlimited

    def alignment(self) -> int:
        if isinstance(self.position, dict):
            return 5
        try:
            return ANCHORS[self.position]
        except KeyError:
            raise ValueError(
                f"unknown position {self.position!r} (expected one of {', '.join(ANCHORS)} or {{x,y}})"
            ) from None

    def pos_override(self) -> tuple[int, int] | None:
        """Explicit coordinates as (x, y) offsets from the centre of the frame."""
        if isinstance(self.position, dict):
            return int(self.position["x"]), int(self.position["y"])
        return None


def parse_position(value: str) -> str | dict:
    """CLI position: an anchor name, or 'x,y' offsets from the frame centre.

    (0, 0) is the middle of the video, +x right and +y down, so the same pair
    lands in the same relative spot whatever the resolution.
    """
    value = value.strip()
    if value in ANCHORS:
        return value
    if "," in value:
        x, _, y = value.partition(",")
        try:
            return {"x": int(x), "y": int(y)}
        except ValueError:
            pass
    raise ValueError(
        f"invalid position {value!r} — use one of {', '.join(ANCHORS)} "
        "or 'x,y' offsets from the frame centre"
    )


class StylesConfig(BaseModel):
    play_res: str | list[int] = "video"
    default_preset: str | None = None  # preset applied when none is passed
    default: StyleDef = Field(default_factory=StyleDef)
    presets: dict[str, dict] = Field(default_factory=dict)  # raw [style.NAME] tables
    speaker: dict[str, dict] = Field(default_factory=dict)  # raw [speaker.KEY] tables
    track: dict[str, dict] = Field(default_factory=dict)    # raw [track.LANG] tables

    def preset_names(self) -> list[str]:
        return sorted(self.presets)

    def track_names(self) -> list[str]:
        return sorted(self.track)

    def base(self, preset: str | None, track: TrackKey = None) -> StyleDef:
        """[default] <- [style.<preset>] <- [track.<key>] for each key in order.

        `track` may be one key or several. Several is how ROLE styling works:
        ("source", "en") merges [track.source] then [track.en], so a rule like
        "whatever language is being spoken is yellow" can be written once and
        still be overridden for one specific language.
        """
        keys = _track_keys(track)
        hits = [k for k in keys if k in self.track]
        if not preset and not hits:
            return self.default
        merged = self.default.model_dump()
        if preset:
            if preset not in self.presets:
                available = ", ".join(self.preset_names()) or "none defined"
                raise ValueError(f"unknown preset {preset!r} — available: {available}")
            merged = _deep_merge(merged, self.presets[preset])
        for key in hits:
            merged = _deep_merge(merged, self.track[key])
        return StyleDef.model_validate(merged)

    def resolve(
        self,
        speaker_id: str | None,
        display_name: str | None,
        preset: str | None = None,
        track: TrackKey = None,
    ) -> tuple[str, StyleDef]:
        """-> (ass_style_name, merged StyleDef).

        The name carries the track too, because the same speaker in two
        languages is two different ASS styles and they must not share a line.
        """
        base = self.base(preset, track)
        hits = [k for k in _track_keys(track) if k in self.track]
        prefix = f"T_{_safe('_'.join(hits))}" if hits else ""
        for key in (speaker_id, display_name):
            if key and key in self.speaker:
                merged = _deep_merge(base.model_dump(), self.speaker[key])
                name = f"{prefix}_S_{_safe(key)}" if prefix else f"S_{_safe(key)}"
                return name, StyleDef.model_validate(merged)
        return prefix or "Default", base


def _track_keys(track: TrackKey) -> list[str]:
    """One key or several, always as a list, empties dropped."""
    if track is None:
        return []
    if isinstance(track, str):
        return [track] if track else []
    return [k for k in track if k]


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name)


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_styles(path: str | Path | None) -> StylesConfig:
    if path is None:
        return StylesConfig()
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    meta = raw.pop("meta", {})
    return StylesConfig(
        play_res=meta.get("play_res", "video"),
        default_preset=meta.get("default_preset"),
        default=StyleDef.model_validate(raw.get("default", {})),
        presets=raw.get("style", {}),
        speaker=raw.get("speaker", {}),
        track=raw.get("track", {}),
    )
