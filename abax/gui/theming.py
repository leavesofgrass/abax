"""Dual-surface theming: QSS for standard widgets, Theme dataclass for paint.

Both surfaces derive from the same token dict — one source of truth (spec §9).
``apply_theme`` formats a ``.qss`` file with the token dict; custom-painted
widgets receive the ``Theme`` object directly and call ``q_color``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from pathlib import Path

THEMES_DIR = Path(__file__).parent / "themes"


@dataclass(frozen=True)
class Theme:
    bg_primary: str = "#1e1e2e"
    bg_secondary: str = "#181825"
    bg_tertiary: str = "#313244"
    fg_primary: str = "#cdd6f4"
    fg_secondary: str = "#6c7086"
    accent: str = "#7c3aed"
    border: str = "#45475a"
    success: str = "#a6e3a1"
    warning: str = "#f9e2af"
    error: str = "#f38ba8"

    def tokens(self) -> dict:
        """Token dict for QSS ``format()`` — drives both surfaces."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def q_color(self, attr: str):
        from ._qtcompat import QColor

        return QColor(getattr(self, attr))


# A couple of named presets that match the QSS files in themes/.
LIGHT = Theme(
    bg_primary="#ffffff",
    bg_secondary="#f0f0f0",
    bg_tertiary="#e0e0e0",
    fg_primary="#1e1e1e",
    fg_secondary="#6c7086",
    accent="#7c3aed",
    border="#cccccc",
)

HIGH_CONTRAST = Theme(
    bg_primary="#111111",
    bg_secondary="#000000",
    bg_tertiary="#222222",
    fg_primary="#ffffff",
    fg_secondary="#dddddd",
    accent="#ffff00",
    border="#ffffff",
)

# Dark themes matching the star / qv ecosystem palettes. apply_theme() renders
# any of these through galaxy.qss (token-based) — no per-theme .qss needed.
NORD = Theme(
    bg_primary="#2e3440", bg_secondary="#272b35", bg_tertiary="#3b4252",
    fg_primary="#d8dee9", fg_secondary="#7b88a1", accent="#88c0d0",
    border="#434c5e", success="#a3be8c", warning="#ebcb8b", error="#bf616a",
)

DARK_ONE = Theme(  # Atom/One Dark
    bg_primary="#282c34", bg_secondary="#21252b", bg_tertiary="#2c313a",
    fg_primary="#abb2bf", fg_secondary="#5c6370", accent="#61afef",
    border="#3e4451", success="#98c379", warning="#e5c07b", error="#e06c75",
)

SOLARIZED = Theme(  # Solarized Dark
    bg_primary="#002b36", bg_secondary="#073642", bg_tertiary="#0a4a59",
    fg_primary="#93a1a1", fg_secondary="#586e75", accent="#268bd2",
    border="#0e5160", success="#859900", warning="#b58900", error="#dc322f",
)

# CRT phosphor emulations. #0a... backgrounds (not pure black) avoid halation.
CRT_GREEN = Theme(  # P1 green phosphor
    bg_primary="#0a120a", bg_secondary="#050805", bg_tertiary="#0f1f0f",
    fg_primary="#33ff66", fg_secondary="#1aa31a", accent="#7dff7d",
    border="#1f5f1f", success="#33ff66", warning="#ffd633", error="#ff5555",
)

CRT_AMBER = Theme(  # P3 amber phosphor
    bg_primary="#140d00", bg_secondary="#0a0600", bg_tertiary="#1f1500",
    fg_primary="#ffb000", fg_secondary="#b37a00", accent="#ffd060",
    border="#5c3f00", success="#ffb000", warning="#ffd633", error="#ff6b3d",
)

# Popular open-source IDE / editor palettes, mapped onto the token set. All render
# through galaxy.qss (token-based), so no per-theme .qss is needed.
DRACULA = Theme(  # dracula-theme.com
    bg_primary="#282a36", bg_secondary="#21222c", bg_tertiary="#343746",
    fg_primary="#f8f8f2", fg_secondary="#6272a4", accent="#bd93f9",
    border="#44475a", success="#50fa7b", warning="#f1fa8c", error="#ff5555",
)

TOKYO_NIGHT = Theme(  # folke/tokyonight
    bg_primary="#1a1b26", bg_secondary="#16161e", bg_tertiary="#292e42",
    fg_primary="#c0caf5", fg_secondary="#565f89", accent="#7aa2f7",
    border="#3b4261", success="#9ece6a", warning="#e0af68", error="#f7768e",
)

GRUVBOX_DARK = Theme(  # morhetz/gruvbox (dark, medium)
    bg_primary="#282828", bg_secondary="#1d2021", bg_tertiary="#3c3836",
    fg_primary="#ebdbb2", fg_secondary="#928374", accent="#83a598",
    border="#504945", success="#b8bb26", warning="#fabd2f", error="#fb4934",
)

MONOKAI = Theme(  # classic Sublime/TextMate Monokai
    bg_primary="#272822", bg_secondary="#1e1f1c", bg_tertiary="#3e3d32",
    fg_primary="#f8f8f2", fg_secondary="#75715e", accent="#66d9ef",
    border="#49483e", success="#a6e22e", warning="#e6db74", error="#f92672",
)

PRESETS = {
    "galaxy": Theme(),
    "light": LIGHT,
    "high_contrast": HIGH_CONTRAST,
    "nord": NORD,
    "dark_one": DARK_ONE,
    "solarized": SOLARIZED,
    "crt_green": CRT_GREEN,
    "crt_amber": CRT_AMBER,
    "dracula": DRACULA,
    "tokyo_night": TOKYO_NIGHT,
    "gruvbox_dark": GRUVBOX_DARK,
    "monokai": MONOKAI,
}


def theme_for(name: str) -> Theme:
    return PRESETS.get(name, Theme())


def _read_qss(name: str) -> str:
    """Read a bundled ``.qss`` theme, working from source AND from the .pyz.

    Uses ``importlib.resources`` so the stylesheet loads whether it lives on the
    filesystem or inside the zipapp archive (a plain ``Path.read_text`` fails on a
    zip-internal path).
    """
    from importlib.resources import files

    base = files("abax.gui").joinpath("themes")
    target = base.joinpath(f"{name}.qss")
    if not target.is_file():
        target = base.joinpath("galaxy.qss")
    return target.read_text(encoding="utf-8")


def apply_theme(app, name: str, tokens: dict, extra_qss: str = "") -> None:
    app.setStyleSheet(_read_qss(name).format(**tokens) + extra_qss)


def from_obsidian_css(css: str) -> Theme:
    """Parse ``--color-*`` CSS variables from an Obsidian theme file."""
    vars = {m.group(1): m.group(2) for m in re.finditer(r"--(color-[\w-]+):\s*(#[0-9a-fA-F]+)", css)}
    return Theme(
        bg_primary=vars.get("color-base-00", "#1e1e2e"),
        accent=vars.get("color-accent", "#7c3aed"),
    )


def from_zed_json(data: dict) -> Theme:
    """Parse a Zed JSON theme file."""
    style = data.get("themes", [{}])[0].get("style", {})
    return Theme(
        bg_primary=style.get("background", "#1e1e2e"),
        accent=style.get("border_focused", "#7c3aed"),
    )
