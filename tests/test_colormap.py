"""Colormap interpolation — endpoints, clamping, midpoints, fallback."""

from __future__ import annotations

from qcell.core.format.colormap import PALETTES, colorize


def test_endpoints_are_exact_stops():
    assert colorize(0.0, 0.0, 1.0, "viridis") == (68, 1, 84)
    assert colorize(1.0, 0.0, 1.0, "viridis") == (253, 231, 37)


def test_clamps_outside_range():
    assert colorize(-5, 0, 1, "viridis") == (68, 1, 84)
    assert colorize(99, 0, 1, "viridis") == (253, 231, 37)


def test_gray_midpoint():
    r, g, b = colorize(0.5, 0.0, 1.0, "gray")
    assert (r, g, b) == (128, 128, 128)


def test_zero_range_returns_first_stop():
    assert colorize(5, 3, 3, "magma") == PALETTES["magma"][0]


def test_unknown_palette_falls_back_to_viridis():
    assert colorize(0.0, 0.0, 1.0, "nope") == (68, 1, 84)


def test_interpolated_value_between_stops():
    # halfway between stop 0 (t=0) and stop 1 (t=0.25) -> t=0.125
    r, g, b = colorize(0.125, 0.0, 1.0, "viridis")
    a, c = PALETTES["viridis"][0], PALETTES["viridis"][1]
    assert r == round(a[0] + (c[0] - a[0]) * 0.5)
    assert g == round(a[1] + (c[1] - a[1]) * 0.5)
