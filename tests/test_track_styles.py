"""Per-track overrides and the end-of-subtitle full stop.

Both exist for one video carrying several languages at once: [track.<lang>] so
restyling one language leaves the others alone, and end_period so the cards read
the way subtitles are supposed to.
"""

import pytest

from subtitle_studio.preview import merge_transcripts
from subtitle_studio.schema import Segment, SourceInfo, Transcript, VideoInfo
from subtitle_studio.subtitles.ass_builder import _drop_end_period, build_ass
from subtitle_studio.subtitles.styleconf import StylesConfig


def transcript(language, text, speaker=None):
    return Transcript(
        source=SourceInfo(media_path="t", video=VideoInfo(width=1920, height=1080, fps=30)),
        language=language,
        segments=[Segment(id=0, start=1.0, end=3.0, text=text, speaker=speaker)],
    )


def styles(**track_tables):
    return StylesConfig(track=dict(track_tables))


# --------------------------------------------------------------------------- #
# the track layer
# --------------------------------------------------------------------------- #

def test_track_override_changes_only_that_track():
    config = styles(es={"size": 30, "color": "#FF0000"})

    en = build_ass(transcript("en", "hello"), config, None, track="en")
    es = build_ass(transcript("es", "hola"), config, None, track="es")

    en_style = next(line for line in en.splitlines() if line.startswith("Style: "))
    es_style = next(line for line in es.splitlines() if line.startswith("Style: "))
    assert ",56," in en_style          # untouched default size
    assert ",30," in es_style          # the track override
    # PrimaryColour is field 3, ASS &HAABBGGRR — red at full opacity
    assert es_style.split(",")[3] == "&H000000FF"
    assert en_style.split(",")[3] == "&H00FFFFFF"


def test_a_track_without_a_table_is_the_plain_default():
    config = styles(es={"size": 30})
    doc = build_ass(transcript("en", "hello"), config, None, track="en")

    assert "Style: Default," in doc
    assert ",56," in next(line for line in doc.splitlines() if line.startswith("Style: "))


def test_resolution_order_is_default_then_preset_then_track():
    config = StylesConfig(
        presets={"neon": {"size": 40, "bold": True}},
        track={"es": {"size": 30}},
    )
    style = config.base("neon", "es")

    assert style.size == 30      # track wins over preset
    assert style.bold is True    # preset still applies underneath


def test_speaker_still_wins_over_the_track():
    config = StylesConfig(track={"es": {"size": 30, "color": "#111111"}},
                          speaker={"SPEAKER_00": {"color": "#00FF00"}})

    _, style = config.resolve("SPEAKER_00", None, None, "es")

    assert style.size == 30           # from the track
    assert style.color == "#00FF00"   # speaker overrides it


def test_the_same_speaker_in_two_tracks_gets_two_style_names():
    """Otherwise both languages would share one ASS style line and one look."""
    config = StylesConfig(track={"es": {"size": 30}}, speaker={"S0": {"color": "#00FF00"}})

    en_name, _ = config.resolve("S0", None, None, "en")
    es_name, _ = config.resolve("S0", None, None, "es")

    assert en_name != es_name


# --------------------------------------------------------------------------- #
# merging tracks for the all-languages preview
# --------------------------------------------------------------------------- #

def test_merge_reports_the_track_of_every_segment():
    merged, track_by_id = merge_transcripts([transcript("en", "hello"), transcript("es", "hola")])

    assert [s.id for s in merged.segments] == [0, 1]   # ids renumbered, no collision
    assert track_by_id == {0: "en", 1: "es"}
    assert [s.text for s in merged.segments] == ["hello", "hola"]


def test_merged_document_keeps_each_track_its_own_style():
    config = styles(es={"size": 30})
    merged, track_by_id = merge_transcripts([transcript("en", "hello"), transcript("es", "hola")])

    doc = build_ass(merged, config, None, track_of=lambda s: track_by_id.get(s.id))

    style_lines = [line for line in doc.splitlines() if line.startswith("Style: ")]
    assert len(style_lines) == 2                       # one per track, not one shared
    assert any(",56," in line for line in style_lines)
    assert any(",30," in line for line in style_lines)


def test_merged_document_stacks_the_two_languages():
    """Same timespan, same alignment -> the builder's own stacking separates
    them, which is what makes the preview honest about a two-language burn."""
    merged, track_by_id = merge_transcripts([transcript("en", "hello"), transcript("es", "hola")])

    doc = build_ass(merged, StylesConfig(), None, track_of=lambda s: track_by_id.get(s.id))

    dialogues = [line for line in doc.splitlines() if line.startswith("Dialogue: ")]
    assert len(dialogues) == 2
    assert "hello" in dialogues[0] and "hola" in dialogues[1]
    # With no drawn box or glow there is no \pos, so the stack is MarginV
    # (field 7): the second language is lifted a full block off the first.
    assert dialogues[0].split(",")[7] == "0"
    assert int(dialogues[1].split(",")[7]) > 0


# --------------------------------------------------------------------------- #
# the end-of-subtitle full stop
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("line, expected", [
    ("Hello there.", "Hello there"),
    ("Hello there", "Hello there"),
    ("Hello there.  ", "Hello there"),
    ("Wait...", "Wait..."),          # an ellipsis runs on into the next card
    ("Really?", "Really?"),
    ("Stop!", "Stop!"),
    ("Dr. Moreno", "Dr. Moreno"),    # only the END of the line is touched
    ("", ""),
])
def test_drop_end_period(line, expected):
    assert _drop_end_period(line) == expected


def test_subtitles_drop_the_closing_full_stop_by_default():
    doc = build_ass(transcript("en", "This is the end."), StylesConfig(), None)

    assert "This is the end" in doc
    assert "the end." not in doc


def test_end_period_true_keeps_it():
    config = StylesConfig(track={"en": {"end_period": True}})
    doc = build_ass(transcript("en", "This is the end."), config, None, track="en")

    assert "This is the end." in doc


# --------------------------------------------------------------------------- #
# burning every language into one picture
# --------------------------------------------------------------------------- #

def test_combined_subs_path_is_not_globbed_by_mux(tmp_path):
    """`mux` collects tracks with `subs.*.ass`. The combined document must sit
    outside that glob or it would be embedded as a bogus extra language."""
    from subtitle_studio import paths

    combined = paths.combined_subs_path(tmp_path)
    assert combined.name == "combined.ass"
    assert combined not in list(tmp_path.glob("subs.*.ass"))


@pytest.mark.parametrize("codec, configured, expected", [
    # an NVENC preset must never reach x264 -- ffmpeg rejects it outright
    ("libx264", "p5", "slow"),
    ("libx264", "veryslow", "veryslow"),
    ("libx264", "", "slow"),
    ("h264_nvenc", "p5", "p5"),
    ("h264_nvenc", "slow", "p5"),
    ("hevc_nvenc", "p7", "p7"),
])
def test_preset_is_codec_aware(codec, configured, expected):
    from subtitle_studio.stages.render import _preset_for

    assert _preset_for(codec, configured) == expected


def test_an_explicit_position_is_never_auto_shifted():
    """Auto-stacking keeps ANCHORED subtitles off each other. A subtitle placed
    by coordinate must hold that exact spot, or one language lands on two
    different rows depending on whether it overlapped another track."""
    config = StylesConfig(track={
        "en": {"position": {"x": 0, "y": 170}},
        "es": {"position": {"x": 0, "y": 155}},
    })
    merged, track_by_id = merge_transcripts([transcript("en", "hello"), transcript("es", "hola")])

    doc = build_ass(merged, config, None, track_of=lambda s: track_by_id.get(s.id))

    dialogues = [line for line in doc.splitlines() if line.startswith("Dialogue: ")]
    # 1080-tall frame -> centre 540, so +170 and +155
    assert "\\pos(960,710)" in dialogues[0]
    assert "\\pos(960,695)" in dialogues[1]


def test_anchored_tracks_still_stack():
    """The protection is for explicit coordinates only — two auto-placed
    languages must still be separated, which is the whole point of stacking."""
    merged, track_by_id = merge_transcripts([transcript("en", "hello"), transcript("es", "hola")])

    doc = build_ass(merged, StylesConfig(), None, track_of=lambda s: track_by_id.get(s.id))

    dialogues = [line for line in doc.splitlines() if line.startswith("Dialogue: ")]
    assert int(dialogues[1].split(",")[7]) > int(dialogues[0].split(",")[7])


# --------------------------------------------------------------------------- #
# role styling: what is spoken is yellow, the other language is white
# --------------------------------------------------------------------------- #

def role_config():
    """The owner's rule, written once and language-independent."""
    return StylesConfig(track={
        "source": {"color": "#F9CD26", "position": {"x": 0, "y": 136}},
        "translated": {"color": "#f6f5f4", "size": 25, "position": {"x": 0, "y": 160}},
    })


@pytest.mark.parametrize("spoken, other", [("en", "es"), ("es", "en"), ("fr", "pt")])
def test_the_spoken_language_is_always_the_source_style(spoken, other):
    """Keyed by ROLE, so recording in Spanish makes the Spanish yellow without
    touching the config — the whole point of not keying on the language."""
    config = role_config()

    assert config.base(None, ("source", spoken)).color == "#F9CD26"
    assert config.base(None, ("translated", other)).color == "#f6f5f4"


def test_a_language_table_overrides_the_role():
    config = role_config()
    config.track["es"] = {"size": 40}

    style = config.base(None, ("translated", "es"))

    assert style.size == 40             # the language table wins
    assert style.color == "#f6f5f4"     # the role still supplies the rest


def test_role_and_language_get_distinct_style_names():
    config = role_config()

    src, _ = config.resolve(None, None, None, ("source", "en"))
    trn, _ = config.resolve(None, None, None, ("translated", "es"))

    assert src != trn


def test_a_single_string_track_key_still_works():
    """Backwards compatible: [track.es] alone addressed by its language."""
    config = StylesConfig(track={"es": {"size": 30}})

    assert config.base(None, "es").size == 30
    assert config.base(None, ("translated", "es")).size == 30
