"""Putting every subtitle track into one video: the mapping, and its guards."""

import pytest

from subtitle_studio import paths
from subtitle_studio.stages.mux import (
    available_subtitles,
    build_mux_command,
    language_tag,
    run_mux,
    track_title,
)


def test_language_tags_are_the_ones_players_read():
    assert language_tag("es") == "spa"
    assert language_tag("EN") == "eng"
    assert language_tag("pt") == "por"
    assert language_tag("swap") == "mul"      # honestly "multiple languages"
    assert language_tag("xyz") == "xyz"        # unknown codes pass through
    assert track_title("swap") == "bilingual cross"
    assert track_title("fr") == "fr"


def test_available_subtitles_reads_the_work_directory(tmp_path):
    (tmp_path / "subs.es.ass").write_text("[Script Info]\n", encoding="utf-8")
    (tmp_path / "subs.swap.ass").write_text("[Script Info]\n", encoding="utf-8")
    (tmp_path / "transcript.json").write_text("{}", encoding="utf-8")
    assert [track for track, _ in available_subtitles(tmp_path)] == ["es", "swap"]


def test_command_maps_one_stream_per_track(tmp_path):
    video = tmp_path / "clip.mkv"
    subtitles = [("es", tmp_path / "subs.es.ass"), ("en", tmp_path / "subs.en.ass")]
    command = build_mux_command(video, subtitles, tmp_path / "subtitled.mkv")

    # the source is copied, never re-encoded
    assert "-c:v" in command and command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:s") + 1] == "copy"
    # video, optional audio, then one input per subtitle file
    assert command.count("-i") == 3
    assert "-map" in command and "0:v:0" in command and "0:a?" in command
    assert "1:0" in command and "2:0" in command
    # each stream carries its language and a readable name
    assert "language=spa" in command and "language=eng" in command
    assert "title=es" in command and "title=en" in command
    # the first track is the one a player opens with
    assert command[command.index("-disposition:s:0") + 1] == "default"


def test_requesting_a_track_that_was_never_built_is_refused(tmp_path):
    (tmp_path / "subs.es.ass").write_text("[Script Info]\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError) as raised:
        run_mux(tmp_path / "clip.mkv", tmp_path, tracks=["es", "de"])
    assert "de" in str(raised.value)


def test_nothing_built_yet_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_mux(tmp_path / "clip.mkv", tmp_path)


def test_the_muxed_file_lives_in_the_work_directory(tmp_path):
    assert paths.muxed_path(tmp_path).name == "subtitled.mkv"
    assert paths.muxed_path(tmp_path).parent == tmp_path
