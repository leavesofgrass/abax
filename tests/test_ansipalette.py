"""ANSI colour resolution — named, hex, default, and bold-brightening."""

from __future__ import annotations

from abax.core.format.ansipalette import resolve

FG = (212, 221, 228)
BG = (12, 16, 20)


def test_default_returns_base():
    assert resolve("default", FG) == FG
    assert resolve("default", BG) == BG
    assert resolve("", FG) == FG


def test_named_colors():
    assert resolve("red", FG) == (205, 49, 49)
    assert resolve("brown", FG) == (229, 229, 16)  # ANSI yellow
    assert resolve("cyan", FG) == (17, 168, 205)


def test_hex_truecolor_and_256():
    assert resolve("ff8700", FG) == (255, 135, 0)
    assert resolve("0a141e", FG) == (10, 20, 30)


def test_bold_brightens_base_colors():
    assert resolve("red", FG, bold=True) == (241, 76, 76)
    assert resolve("green", FG, bold=True) == (35, 209, 139)
    # a hex colour is unaffected by bold
    assert resolve("ff8700", FG, bold=True) == (255, 135, 0)


def test_unknown_name_falls_back():
    assert resolve("chartreuse", FG) == FG
    assert resolve("xyz", BG) == BG
