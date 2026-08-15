import json

import pytest

from subtitle_studio.schema import (
    SCHEMA_VERSION,
    Segment,
    SchemaVersionError,
    SourceInfo,
    SpeakerInfo,
    Transcript,
    Word,
    load_transcript,
    save_transcript,
)


def make_transcript() -> Transcript:
    return Transcript(
        source=SourceInfo(media_path="/tmp/interview.mkv", audio_path="audio.wav", duration_s=61.4),
        language="es",
        language_probability=0.99,
        speakers={"SPEAKER_00": SpeakerInfo(name="María"), "SPEAKER_01": SpeakerInfo()},
        segments=[
            Segment(
                id=0, start=1.23, end=4.56, speaker="SPEAKER_00",
                text="Hola, ¿cómo estás?",
                words=[Word(word="Hola,", start=1.23, end=1.51, score=0.98, speaker="SPEAKER_00")],
            )
        ],
    )


def test_round_trip(tmp_path):
    original = make_transcript()
    path = tmp_path / "transcript.json"
    save_transcript(original, path)
    loaded = load_transcript(path)
    assert loaded == original


def test_bak_written_on_overwrite(tmp_path):
    path = tmp_path / "transcript.json"
    first = make_transcript()
    save_transcript(first, path)
    second = make_transcript()
    second.speakers["SPEAKER_01"].name = "Dante"
    save_transcript(second, path)
    bak = tmp_path / "transcript.json.bak"
    assert bak.exists()
    assert json.loads(bak.read_text())["speakers"]["SPEAKER_01"]["name"] is None
    assert load_transcript(path).speakers["SPEAKER_01"].name == "Dante"


def test_unknown_schema_version_rejected(tmp_path):
    path = tmp_path / "transcript.json"
    raw = json.loads(make_transcript().model_dump_json())
    raw["schema_version"] = SCHEMA_VERSION + 99
    path.write_text(json.dumps(raw))
    with pytest.raises(SchemaVersionError):
        load_transcript(path)


def test_display_name_falls_back_to_id():
    t = make_transcript()
    assert t.display_name("SPEAKER_00") == "María"
    assert t.display_name("SPEAKER_01") == "SPEAKER_01"
    assert t.display_name(None) is None


def test_retime_words_same_count_keeps_timings():
    from subtitle_studio.schema import retime_words

    seg = make_transcript().segments[0]
    seg.words = [Word(word=w, start=1.0 + i, end=1.5 + i) for i, w in enumerate(["a", "b", "c"])]
    seg.text = "x y z"
    out = retime_words(seg, seg.text)
    assert [w.word for w in out] == ["x", "y", "z"]
    assert [w.start for w in out] == [1.0, 2.0, 3.0]


def test_retime_words_different_count_shares_span():
    from subtitle_studio.schema import retime_words

    seg = make_transcript().segments[0]
    out = retime_words(seg, "uno dos tres cuatro")
    assert len(out) == 4
    assert out[0].start == seg.start and abs(out[-1].end - seg.end) < 0.01
    starts = [w.start for w in out]
    assert starts == sorted(starts)
