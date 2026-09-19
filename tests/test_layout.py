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


def caps_segment():
    words = [
        Word(word=w, start=round(i * 0.5, 3), end=round((i + 1) * 0.5, 3))
        for i, w in enumerate("uno dos tres cuatro cinco seis siete ocho nueve diez once doce".split())
    ]
    return Segment(id=0, start=0.0, end=6.0, text=" ".join(w.word for w in words), words=words)


def words_per_event(events):
    return [sum(len(line.split()) for line in event.lines) for event in events]


def test_the_smaller_of_the_two_caps_wins():
    """A subtitle is capped twice, by characters (max_line_chars * max_lines) and
    by words (max_words). Whichever is smaller decides — a generous max_words is
    invisible while the character cap is tight, which reads like a broken setting.
    """
    segment = caps_segment()

    # a tight character cap decides, however many words are allowed
    tight = segment_events(segment, max_line_chars=7, max_lines=2, max_words=46)
    assert words_per_event(tight) == words_per_event(segment_events(segment, 7, 2, max_words=0))
    assert all(len(event.text.replace(r"\N", " ")) <= 14 for event in tight)

    # give the characters room and the word cap is the one that bites
    roomy = segment_events(segment, max_line_chars=60, max_lines=3, max_words=4)
    assert words_per_event(roomy) == [4, 4, 4]

    # a word cap above what the characters can ever hold changes nothing
    assert words_per_event(segment_events(segment, 60, 3, max_words=46)) == words_per_event(
        segment_events(segment, 60, 3, max_words=0)
    )


def test_rebuilding_identical_subtitles_leaves_the_file_alone(tmp_path):
    """A preview rebuilds the ASS constantly. If an identical rebuild touched
    the file, every video built from it would look stale forever."""
    import os
    import time

    from subtitle_studio.schema import Segment, SourceInfo, Transcript, save_transcript
    from subtitle_studio.stages.style import run_style

    workdir = tmp_path / "clip.studio"
    workdir.mkdir()
    video = tmp_path / "clip.mkv"
    video.write_bytes(b"not a video")
    transcript = Transcript(
        source=SourceInfo(media_path=str(video)),
        language="es",
        segments=[Segment(id=0, start=0.0, end=2.0, text="Hola mundo.")],
    )
    save_transcript(transcript, workdir / "transcript.json")

    first = run_style(video, workdir, styles_path=tmp_path / "missing.toml")
    stamp = first.stat().st_mtime
    os.utime(first, (stamp - 100, stamp - 100))
    aged = first.stat().st_mtime

    run_style(video, workdir, styles_path=tmp_path / "missing.toml")
    assert first.stat().st_mtime == aged          # untouched, same subtitles

    transcript.segments[0].text = "Hola mundo entero."
    save_transcript(transcript, workdir / "transcript.json")
    time.sleep(0.01)
    run_style(video, workdir, styles_path=tmp_path / "missing.toml")
    assert first.stat().st_mtime > aged           # real change, real write


def test_split_does_not_strand_a_single_word():
    """Greedy filling to the cap pushes the remainder into the last subtitle,
    which is how a sentence ends on one orphan word ("...web" / "developer").
    The chunk count is unchanged; the words are just spread across it."""
    text = "I'm from Colombia, and I've spent the last seven years as a full-stack web developer."
    seg = Segment(id=0, start=0.0, end=8.0, text=text, words=[])

    events = segment_events(seg, max_line_chars=40, max_lines=1)

    assert len(events) == 3                       # same count a greedy fill needs
    assert all(len(e.text) <= 40 for e in events)  # still inside the cap
    assert min(len(e.text.split()) for e in events) > 1
    # no chunk is a runt next to its neighbours
    lengths = [len(e.text) for e in events]
    assert max(lengths) - min(lengths) <= 10


def test_balanced_split_keeps_word_timings():
    """Balancing changes where chunks break, never what the clock says."""
    words = [
        Word(word=w, start=float(i), end=float(i) + 0.9)
        for i, w in enumerate("alpha bravo charlie delta echo foxtrot golf hotel".split())
    ]
    seg = Segment(id=0, start=0.0, end=7.9, text=" ".join(w.word for w in words), words=words)

    events = segment_events(seg, max_line_chars=20, max_lines=1)

    assert events[0].start == 0.0
    assert events[-1].end == 7.9
    assert [e.start for e in events] == sorted(e.start for e in events)
    assert " ".join(e.text for e in events).split() == [w.word for w in words]
