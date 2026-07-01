"""Cartesian SVG chart generators — structural tests (pure stdlib)."""

from __future__ import annotations

from qcell.core.science import chartsvg


def _is_svg(s: str) -> None:
    assert s.startswith("<svg")
    assert s.rstrip().endswith("</svg>")


def _count(s: str, tag: str) -> int:
    return s.count(tag)


# --- line_svg --------------------------------------------------------------

def test_line_svg_basic_and_legend():
    series = [
        ("alpha", [(0, 0), (1, 1), (2, 4)]),
        ("beta", [(0, 1), (1, 2), (2, 3)]),
        ("gamma", [(0, 3), (1, 1), (2, 0)]),
    ]
    svg = chartsvg.line_svg(series, title="My Lines")
    _is_svg(svg)
    # Axis ticks are drawn with <line …>; there must be several.
    assert "<line" in svg
    assert svg.count("<line") >= 8
    # Title text present and escaped normally.
    assert "My Lines" in svg
    # One data path per series.
    assert svg.count("<path") == len(series)
    # One legend entry (a <rect swatch beyond the border rect) per series:
    # legend swatches are the only rects besides background + border.
    assert svg.count("<rect") == 2 + len(series)


def test_line_svg_title_absent_by_default():
    svg = chartsvg.line_svg([("a", [(0, 0), (1, 1)])])
    _is_svg(svg)
    assert "<text" in svg  # tick labels + legend
    # No bold title text element when title omitted.
    assert 'font-weight="bold"' not in svg


def test_line_svg_escapes_names():
    svg = chartsvg.line_svg([("a<b>&c", [(0, 0), (1, 1)])], title="t&<>")
    _is_svg(svg)
    assert "&lt;" in svg and "&amp;" in svg and "&gt;" in svg
    assert "a<b>&c" not in svg
    assert "t&<>" not in svg


def test_line_svg_empty():
    svg = chartsvg.line_svg([])
    _is_svg(svg)
    assert svg.count("<path") == 0  # no data marks
    assert "<line" in svg           # axes still present


# --- bar_svg ---------------------------------------------------------------

def test_bar_svg_bar_count_and_labels():
    cats = ["Q1", "Q2", "Q3", "Q4"]
    vals = [10, 25, 15, 30]
    svg = chartsvg.bar_svg(cats, vals, title="Quarters")
    _is_svg(svg)
    assert "<line" in svg
    assert "Quarters" in svg
    # background + border = 2 rects, plus one bar per category.
    assert svg.count("<rect") == 2 + len(cats)
    for c in cats:
        assert c in svg


def test_bar_svg_empty():
    svg = chartsvg.bar_svg([], [])
    _is_svg(svg)
    assert svg.count("<rect") == 2  # only background + border, no bars
    assert "<line" in svg


# --- scatter_svg -----------------------------------------------------------

def test_scatter_svg_circle_count():
    pts = [(0, 0), (1, 2), (2, 1), (3, 5), (4, 3)]
    svg = chartsvg.scatter_svg(pts, title="Scatter")
    _is_svg(svg)
    assert "<line" in svg
    assert "Scatter" in svg
    assert svg.count("<circle") == len(pts)


def test_scatter_svg_empty():
    svg = chartsvg.scatter_svg([])
    _is_svg(svg)
    assert svg.count("<circle") == 0
    assert "<line" in svg


# --- histogram_svg ---------------------------------------------------------

def test_histogram_svg_bin_count():
    values = [1, 2, 2, 3, 3, 3, 4, 4, 5, 6, 7, 8, 9, 10]
    svg = chartsvg.histogram_svg(values, bins=8, title="Hist")
    _is_svg(svg)
    assert "<line" in svg
    assert "Hist" in svg
    # background + border = 2 rects, plus one bar per bin.
    assert svg.count("<rect") == 2 + 8


def test_histogram_svg_default_bins():
    svg = chartsvg.histogram_svg([float(i) for i in range(50)])
    _is_svg(svg)
    assert svg.count("<rect") == 2 + 10  # default bins == 10


def test_histogram_svg_empty():
    svg = chartsvg.histogram_svg([])
    _is_svg(svg)
    # Empty input draws no bars (only background + border rects).
    assert svg.count("<rect") == 2
    assert "<line" in svg


# --- shared structural checks ----------------------------------------------

def test_default_dimensions():
    svg = chartsvg.line_svg([("a", [(0, 0), (1, 1)])])
    assert 'width="480"' in svg
    assert 'height="320"' in svg
