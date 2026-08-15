import pytest

from subtitle_studio.config import Settings
from subtitle_studio.schema import Segment, SourceInfo, Transcript, load_transcript, save_transcript
from subtitle_studio.stages.translate import run_translate


def bilingual(tmp_path):
    t = Transcript(
        source=SourceInfo(media_path="/x.mkv"),
        language="en",
        segments=[
            Segment(id=0, start=0.0, end=2.0, language="en", text="Hello everyone."),
            Segment(id=1, start=2.0, end=4.0, language="es", text="Ahora hablo español."),
            Segment(id=2, start=4.0, end=6.0, language="en", text="Back to English."),
        ],
    )
    save_transcript(t, tmp_path / "transcript.json")
    return t


def test_swap_crosses_both_languages(tmp_path, fake_provider):
    bilingual(tmp_path)
    out = run_translate(tmp_path / "x.mkv", tmp_path, Settings(), swap=True)
    assert out.name == "transcript.swap.json"
    result = load_transcript(out)
    texts = [s.text for s in result.segments]
    assert texts == ["[es] Hello everyone.", "[en] Ahora hablo español.", "[es] Back to English."]
    # every segment translated: source kept, per-segment language flipped
    assert all(s.source_text for s in result.segments)
    assert [s.language for s in result.segments] == ["es", "en", "es"]
    assert result.language == "swap"


def test_swap_rejects_monolingual(tmp_path, fake_provider):
    t = Transcript(
        source=SourceInfo(media_path="/x.mkv"), language="en",
        segments=[Segment(id=0, start=0.0, end=1.0, language="en", text="Only English spoken here today.")],
    )
    save_transcript(t, tmp_path / "transcript.json")
    with pytest.raises(ValueError, match="exactly two languages"):
        run_translate(tmp_path / "x.mkv", tmp_path, Settings(), swap=True)


def test_neither_to_nor_swap_rejected(tmp_path, fake_provider):
    bilingual(tmp_path)
    with pytest.raises(ValueError, match="--to LANG"):
        run_translate(tmp_path / "x.mkv", tmp_path, Settings())
