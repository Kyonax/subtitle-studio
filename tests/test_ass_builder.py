import tomllib

from subtitle_studio.schema import Segment, SourceInfo, SpeakerInfo, Transcript, VideoInfo
from subtitle_studio.subtitles.ass_builder import build_ass
from subtitle_studio.subtitles.styleconf import StyleDef, StylesConfig


def make_transcript():
    return Transcript(
        source=SourceInfo(media_path="/x.mkv", video=VideoInfo(width=1280, height=720, fps=30)),
        language="es",
        speakers={"SPEAKER_00": SpeakerInfo(name="María"), "SPEAKER_01": SpeakerInfo()},
        segments=[
            Segment(id=0, start=1.0, end=3.0, speaker="SPEAKER_00", text="Hola a todos."),
            Segment(id=1, start=3.5, end=5.0, speaker="SPEAKER_01", text="Buenas {tardes}."),
        ],
    )


def styles_with_speaker_override():
    return StylesConfig(
        default=StyleDef(),
        speaker={"SPEAKER_01": {"color": "#7FD4FF", "position": "top-center"}},
    )


def test_header_uses_video_resolution_and_own_wrapping():
    doc = build_ass(make_transcript(), StylesConfig(), None)
    assert "PlayResX: 1280" in doc and "PlayResY: 720" in doc
    assert "WrapStyle: 2" in doc
    assert "ScaledBorderAndShadow: yes" in doc


def test_speaker_override_gets_own_style_and_alignment():
    doc = build_ass(make_transcript(), styles_with_speaker_override(), None)
    style_lines = [l for l in doc.splitlines() if l.startswith("Style: ")]
    names = [l.split(":", 1)[1].split(",")[0].strip() for l in style_lines]
    assert names == ["Default", "S_SPEAKER_01"]
    s01 = next(l for l in style_lines if "S_SPEAKER_01" in l)
    fields = s01.split(",")
    assert fields[19 - 1].strip() == "8"  # Alignment field = top-center


def test_dialogue_lines_carry_speaker_names_and_escaped_braces():
    doc = build_ass(make_transcript(), styles_with_speaker_override(), None)
    dialogues = [l for l in doc.splitlines() if l.startswith("Dialogue: ")]
    assert len(dialogues) == 2
    assert ",María," in dialogues[0]
    assert r"\{tardes\}" in dialogues[1]


def test_explicit_xy_position_emits_pos_override():
    styles = StylesConfig(default=StyleDef(position={"x": 640, "y": 650}))
    doc = build_ass(make_transcript(), styles, None)
    assert "{\\pos(640,650)}" in doc


def test_background_disabled_uses_stroke_outline():
    styles = StylesConfig(default=StyleDef.model_validate({"background": {"enabled": False}, "stroke": {"width": 2.5}}))
    doc = build_ass(make_transcript(), styles, None)
    default = next(l for l in doc.splitlines() if l.startswith("Style: Default"))
    fields = default.split(",")
    assert fields[16 - 1].strip() == "1"  # BorderStyle=1 (outline, no box)
    assert fields[17 - 1].strip() == "2.5"  # Outline = stroke width


def test_central_styles_toml_is_the_full_reference():
    from subtitle_studio.subtitles.styleconf import (
        Background,
        Glow,
        Margin,
        Padding,
        Shadow,
        Stroke,
        StyleDef,
        load_styles,
    )

    with open("styles.toml", "rb") as f:
        raw = tomllib.load(f)
    default = raw["default"]
    # every supported key is present and documented in the reference [default]
    assert set(default) == set(StyleDef.model_fields) - {"position"}
    # including every nested key of every table value
    for key, model in [
        ("stroke", Stroke), ("glow", Glow), ("shadow", Shadow),
        ("background", Background), ("margin", Margin),
    ]:
        assert set(default[key]) == set(model.model_fields), key
    assert set(default["background"]["padding"]) == set(Padding.model_fields)
    assert raw["meta"]["play_res"] == "video"
    # and the whole file validates into the model
    config = load_styles("styles.toml")
    assert config.default.size == 56 and config.default.background.enabled
