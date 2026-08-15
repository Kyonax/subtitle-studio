"""Translation providers. Local and free is the law here — no API keys, no
subscriptions. MADLAD-400 is the default; an `ollama` provider slot is reserved
for context-aware LLM translation later."""

from __future__ import annotations

from subtitle_studio.config import Settings
from subtitle_studio.translate.base import TranslationProvider


def get_provider(settings: Settings) -> TranslationProvider:
    name = settings.translation.provider
    if name == "madlad":
        from subtitle_studio.translate.madlad import MadladProvider

        return MadladProvider(settings)
    raise ValueError(f"unknown translation provider {name!r} (available: madlad)")
