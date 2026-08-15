from pathlib import Path

from subtitle_studio.preview import render_style_preview


def test_preview_renders_png_without_a_video(tmp_path):
    styles = tmp_path / "styles.toml"
    styles.write_text(
        """
[default]
color = "#F9CD26"
background = { enabled = true, rounded = true, radius = 20.0 }
""",
        encoding="utf-8",
    )
    out = render_style_preview(styles, width=640, height=360, out_png=tmp_path / "p.png")
    assert out.exists() and out.stat().st_size > 1000


def test_preview_with_defaults_and_position(tmp_path):
    out = render_style_preview(None, position="top-center", width=640, height=360, out_png=tmp_path / "p.png")
    assert out.exists()
