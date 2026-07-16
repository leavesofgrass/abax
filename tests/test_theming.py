"""GUI theme presets: every one renders, and the pickers stay in sync."""

from __future__ import annotations

import re

from abax.gui import theming

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_every_preset_has_valid_hex_tokens():
    for name, theme in theming.PRESETS.items():
        for key, value in theme.tokens().items():
            assert _HEX.match(value), f"{name}.{key} = {value!r} is not #rrggbb"


def test_every_preset_formats_through_galaxy_qss():
    """apply_theme() formats galaxy.qss with a theme's tokens — no missing keys."""
    template = theming._read_qss("galaxy")
    for name, theme in theming.PRESETS.items():
        # Raises KeyError/IndexError if a token is missing; the assert is the run.
        assert template.format(**theme.tokens())


def test_new_ide_themes_present():
    for key in ("dracula", "tokyo_night", "gruvbox_dark", "monokai"):
        assert key in theming.PRESETS


def test_theme_for_falls_back_to_default():
    assert theming.theme_for("no_such_theme") == theming.Theme()
    assert theming.theme_for("dracula") is theming.PRESETS["dracula"]


def test_pickers_cover_exactly_the_presets():
    """The Preferences list and the theme chooser must offer every preset — and
    nothing that isn't a preset — so a new theme can never be half-registered."""
    from abax.gui.dialogs.preferences_dialog import _THEMES
    from abax.gui.dialogs.theme_dialog import _NICE

    preset_keys = set(theming.PRESETS)
    assert {k for k, _label in _THEMES} == preset_keys
    assert set(_NICE) == preset_keys
