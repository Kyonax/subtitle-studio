from subtitle_studio.schema import Segment, SourceInfo, Transcript, Word
from subtitle_studio.subtitles.ass_builder import build_ass
from subtitle_studio.subtitles.layout import segment_events
from subtitle_studio.subtitles.styleconf import StyleDef, StylesConfig


def transcript():
    return Transcript(
        source=SourceInfo(media_path="/x.mkv"),
        language="es",
        segments=[Segment(id=0, start=1.0, end=3.0, text="Hola a todos los presentes.")],
    )


def styles_with(**default_overrides):
    return StylesConfig(default=StyleDef.model_validate(default_overrides))


def test_rounded_background_emits_drawing_layer():
    styles = styles_with(background={"enabled": True, "rounded": True, "radius": 18.0, "color": "#101018CC"})
    doc = build_ass(transcript(), styles, None)
    dialogues = [line for line in doc.splitlines() if line.startswith("Dialogue: ")]
    assert len(dialogues) == 2  # box layer + text layer
    box, text = dialogues
    assert box.startswith("Dialogue: 0,") and "\\p1}m " in box and " b " in box
    assert text.startswith("Dialogue: 2,") and "\\pos(" in text
    # rounded mode keeps the real stroke on the text style (BorderStyle=1)
    style_line = next(line for line in doc.splitlines() if line.startswith("Style: Default"))
    assert style_line.split(",")[15].strip() == "1"


def test_glow_emits_blurred_middle_layer():
    styles = styles_with(
        background={"enabled": False},
        glow={"enabled": True, "color": "#00D5FF", "radius": 7.0, "size": 2.0},
        stroke={"width": 3.0},
    )
    doc = build_ass(transcript(), styles, None)
    dialogues = [line for line in doc.splitlines() if line.startswith("Dialogue: ")]
    assert len(dialogues) == 2  # glow + text
    glow, text = dialogues
    assert glow.startswith("Dialogue: 1,") and "\\blur7" in glow and "\\bord5" in glow
    assert "\\1a&HFF&" in glow  # transparent fill, only the halo shows
    assert text.startswith("Dialogue: 2,")


def test_letter_spacing_scale_and_uppercase():
    styles = styles_with(letter_spacing=1.5, scale_x=110, uppercase=True)
    doc = build_ass(transcript(), styles, None)
    style_line = next(line for line in doc.splitlines() if line.startswith("Style: Default"))
    fields = style_line.split(",")
    assert fields[11].strip() == "110"   # ScaleX
    assert fields[13].strip() == "1.5"   # Spacing
    # end_period defaults to false, so the closing full stop is gone
    assert "HOLA A TODOS LOS PRESENTES" in doc
    assert "PRESENTES." not in doc


def test_square_box_still_borderstyle_4():
    styles = styles_with(background={"enabled": True, "rounded": False, "padding": 12})
    doc = build_ass(transcript(), styles, None)
    style_line = next(line for line in doc.splitlines() if line.startswith("Style: Default"))
    assert style_line.split(",")[15].strip() == "4"


def test_max_words_splits_events():
    words = [Word(word=w, start=float(i), end=float(i) + 0.9)
             for i, w in enumerate("uno dos tres cuatro cinco seis".split())]
    seg = Segment(id=0, start=0.0, end=5.9, text=" ".join(w.word for w in words), words=words)
    events = segment_events(seg, max_line_chars=100, max_lines=2, max_words=2)
    assert len(events) == 3
    assert all(len(e.lines[0].split()) + sum(len(line.split()) for line in e.lines[1:]) <= 2 for e in events)
