from subtitle_studio.langid import annotate_segments, detect_language
from subtitle_studio.schema import Segment, SourceInfo, Transcript


def make(lang, texts):
    return Transcript(
        source=SourceInfo(media_path="/x.mkv"),
        language=lang,
        segments=[Segment(id=i, start=float(i), end=float(i) + 1, text=t) for i, t in enumerate(texts)],
    )


def test_detects_spanish_and_english():
    assert detect_language("La precisión del sistema depende del modelo de audio.")[0] == "es"
    assert detect_language("I want to see how accurate the subtitles are.")[0] == "en"


def test_annotate_mixed_transcript():
    t = make("en", [
        "This is a test, testing everything about audio.",
        "Ahora estoy hablando en español para probar el sistema.",
    ])
    talk_time = annotate_segments(t)
    assert t.segments[0].language == "en"
    assert t.segments[1].language == "es"
    assert set(talk_time) == {"en", "es"}


def test_short_segment_inherits_file_language():
    t = make("es", ["Ok."])
    annotate_segments(t)
    assert t.segments[0].language == "es"
