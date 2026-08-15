import pytest

from subtitle_studio.subtitles.colors import parse_hex, to_ass


def test_rgb_to_ass_reorders_and_opaque_alpha():
    # white, no alpha given -> fully opaque = ASS alpha 00
    assert to_ass("#FFFFFF") == "&H00FFFFFF"
    # pure red -> BGR order puts red last
    assert to_ass("#FF0000") == "&H000000FF"


def test_alpha_is_inverted():
    # CSS AA=AA (semi-transparent) -> ASS alpha 255-0xAA = 0x55
    assert to_ass("#000000AA") == "&H55000000"
    # fully transparent CSS 00 -> ASS FF
    assert to_ass("#12345600").startswith("&HFF")


def test_parse_and_reject():
    assert parse_hex("#7FD4FF") == (0x7F, 0xD4, 0xFF, 255)
    with pytest.raises(ValueError):
        to_ass("red")
    with pytest.raises(ValueError):
        to_ass("#FFF")
