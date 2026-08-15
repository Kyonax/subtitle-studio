"""Color conversion: config `#RRGGBB[AA]` -> ASS `&HAABBGGRR`.

ASS byte order is blue-green-red, and its alpha is INVERTED relative to CSS:
ASS 00 = opaque, FF = transparent, while config AA follows CSS (FF = opaque).
"""

from __future__ import annotations

import re

_HEX = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def parse_hex(color: str) -> tuple[int, int, int, int]:
    """-> (r, g, b, css_alpha 0-255, 255 = opaque)."""
    m = _HEX.match(color.strip())
    if not m:
        raise ValueError(f"invalid color {color!r} (expected #RRGGBB or #RRGGBBAA)")
    value = m.group(1)
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    a = int(value[6:8], 16) if len(value) == 8 else 255
    return r, g, b, a


def to_ass(color: str) -> str:
    r, g, b, a = parse_hex(color)
    return f"&H{255 - a:02X}{b:02X}{g:02X}{r:02X}"
