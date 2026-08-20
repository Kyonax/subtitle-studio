"""The HTTP surface the page drives: the laws it must keep, locked."""

import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

import subtitle_studio.stages.style as style_stage
from subtitle_studio.schema import Segment, SourceInfo, Transcript, Word, load_transcript, save_transcript
from subtitle_studio.web.server import build_server

STYLES_REFERENCE = '''# the styles reference, comments included
[meta]
play_res = "video"

[default]
# Letter height in pixels.
size = 56
# Box behind the text.
background = { enabled = true, color = "#000000AA", padding = { x = 16, y = 10 } }
'''


@pytest.fixture
def job(tmp_path, monkeypatch):
    """A video with a transcript and a styles.toml, served by a live server."""
    video = tmp_path / "clip.mkv"
    video.write_bytes(b"not really a video")
    workdir = tmp_path / "clip.studio"
    workdir.mkdir()
    transcript = Transcript(
        source=SourceInfo(media_path=str(video)),
        language="es",
        segments=[
            Segment(id=0, start=0.0, end=3.0, language="es", text="Hola mundo.",
                    words=[Word(word="Hola", start=0.0, end=1.5), Word(word="mundo.", start=1.5, end=3.0)]),
        ],
    )
    save_transcript(transcript, workdir / "transcript.json")

    translated = transcript.model_copy(deep=True)
    translated.language = "en"
    translated.translated_from = "es"
    translated.segments[0].text = "Hello world."
    translated.segments[0].words = []
    save_transcript(translated, workdir / "transcript.en.json")

    styles = tmp_path / "styles.toml"
    styles.write_text(STYLES_REFERENCE, encoding="utf-8")
    monkeypatch.setattr(style_stage, "project_root", lambda: tmp_path)

    httpd, studio = build_server(video, "127.0.0.1", 0, dist_dir=None)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield {"base": base, "video": video, "workdir": workdir, "styles": styles, "studio": studio}
    httpd.shutdown()
    httpd.server_close()


def call(base, path, payload=None, method=None, headers=None):
    url = f"{base}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    if data:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read()
        if response.headers.get_content_type() == "application/json":
            return response.status, json.loads(body)
        return response.status, body


def test_health_and_job_state(job):
    status, health = call(job["base"], "/api/health")
    assert status == 200 and health["version"] and health["styles_path"] == str(job["styles"])

    status, state = call(job["base"], "/api/job")
    assert state["name"] == "clip.mkv"
    assert state["stages"]["transcribe"]["state"] == "done"
    assert [row["text"] for row in state["transcript"]["segments"]] == ["Hola mundo."]
    assert [track["id"] for track in state["tracks"]] == ["", "en"]


def test_editing_a_segment_retimes_its_words(job):
    """Law 1: an edit on the source always retimes the words, so the layout
    guard can never drop them and the screen always shows the new text."""
    status, payload = call(job["base"], "/api/segment", {"id": 0, "text": "Hola  mundo  entero  ahora"})
    assert status == 200 and payload["words"] == 4

    segment = load_transcript(job["workdir"] / "transcript.json").segments[0]
    assert segment.text == "Hola mundo entero ahora"          # whitespace normalized
    assert [w.word for w in segment.words] == ["Hola", "mundo", "entero", "ahora"]
    assert segment.words[0].start == 0.0 and segment.words[-1].end == 3.0


def test_editing_a_translated_track_keeps_it_wordless(job):
    """Translated variants carry no word timings by design — an edit there must
    not invent any, the proportional split does the timing."""
    call(job["base"], "/api/segment", {"track": "en", "id": 0, "text": "Hello whole world"})
    segment = load_transcript(job["workdir"] / "transcript.en.json").segments[0]
    assert segment.text == "Hello whole world" and segment.words == []


def test_empty_edit_is_refused(job):
    with pytest.raises(urllib.error.HTTPError) as raised:
        call(job["base"], "/api/segment", {"id": 0, "text": "   "})
    assert raised.value.code == 400


def test_style_key_write_keeps_the_comments(job):
    status, _ = call(job["base"], "/api/styles/set", {"table": "default", "key": "size", "value": 72})
    assert status == 200
    call(job["base"], "/api/styles/set", {"table": "default", "key": "background.padding.x", "value": 30})
    call(job["base"], "/api/styles/set", {"table": "style.neon", "key": "uppercase", "value": True})

    text = job["styles"].read_text(encoding="utf-8")
    assert "# Letter height in pixels." in text
    assert "# the styles reference, comments included" in text
    assert "size = 72" in text
    assert "padding = { x = 30, y = 10 }" in text

    _, info = call(job["base"], "/api/styles")
    assert info["presets"] == ["neon"]
    assert info["effective"]["size"] == 72


def test_broken_styles_are_refused_and_the_file_survives(job):
    before = job["styles"].read_text(encoding="utf-8")
    with pytest.raises(urllib.error.HTTPError) as raised:
        call(job["base"], "/api/styles", {"raw": "[default]\nsize = "}, method="PUT")
    assert raised.value.code == 400
    assert job["styles"].read_text(encoding="utf-8") == before


def test_preset_lifecycle(job):
    call(job["base"], "/api/styles/preset", {"name": "shorts", "action": "create"})
    _, info = call(job["base"], "/api/styles")
    assert "shorts" in info["presets"]

    with pytest.raises(urllib.error.HTTPError) as raised:  # names are unique
        call(job["base"], "/api/styles/preset", {"name": "shorts", "action": "create"})
    assert raised.value.code == 400

    call(job["base"], "/api/styles/preset", {"name": "shorts", "action": "delete"})
    _, info = call(job["base"], "/api/styles")
    assert "shorts" not in info["presets"]


def test_files_outside_the_job_are_not_served(job, tmp_path):
    status, served = call(job["base"], f"/api/file?path={urllib.parse.quote(str(job['workdir'] / 'transcript.json'))}")
    assert status == 200 and served["segments"][0]["text"] == "Hola mundo."

    stranger = tmp_path.parent / "stranger.json"
    stranger.write_text("{}", encoding="utf-8")
    with pytest.raises(urllib.error.HTTPError) as raised:
        call(job["base"], f"/api/file?path={urllib.parse.quote(str(stranger))}")
    assert raised.value.code == 403


def test_only_localhost_is_answered(job):
    with pytest.raises(urllib.error.HTTPError) as raised:
        call(job["base"], "/api/health", headers={"Host": "subtitle-studio.example.com"})
    assert raised.value.code == 403


def test_unknown_stage_is_refused(job):
    with pytest.raises(urllib.error.HTTPError) as raised:
        call(job["base"], "/api/run", {"stage": "teleport"})
    assert raised.value.code == 400


def test_one_stage_at_a_time(job):
    """The GPU law reaches the browser: a second stage while one runs is
    refused with 409, not queued behind another model load."""
    release = threading.Event()
    started = threading.Event()

    def slow(progress):
        started.set()
        release.wait(5)
        return "done"

    job["studio"].runner.submit("transcribe", "slow stage", slow)
    started.wait(2)
    try:
        with pytest.raises(urllib.error.HTTPError) as raised:
            call(job["base"], "/api/run", {"stage": "extract"})
        assert raised.value.code == 409
        assert json.loads(raised.value.read())["busy"] is True
    finally:
        release.set()


def test_events_replay_what_was_missed(job):
    job["studio"].runner.log("first line")
    job["studio"].runner.log("second line")
    request = urllib.request.Request(f"{job['base']}/api/events")
    with urllib.request.urlopen(request, timeout=5) as stream:
        seen = []
        while len(seen) < 2:
            line = stream.readline().decode()
            if line.startswith("data: "):
                seen.append(json.loads(line[len("data: "):]))
    assert [event["message"] for event in seen] == ["first line", "second line"]


def test_removing_a_track_takes_its_files_with_it(job):
    workdir = job["workdir"]
    (workdir / "subs.en.ass").write_text("[Script Info]\n", encoding="utf-8")
    (workdir / "render.en.mp4").write_bytes(b"video")

    status, payload = call(job["base"], "/api/track/remove", {"track": "en"})
    assert status == 200
    assert set(payload["removed"]) >= {"transcript.en.json", "subs.en.ass", "render.en.mp4"}
    assert not (workdir / "transcript.en.json").exists()
    assert not (workdir / "subs.en.ass").exists()

    # the source transcript is not removable from here — losing it costs a
    # whole transcription, and no button should be able to do that
    with pytest.raises(urllib.error.HTTPError) as raised:
        call(job["base"], "/api/track/remove", {"track": ""})
    assert raised.value.code == 400
    assert (workdir / "transcript.json").exists()


def test_removing_a_track_that_is_not_there(job):
    with pytest.raises(urllib.error.HTTPError) as raised:
        call(job["base"], "/api/track/remove", {"track": "de"})
    assert raised.value.code == 404


def test_adding_a_language_twice_is_refused(job):
    with pytest.raises(urllib.error.HTTPError) as raised:
        call(job["base"], "/api/run", {"stage": "add_track", "options": {"to": "en"}})
    assert raised.value.code == 400
    assert "already" in json.loads(raised.value.read())["error"]

    with pytest.raises(urllib.error.HTTPError) as raised:
        call(job["base"], "/api/run", {"stage": "add_track", "options": {}})
    assert raised.value.code == 400


def test_the_page_state_carries_the_tracks_and_the_delivery(job):
    _, state = call(job["base"], "/api/job")
    assert [track["id"] for track in state["subtitles"]] == ["", "en"]
    assert state["subtitles"][1]["name"] == "english"
    assert state["delivery"]["state"] == "pending"
