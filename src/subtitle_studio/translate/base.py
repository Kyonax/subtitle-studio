from __future__ import annotations

from typing import Protocol


class TranslationProvider(Protocol):
    name: str

    def translate_batch(self, texts: list[str], src: str, tgt: str) -> list[str]: ...

    def supports(self, code: str) -> bool: ...
