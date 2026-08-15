"""Main tool configuration (models, devices, render settings, paths).

Search order (later wins): built-in defaults -> ~/.config/subtitle-studio/config.toml
-> --config PATH. Styling lives in its own styles.toml handled by subtitles/;
this file is about *how* the pipeline runs, not how subtitles look.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

USER_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "subtitle-studio" / "config.toml"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "subtitle-studio"


class AsrConfig(BaseModel):
    engine: str = "whisperx"  # whisperx | faster-whisper
    model: str = "large-v3"
    compute_type: str = "int8_float16"
    batch_size: int = 8
    language: str | None = None  # None = auto-detect
    condition_on_previous_text: bool = False
    max_segment_seconds: float = 8.0  # split longer segments at word boundaries, 0 = off


class DiarizationConfig(BaseModel):
    model: str = "pyannote/speaker-diarization-3.1"
    min_speakers: int | None = None
    max_speakers: int | None = None


class TranslationConfig(BaseModel):
    provider: str = "madlad"
    device: str = "cuda"  # cuda | cpu
    beam_size: int = 4
    batch_size: int = 16


class RenderConfig(BaseModel):
    codec: str = "h264_nvenc"
    preset: str = "p5"
    cq: int = 19
    pix_fmt: str = "yuv420p"


class PathsConfig(BaseModel):
    fonts_dir: str | None = None  # default: <project>/fonts next to styles.toml, else cwd/fonts
    models_dir: str = str(CACHE_DIR / "models")


class AuthConfig(BaseModel):
    hf_token: str | None = None  # falls back to HF_TOKEN env


class Settings(BaseModel):
    asr: AsrConfig = Field(default_factory=AsrConfig)
    diarization: DiarizationConfig = Field(default_factory=DiarizationConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)

    def hf_token(self) -> str | None:
        return self.auth.hf_token or os.environ.get("HF_TOKEN")


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_settings(config_path: str | Path | None = None) -> Settings:
    merged: dict = {}
    for candidate in [USER_CONFIG, Path(config_path) if config_path else None]:
        if candidate and candidate.exists():
            with open(candidate, "rb") as f:
                merged = _deep_merge(merged, tomllib.load(f))
    return Settings.model_validate(merged)
