import pytest

import subtitle_studio.translate as translate_registry


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.received: list[str] = []

    def supports(self, code):
        return True

    def translate_batch(self, texts, src, tgt):
        self.received.extend(texts)
        return [f"[{tgt}] {t}" for t in texts]


@pytest.fixture
def fake_provider(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(translate_registry, "get_provider", lambda settings: provider)
    monkeypatch.setattr("subtitle_studio.stages.translate.get_provider", lambda settings: provider)
    return provider
