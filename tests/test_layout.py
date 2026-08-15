from subtitle_studio.schema import Segment, Word
from subtitle_studio.subtitles.layout import segment_events, wrap_text


def test_wrap_respects_max_chars():
    text = "La precisión del sistema depende del modelo y de la calidad del audio original."
    lines = wrap_text(text, 42)
    assert all(len(line) <= 42 for line in lines)
    assert " ".join(lines) == text


def test_wrap_short_text_single_line():
    assert wrap_text("Hola mundo", 42) == ["Hola mundo"]


def test_overlong_segment_splits_at_word_timestamps():
    words = [
        Word(word=w, start=float(i), end=float(i) + 0.8)
        for i, w in enumerate("uno dos tres cuatro cinco seis siete ocho nueve diez".split())
    ]
    seg = Segment(id=0, start=0.0, end=9.8, text=" ".join(w.word for w in words), words=words)
    events = segment_events(seg, max_line_chars=12, max_lines=1)
    assert len(events) > 1
    for ev in events:
        assert ev.end > ev.start
    # chunk boundaries come from the actual word timings
    assert events[0].start == 0.0
    assert events[-1].end == 9.8
    starts = [e.start for e in events]
    assert starts == sorted(starts)


def test_proportional_split_without_words_covers_full_duration():
    seg = Segment(id=0, start=10.0, end=20.0, text="palabra " * 20, words=[])
    events = segment_events(seg, max_line_chars=20, max_lines=1)
    assert len(events) > 1
    assert events[0].start == 10.0
    assert events[-1].end == 20.0


def test_stale_words_never_reach_the_screen():
    # text was edited, words still carry the OLD text: chunks must use the text
    words = [Word(word=w, start=float(i), end=float(i) + 0.9)
             for i, w in enumerate("this is a new test testing everything about audio".split())]
    seg = Segment(id=0, start=0.0, end=8.9,
                  text="Test is a new test testing everything about audio", words=words)
    events = segment_events(seg, max_line_chars=7, max_lines=2)
    all_text = " ".join(" ".join(e.lines) for e in events)
    assert "Test" in all_text and "this" not in all_text


def test_matching_words_still_do_timed_splits():
    words = [Word(word=w, start=float(i), end=float(i) + 0.9)
             for i, w in enumerate("uno dos tres cuatro cinco seis".split())]
    seg = Segment(id=0, start=0.0, end=5.9, text="uno dos tres cuatro cinco seis", words=words)
    events = segment_events(seg, max_line_chars=8, max_lines=1)
    assert len(events) > 1
    assert events[0].start == 0.0  # timings came from the real words
