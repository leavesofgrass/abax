"""ANSI / xterm colour resolution for the terminal view (stdlib-only, Qt-free).

``pyte`` hands us per-cell ``fg``/``bg`` already normalised to either the sentinel
``"default"``, one of the named ANSI colours, or a 6-hex-digit string (it collapses
256-colour and true-colour SGR into hex). This module turns those into ``(r, g, b)``
tuples against a base fg/bg, applying the "bold brightens the 8 base colours"
convention. Kept in ``core`` so it is unit-testable without Qt.
"""

from __future__ import annotations

# A modern, readable 16-colour palette (VS Code "Dark+" ANSI values).
ANSI_16: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "red": (205, 49, 49),
    "green": (13, 188, 121),
    "brown": (229, 229, 16),       # pyte names ANSI-yellow "brown"
    "yellow": (229, 229, 16),
    "blue": (36, 114, 200),
    "magenta": (188, 63, 188),
    "cyan": (17, 168, 205),
    "white": (229, 229, 229),
    "brightblack": (102, 102, 102),
    "brightred": (241, 76, 76),
    "brightgreen": (35, 209, 139),
    "brightbrown": (245, 245, 67),
    "brightyellow": (245, 245, 67),
    "brightblue": (59, 142, 234),
    "brightmagenta": (214, 112, 214),
    "brightcyan": (41, 184, 219),
    "brightwhite": (255, 255, 255),
}


def _is_hex6(s: str) -> bool:
    if len(s) != 6:
        return False
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def resolve(color: str, default: tuple[int, int, int],
            bold: bool = False) -> tuple[int, int, int]:
    """Resolve a pyte colour string to an ``(r, g, b)`` tuple.

    ``default`` is returned for the ``"default"`` sentinel (pass the view's fg for
    foreground cells, its bg for background cells). 6-hex strings parse directly.
    Named base colours brighten under ``bold`` when a ``bright*`` variant exists.
    """
    if not color or color == "default":
        return default
    if _is_hex6(color):
        return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))
    name = color
    if bold and ("bright" + name) in ANSI_16:
        name = "bright" + name
    return ANSI_16.get(name, default)
