"""The badges the page shows must say what is actually on disk."""

import subtitle_studio.stages.style as style_stage
from subtitle_studio.config import Settings
from subtitle_studio.schema import Segment, SourceInfo, Transcript, Word, save_transcript
from subtitle_studio.state import record_stage
from subtitle_studio.web.status import job_state, translate_inputs, translate_state


def make_job(tmp_path, speakers=None):
    video = tmp_path / "clip.mkv"
    video.write_bytes(b"not really a video")
    workdir = tmp_path / "clip.studio"
    workdir.mkdir()
    transcript = Transcript(
        source=SourceInfo(media_path=str(video)),
        language="es",
        speakers=speakers or {},
        segments=[
            Segment(id=0, start=0.0, end=2.0, language="es", text="Hola mundo.",
                    words=[Word(word="Hola", start=0.0, end=1.0, score=0.9),
                           Word(word="mundo.", start=1.0, end=2.0, score=0.2)]),
            Segment(id=1, start=2.0, end=4.0, language="en", text="Hello world.",
                    words=[Word(word="Hello", start=2.0, end=3.0)]),
        ],
    )
    save_transcript(transcript, workdir / "transcript.json")
    return video, workdir


def test_stage_badges_follow_the_files(tmp_path):
    video, workdir = make_job(tmp_path)
    state = job_state(video, Settings())

    assert state["exists"] and state["workdir"] == str(workdir)
    assert state["stages"]["extract"]["state"] == "pending"       # no audio.wav yet
    assert state["stages"]["transcribe"]["state"] == "done"
    assert state["stages"]["transcribe"]["detail"] == "2 segments"
    assert state["stages"]["diarize"]["state"] == "pending"       # no speakers in the transcript
    assert state["stages"]["style"]["state"] == "pending"
    assert state["stages"]["render"]["state"] == "pending"

    (workdir / "audio.wav").write_bytes(b"RIFF")
    assert job_state(video, Settings())["stages"]["extract"]["state"] == "done"


def test_segments_carry_what_the_table_shows(tmp_path):
    video, _ = make_job(tmp_path, speakers={"SPEAKER_00": {"name": "Ana"}})
    rows = job_state(video, Settings())["transcript"]["segments"]

    assert [row["text"] for row in rows] == ["Hola mundo.", "Hello world."]
    assert rows[0]["low_confidence"] is True     # a word scored below 0.5
    assert rows[1]["low_confidence"] is False
    assert [row["language"] for row in rows] == ["es", "en"]


def test_speaker_and_language_summaries(tmp_path):
    video, workdir = make_job(tmp_path, speakers={"SPEAKER_00": {"name": "Ana"}})
    transcript_file = workdir / "transcript.json"
    from subtitle_studio.schema import load_transcript

    transcript = load_transcript(transcript_file)
    transcript.segments[0].speaker = "SPEAKER_00"
    save_transcript(transcript, transcript_file)

    state = job_state(video, Settings())
    assert state["speakers"] == [
        {"id": "SPEAKER_00", "name": "Ana", "style": None, "segments": 1, "talk_time_s": 2.0}
    ]
    assert state["languages"] == [
        {"code": "es", "segments": 1, "talk_time_s": 2.0},
        {"code": "en", "segments": 1, "talk_time_s": 2.0},
    ]
    assert state["stages"]["diarize"]["state"] == "done"


def test_translation_staleness_is_reported(tmp_path):
    """Law 3: an edit to the source must show the translated track as stale."""
    video, workdir = make_job(tmp_path)
    settings = Settings()
    assert translate_state(workdir, settings, "en") == "missing"

    from subtitle_studio.schema import load_transcript

    translated = load_transcript(workdir / "transcript.json")
    translated.language = "en"
    translated.translated_from = "es"
    save_transcript(translated, workdir / "transcript.en.json")
    record_stage(workdir, "translate:en", translate_inputs(workdir, settings, "en"))
    assert translate_state(workdir, settings, "en") == "fresh"
    assert job_state(video, settings, track="en")["stages"]["translate"]["state"] == "done"

    source = load_transcript(workdir / "transcript.json")
    source.segments[0].text = "Hola mundo, editado."
    save_transcript(source, workdir / "transcript.json")
    assert translate_state(workdir, settings, "en") == "stale"
    assert job_state(video, settings, track="en")["stages"]["translate"]["state"] == "stale"


def test_tracks_list_every_transcript_variant(tmp_path):
    video, workdir = make_job(tmp_path)
    from subtitle_studio.schema import load_transcript

    for track in ("en", "swap"):
        variant = load_transcript(workdir / "transcript.json")
        variant.language = track
        save_transcript(variant, workdir / f"transcript.{track}.json")

    tracks = job_state(video, Settings())["tracks"]
    assert [t["id"] for t in tracks] == ["", "en", "swap"]
    assert tracks[0]["label"] == "source (es)"
    assert tracks[2]["kind"] == "swap"


def test_styles_info_reaches_the_page(tmp_path, monkeypatch):
    video, _ = make_job(tmp_path)
    styles = tmp_path / "styles.toml"
    styles.write_text('[default]\nsize = 44\n\n[style.neon]\nuppercase = true\n', encoding="utf-8")
    monkeypatch.setattr(style_stage, "project_root", lambda: tmp_path)

    info = job_state(video, Settings())["styles"]
    assert info["path"] == str(styles)
    assert info["presets"] == ["neon"]
    assert info["effective"]["size"] == 44
    assert "bottom-center" in info["anchors"]


def test_styles_info_resolves_the_role_table_first(tmp_path, monkeypatch):
    """The panel must show what `style` paints: [track.<role>] then
    [track.<lang>]. The key it hands back stays the language, because that is
    the table the page files an edit under."""
    from subtitle_studio.schema import load_transcript
    from subtitle_studio.web.status import styles_info

    video, workdir = make_job(tmp_path)
    variant = load_transcript(workdir / "transcript.json")
    variant.language = "en"
    variant.translated_from = "es"
    save_transcript(variant, workdir / "transcript.en.json")
    (tmp_path / "styles.toml").write_text(
        '[track.source]\nsize = 60\n\n[track.translated]\nsize = 25\ncolor = "#f6f5f4"\n\n'
        '[track.en]\nsize = 30\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(style_stage, "project_root", lambda: tmp_path)

    source = styles_info(video, None, None)
    translated = styles_info(video, None, "en")

    assert (source["track"], source["effective"]["size"]) == ("es", 60)
    assert (translated["track"], translated["effective"]["size"]) == ("en", 30)
    assert translated["effective"]["color"] == "#f6f5f4"


def test_subtitle_tracks_describe_every_language(tmp_path):
    """The rail iterates this: the source plus one entry per translated track,
    each carrying whether its text, its subtitles and its video are current."""
    from subtitle_studio.schema import load_transcript
    from subtitle_studio.web.status import delivery_state, subtitle_tracks

    video, workdir = make_job(tmp_path)
    settings = Settings()

    for track in ("en", "swap"):
        variant = load_transcript(workdir / "transcript.json")
        variant.language = track
        variant.translated_from = "es"
        save_transcript(variant, workdir / f"transcript.{track}.json")

    (workdir / "subs.es.ass").write_text("[Script Info]\n", encoding="utf-8")

    tracks = subtitle_tracks(workdir, settings, None)
    assert [item["id"] for item in tracks] == ["", "en", "swap"]
    assert [item["kind"] for item in tracks] == ["source", "unify", "swap"]
    assert tracks[0]["name"] == "spanish"          # plain names, not codes
    assert tracks[1]["name"] == "english"
    assert tracks[2]["name"] == "bilingual cross"
    assert tracks[0]["translate"] == "n/a"          # the source is never translated
    assert tracks[1]["translate"] == "stale"        # never recorded, so not fresh
    assert tracks[0]["styled"] == "done" and tracks[1]["styled"] == "pending"
    assert tracks[0]["segments"] == 2

    delivery = delivery_state(workdir, tracks)
    assert delivery["state"] == "pending" and delivery["path"] is None
    assert delivery["tracks_built"] == [""]


def test_delivery_goes_stale_when_a_subtitle_is_rebuilt(tmp_path):
    import os
    import time

    from subtitle_studio import paths
    from subtitle_studio.web.status import delivery_state, subtitle_tracks

    video, workdir = make_job(tmp_path)
    subs = workdir / "subs.es.ass"
    subs.write_text("[Script Info]\n", encoding="utf-8")
    muxed = paths.muxed_path(workdir)
    muxed.write_bytes(b"matroska")

    tracks = subtitle_tracks(workdir, Settings(), None)
    assert delivery_state(workdir, tracks)["state"] == "done"

    later = time.time() + 10
    os.utime(subs, (later, later))
    assert delivery_state(workdir, tracks)["state"] == "stale"
