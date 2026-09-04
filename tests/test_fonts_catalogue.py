"""The font catalogue behind the searchable picker, and what resolve_font accepts.

Every test pins system_fonts() to a fixed list — the real one is whatever this
machine has installed, which is not a thing to assert against.
"""

import pytest

import subtitle_studio.subtitles.fonts as fonts_mod
from subtitle_studio.subtitles.fonts import (
    FontNotFoundError,
    available_fonts,
    resolve_font,
    system_fonts,
)

INSTALLED = ["DejaVu Sans", "DejaVu Sans Mono", "Roboto", "Zed Mono"]


@pytest.fixture
def installed(monkeypatch):
    monkeypatch.setattr(fonts_mod, "system_fonts", lambda *a, **k: list(INSTALLED))


@pytest.fixture
def bundled(tmp_path):
    """A fonts dir holding one file whose family name is unreadable, so
    scan_fonts falls back to the stem — no real font binary needed."""
    d = tmp_path / "fonts"
    d.mkdir()
    (d / "Roboto-Regular.ttf").write_bytes(b"not a font")
    return d


def test_catalogue_puts_bundled_first_and_tags_the_source(bundled, installed):
    catalogue = available_fonts(bundled)

    assert catalogue[0] == {"family": "Roboto-Regular", "source": "bundled"}
    assert all(f["source"] == "system" for f in catalogue[1:])
    assert [f["family"] for f in catalogue[1:]] == INSTALLED


def test_a_bundled_family_wins_the_dedupe(bundled, installed, monkeypatch):
    """The bundled copy travels with the project, so it is the one a style
    should name — the system entry of the same family is dropped."""
    monkeypatch.setattr(fonts_mod, "system_fonts", lambda *a, **k: ["Roboto-Regular", "Zed Mono"])

    catalogue = available_fonts(bundled)

    assert [f["family"] for f in catalogue] == ["Roboto-Regular", "Zed Mono"]
    assert catalogue[0]["source"] == "bundled"


def test_catalogue_without_a_fonts_dir_is_the_system_alone(installed):
    assert [f["family"] for f in available_fonts(None)] == INSTALLED


def test_resolve_prefers_the_bundled_file_over_the_system(bundled, installed):
    # matched on the filename stem, case-insensitively
    assert resolve_font("roboto-regular", bundled) == "Roboto-Regular"


def test_resolve_accepts_an_installed_family(bundled, installed):
    """The picker offers system fonts, so styling one has to work — libass
    resolves them through fontconfig exactly like the bundled ones."""
    assert resolve_font("DejaVu Sans Mono", bundled) == "DejaVu Sans Mono"
    assert resolve_font("dejavu sans mono", bundled) == "DejaVu Sans Mono"


def test_resolve_passes_generic_aliases_through(bundled, installed):
    """fontconfig resolves these itself; they name no file, so no catalogue
    lists them and they must not read as typos."""
    assert resolve_font("sans-serif", bundled) == "sans-serif"
    assert resolve_font("monospace", bundled) == "monospace"


def test_unknown_name_with_a_fonts_dir_is_a_hard_error(bundled, installed):
    """A typo that silently fell back to a default look is the failure this
    guard exists to prevent, so it names what IS available."""
    with pytest.raises(FontNotFoundError) as excinfo:
        resolve_font("Notafont Xyz", bundled)

    message = str(excinfo.value)
    assert "Notafont Xyz" in message
    assert "Roboto-Regular" in message


def test_unknown_name_without_a_fonts_dir_passes_through(installed):
    """Unchanged contract: with no fonts dir configured there is nothing to
    validate against, so the name goes to libass as written."""
    assert resolve_font("Whatever Sans", None) == "Whatever Sans"


def test_system_fonts_survive_a_missing_fontconfig(monkeypatch):
    """No fc-list is not an error — the bundled fonts still work and the
    picker simply has less to offer."""
    monkeypatch.setattr(fonts_mod, "_system_cache", None)
    monkeypatch.setattr(fonts_mod.shutil, "which", lambda _: None)

    assert system_fonts(refresh=True) == []


def test_system_fonts_split_comma_separated_aliases(monkeypatch):
    """`fc-list : family` prints a family and its aliases comma-separated, one
    line per face, so the same name arrives many times over."""
    class Result:
        stdout = "DejaVu Sans,DejaVu Sans Book\nRoboto\nDejaVu Sans\n"

    monkeypatch.setattr(fonts_mod, "_system_cache", None)
    monkeypatch.setattr(fonts_mod.shutil, "which", lambda _: "/usr/bin/fc-list")
    monkeypatch.setattr(fonts_mod.subprocess, "run", lambda *a, **k: Result())

    assert system_fonts(refresh=True) == ["DejaVu Sans", "DejaVu Sans Book", "Roboto"]
