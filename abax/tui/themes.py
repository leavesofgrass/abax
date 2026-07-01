"""TUI colour themes (role → (index256, index8)) and hex→palette mapping."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TuiTheme:
    name: str
    roles: dict  # role -> (index256, index8)

    def color(self, role: str, cap: str) -> int:
        idx256, idx8 = self.roles.get(role, (7, 7))
        return idx256 if cap == "256" else idx8


THEMES = {
    "mono": TuiTheme("mono", {}),  # attribute-only
    "obsidian": TuiTheme(
        "obsidian",
        {
            "lcd": (189, 7),
            "frame": (240, 7),
            "label": (146, 6),
            "dim": (244, 7),
            "accent": (99, 5),
            "banner": (183, 5),
            "cursor": (99, 3),
        },
    ),
    "hacker": TuiTheme(
        "hacker",
        {
            "lcd": (46, 2),
            "frame": (22, 2),
            "label": (40, 2),
            "dim": (28, 2),
            "accent": (118, 2),
            "banner": (46, 2),
            "cursor": (46, 2),
        },
    ),
    "phosphor": TuiTheme(
        "phosphor",
        {
            "lcd": (214, 3),
            "frame": (130, 3),
            "label": (208, 3),
            "dim": (94, 3),
            "accent": (220, 3),
            "banner": (214, 3),
            "cursor": (214, 3),
        },
    ),
    "solarized": TuiTheme(
        "solarized",
        {
            "lcd": (245, 7), "frame": (240, 7), "label": (33, 4), "dim": (240, 7),
            "accent": (33, 4), "banner": (100, 2), "cursor": (33, 4),
        },
    ),
    "nord": TuiTheme(
        "nord",
        {
            "lcd": (188, 7), "frame": (240, 7), "label": (110, 6), "dim": (244, 7),
            "accent": (110, 6), "banner": (151, 6), "cursor": (67, 4),
        },
    ),
    "dark_one": TuiTheme(
        "dark_one",
        {
            "lcd": (250, 7), "frame": (240, 7), "label": (75, 4), "dim": (243, 7),
            "accent": (75, 4), "banner": (114, 2), "cursor": (75, 4),
        },
    ),
    "crt_green": TuiTheme(
        "crt_green",
        {
            "lcd": (48, 2), "frame": (22, 2), "label": (40, 2), "dim": (28, 2),
            "accent": (83, 2), "banner": (48, 2), "cursor": (48, 2),
        },
    ),
    "crt_amber": TuiTheme(
        "crt_amber",
        {
            "lcd": (214, 3), "frame": (130, 3), "label": (208, 3), "dim": (94, 3),
            "accent": (220, 3), "banner": (214, 3), "cursor": (214, 3),
        },
    ),
}


def _hex_to_256(hexc: str) -> int:
    """Nearest xterm-256 color index for a ``#rrggbb`` string."""
    r, g, b = int(hexc[1:3], 16), int(hexc[3:5], 16), int(hexc[5:7], 16)
    if abs(r - g) < 12 and abs(g - b) < 12:  # grayscale ramp
        if r < 8:
            return 16
        if r > 248:
            return 231
        return 232 + round((r - 8) / 247 * 24)

    def q(v: int) -> int:
        return 0 if v < 48 else 1 if v < 115 else 2 if v < 155 else 3 if v < 195 else 4 if v < 235 else 5

    return 16 + 36 * q(r) + 6 * q(g) + q(b)


def _hex_to_8(hexc: str) -> int:
    r, g, b = int(hexc[1:3], 16), int(hexc[3:5], 16), int(hexc[5:7], 16)
    return (1 if r > 127 else 0) | (2 if g > 127 else 0) | (4 if b > 127 else 0)
