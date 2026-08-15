from subtitle_studio.schema import Segment, Word
from subtitle_studio.stages.transcribe import interpolate_missing_word_times


def seg(words):
    return Segment(id=0, start=10.0, end=20.0, text="x", words=words)


def test_untimed_word_interpolated_between_neighbors():
    s = seg([
        Word(word="uno", start=10.0, end=11.0),
        Word(word="2", start=-1.0, end=-1.0),  # numeral: alignment gave nothing
        Word(word="tres", start=13.0, end=14.0),
    ])
    interpolate_missing_word_times(s)
    w = s.words[1]
    assert 11.0 <= w.start < w.end <= 13.0


def test_untimed_word_at_edges_uses_segment_bounds():
    s = seg([
        Word(word="1", start=-1.0, end=-1.0),
        Word(word="dos", start=12.0, end=13.0),
        Word(word="3", start=-1.0, end=-1.0),
    ])
    interpolate_missing_word_times(s)
    first, last = s.words[0], s.words[2]
    assert 10.0 <= first.start < first.end <= 12.0
    assert 13.0 <= last.start < last.end <= 20.0


def test_timed_words_untouched():
    s = seg([Word(word="hola", start=10.5, end=11.2)])
    interpolate_missing_word_times(s)
    assert (s.words[0].start, s.words[0].end) == (10.5, 11.2)


def test_split_long_segments_caps_duration():
    from subtitle_studio.stages.transcribe import split_long_segments

    words = [Word(word=("uno," if i % 5 == 4 else "uno"), start=float(i), end=float(i) + 0.8)
             for i in range(20)]  # 20 seconds of speech, punctuation every 5th word
    seg = Segment(id=0, start=0.0, end=19.8, text=" ".join(w.word for w in words), words=words)
    result = split_long_segments([seg], max_seconds=8.0)
    assert len(result) >= 2
    assert all(s.end - s.start <= 8.0 * 1.5 for s in result)
    assert [s.id for s in result] == list(range(len(result)))
    assert sum(len(s.words) for s in result) == 20
    assert result[0].start == 0.0 and result[-1].end == 19.8


def test_split_respects_disable_and_short():
    from subtitle_studio.stages.transcribe import split_long_segments

    seg = Segment(id=0, start=0.0, end=30.0, text="x", words=[])
    assert split_long_segments([seg], 0) == [seg]
    assert split_long_segments([seg], 8.0) == [seg]  # fewer than 4 words, untouched
