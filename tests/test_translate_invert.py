import pytest

from subtitle_studio.config import Settings
from subtitle_studio.schema import Segment, SourceInfo, Transcript, Word, load_transcript, save_transcript
from subtitle_studio.stages.translate import run_translate


def mixed_transcript(tmp_path):
    t = Transcript(
        source=SourceInfo(media_path="/x.mkv"),
        language="en",
        segments=[
            Segment(id=0, start=0.0, end=2.0, language="en", text="Hello everyone.",
                    words=[Word(word="Hello", start=0.0, end=0.5)]),
            Segment(id=1, start=2.0, end=4.0, language="es", text="Ahora hablo español.",
                    words=[Word(word="Ahora", start=2.0, end=2.4)]),
        ],
    )
    save_transcript(t, tmp_path / "transcript.json")
    return t


def test_invert_translates_only_foreign_segments(tmp_path, fake_provider):
    mixed_transcript(tmp_path)
    out = run_translate(tmp_path / "x.mkv", tmp_path, Settings(), "es")
    result = load_transcript(out)
    # English segment translated, source kept
    assert result.segments[0].text == "[es] Hello everyone."
    assert result.segments[0].source_text == "Hello everyone."
    # Its words are re-timed from the SOURCE speech rather than dropped —
    # without them layout could only split this segment proportionally, and the
    # translated line would drift off the voice the source line sits on.
    words = result.segments[0].words
    assert " ".join(w.word for w in words) == "[es] Hello everyone."
    assert words[0].start >= result.segments[0].start
    assert words[-1].end <= result.segments[0].end + 1e-6
    # Spanish segment passed through with words intact
    assert result.segments[1].text == "Ahora hablo español."
    assert result.segments[1].words and result.segments[1].source_text is None
    assert fake_provider.received == ["Hello everyone."]
    assert result.language == "es" and result.translated_from == "en"


def test_all_flag_translates_everything(tmp_path, fake_provider):
    mixed_transcript(tmp_path)
    out = run_translate(tmp_path / "x.mkv", tmp_path, Settings(), "es", translate_all=True)
    result = load_transcript(out)
    assert [s.text for s in result.segments] == ["[es] Hello everyone.", "[es] Ahora hablo español."]
    assert fake_provider.received == ["Hello everyone.", "Ahora hablo español."]


def test_nothing_to_translate_raises(tmp_path, fake_provider):
    t = Transcript(
        source=SourceInfo(media_path="/x.mkv"), language="es",
        segments=[Segment(id=0, start=0.0, end=1.0, language="es", text="Hola a todos los presentes.")],
    )
    save_transcript(t, tmp_path / "transcript.json")
    with pytest.raises(ValueError, match="nothing to translate"):
        run_translate(tmp_path / "x.mkv", tmp_path, Settings(), "es")


def test_source_edit_makes_translation_stale(tmp_path, fake_provider):
    from subtitle_studio.state import hash_file, hash_obj, load_state, stage_fresh

    mixed_transcript(tmp_path)
    run_translate(tmp_path / "x.mkv", tmp_path, Settings(), "es")

    def current_inputs():
        return {
            "transcript": hash_file(tmp_path / "transcript.json"),
            "config:translation": hash_obj(Settings().translation.model_dump()),
            "to": "es",
            "mode": "invert",
        }

    assert stage_fresh(load_state(tmp_path), "translate:es", current_inputs())

    # the owner edits the source transcript
    t = load_transcript(tmp_path / "transcript.json")
    t.segments[0].text = "Hello everyone, edited."
    save_transcript(t, tmp_path / "transcript.json")
    assert not stage_fresh(load_state(tmp_path), "translate:es", current_inputs())

    # re-translating restores freshness and carries the edit
    run_translate(tmp_path / "x.mkv", tmp_path, Settings(), "es")
    assert stage_fresh(load_state(tmp_path), "translate:es", current_inputs())
    translated = load_transcript(tmp_path / "transcript.es.json")
    assert "edited" in translated.segments[0].text
