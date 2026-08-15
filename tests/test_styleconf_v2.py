import pytest

from subtitle_studio.subtitles.styleconf import load_styles, parse_position


def write_styles(tmp_path):
    p = tmp_path / "styles.toml"
    p.write_text(
        """
[default]
font = "Roboto"
size = 50
background = { enabled = true, color = "#000000AA", padding = 14 }

[style.neon]
uppercase = true
glow = { enabled = true, color = "#00D5FF" }
background = { rounded = true, radius = 20.0 }

[speaker.SPEAKER_01]
color = "#7FD4FF"
""",
        encoding="utf-8",
    )
    return p


def test_int_padding_shorthand_expands(tmp_path):
    styles = load_styles(write_styles(tmp_path))
    assert styles.default.background.padding.x == 14
    assert styles.default.background.padding.y > 0


def test_preset_merges_over_default(tmp_path):
    styles = load_styles(write_styles(tmp_path))
    neon = styles.base("neon")
    assert neon.uppercase is True
    assert neon.glow.enabled and neon.glow.color == "#00D5FF"
    assert neon.background.rounded and neon.background.radius == 20.0
    assert neon.font == "Roboto" and neon.size == 50  # inherited from default


def test_unknown_preset_lists_available(tmp_path):
    styles = load_styles(write_styles(tmp_path))
    with pytest.raises(ValueError, match="neon"):
        styles.base("nope")


def test_speaker_override_applies_on_top_of_preset(tmp_path):
    styles = load_styles(write_styles(tmp_path))
    name, style = styles.resolve("SPEAKER_01", None, preset="neon")
    assert name == "S_SPEAKER_01"
    assert style.color == "#7FD4FF"      # speaker wins
    assert style.uppercase is True       # preset preserved


def test_meta_default_preset(tmp_path):
    p = tmp_path / "styles.toml"
    p.write_text(
        """
[meta]
play_res = "video"
default_preset = "neon"

[style.neon]
uppercase = true
""",
        encoding="utf-8",
    )
    styles = load_styles(p)
    assert styles.default_preset == "neon"
    assert styles.base(styles.default_preset).uppercase is True


def test_parse_position():
    assert parse_position("top-center") == "top-center"
    assert parse_position("640, 650") == {"x": 640, "y": 650}
    with pytest.raises(ValueError):
        parse_position("center-bottom")
