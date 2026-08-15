import subtitle_studio.stages.style as style_stage
from subtitle_studio.stages.style import resolve_styles_path


def test_search_order(tmp_path, monkeypatch):
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    video = video_dir / "clip.mp4"
    video.touch()
    central_root = tmp_path / "project"
    central_root.mkdir()
    user_file = tmp_path / "xdg" / "styles.toml"
    monkeypatch.setattr(style_stage, "project_root", lambda: central_root)
    monkeypatch.setattr(style_stage, "user_styles_path", lambda: user_file)

    # nothing anywhere -> defaults
    assert resolve_styles_path(None, video) is None

    # user config is the last fallback
    user_file.parent.mkdir(parents=True)
    user_file.write_text("[default]\n")
    assert resolve_styles_path(None, video) == user_file

    # the central project file beats the user config
    central = central_root / "styles.toml"
    central.write_text("[default]\n")
    assert resolve_styles_path(None, video) == central

    # a per-video file beats the central one
    per_video = video_dir / "styles.toml"
    per_video.write_text("[default]\n")
    assert resolve_styles_path(None, video) == per_video

    # explicit --styles beats everything
    explicit = tmp_path / "special.toml"
    explicit.write_text("[default]\n")
    assert resolve_styles_path(explicit, video) == explicit


def test_project_root_finds_repo():
    root = style_stage.project_root()
    assert root is not None and (root / "pyproject.toml").exists()
