"""Word timings for a translation, taken from the source speech.

Without them a translated segment can only be split proportionally by
characters, which ignores pauses and drifts off the voice the source line sits on.
"""

from subtitle_studio.schema import Segment, Word, words_from_source_timing


def source(text, spans, speaker=None):
    words = [Word(word=w, start=a, end=b) for w, (a, b) in zip(text.split(), spans)]
    return Segment(id=0, start=spans[0][0], end=spans[-1][1], text=text,
                   words=words, speaker=speaker)


def test_timings_stay_inside_the_segment_and_move_forward():
    src = source("one two three four", [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0)])

    words = words_from_source_timing(src, "uno dos tres cuatro")

    assert [w.word for w in words] == ["uno", "dos", "tres", "cuatro"]
    assert words[0].start >= src.start and words[-1].end <= src.end + 1e-6
    assert all(a.end <= b.start for a, b in zip(words, words[1:]))
    assert all(w.end > w.start for w in words)


def test_a_pause_in_the_source_is_inherited():
    """A silence between two source words is a jump in the timeline, so the
    translation gets the real pause instead of an average over it."""
    src = source("hello goodbye", [(0.0, 1.0), (9.0, 10.0)])

    words = words_from_source_timing(src, "hola adios")

    # the gap survives: the second word starts near 9s, not near 5s
    assert words[1].start > 5.0


def test_word_count_may_differ_from_the_source():
    src = source("one two", [(0.0, 1.0), (1.0, 2.0)])

    words = words_from_source_timing(src, "uno dos tres cuatro cinco")

    assert len(words) == 5
    assert words[0].start >= 0.0 and words[-1].end <= 2.0 + 1e-6


def test_falls_back_to_an_even_spread_without_source_timings():
    src = Segment(id=0, start=4.0, end=8.0, text="one two", words=[])

    words = words_from_source_timing(src, "uno dos")

    assert len(words) == 2
    assert words[0].start == 4.0
    assert abs(words[-1].end - 8.0) < 1e-6


def test_empty_text_gives_no_words():
    src = source("one", [(0.0, 1.0)])

    assert words_from_source_timing(src, "   ") == []


def test_words_join_back_to_the_text_so_the_layout_guard_accepts_them():
    """Law 2: layout discards words whose join does not equal the segment text."""
    src = source("one two three", [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)])
    text = "uno dos tres cuatro"

    words = words_from_source_timing(src, text)

    assert " ".join(w.word for w in words).split() == text.split()
