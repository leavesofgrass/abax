"""Cartesian SVG chart generators — structural tests (pure stdlib)."""

from __future__ import annotations

from abax.core.science import chartsvg


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


# --- box_svg ---------------------------------------------------------------

def test_box_svg_structure_and_outliers():
    # 100 is a clear outlier beyond 1.5*IQR of the first series.
    series = [
        ("A", [1, 2, 3, 4, 5, 100]),
        ("B", [2, 3, 4, 5, 6]),
    ]
    svg = chartsvg.box_svg(series, title="Box")
    _is_svg(svg)
    assert "Box" in svg
    # A box plot has both rects (the Q1..Q3 boxes) and lines (median/whiskers).
    assert "<rect" in svg and "<line" in svg
    # background + border + one box rect per series.
    assert svg.count("<rect") == 2 + len(series)
    # The outlier in series A is drawn as a dot.
    assert svg.count("<circle") >= 1
    for name in ("A", "B"):
        assert name in svg


def test_box_svg_empty():
    svg = chartsvg.box_svg([])
    _is_svg(svg)
    assert svg.count("<rect") == 2  # only background + border, no boxes
    assert "<line" in svg


def test_box_svg_single_value_series():
    # Degenerate: a one-value series must not raise and draws a (flat) box.
    svg = chartsvg.box_svg([("solo", [5.0])])
    _is_svg(svg)
    assert svg.count("<rect") == 3


# --- violin_svg ------------------------------------------------------------

def test_violin_svg_structure():
    series = [
        ("A", [1, 2, 2, 3, 3, 3, 4, 5]),
        ("B", [2, 3, 4, 5, 6, 7]),
    ]
    svg = chartsvg.violin_svg(series, title="Violin")
    _is_svg(svg)
    assert "Violin" in svg
    # One closed silhouette path per series (mirrored density).
    assert svg.count("<path") == len(series)
    assert " Z" in svg  # path is closed
    assert "<line" in svg  # axis ticks + median lines


def test_violin_svg_empty():
    svg = chartsvg.violin_svg([])
    _is_svg(svg)
    assert svg.count("<path") == 0
    assert "<line" in svg


# --- qq_svg ----------------------------------------------------------------

def test_qq_svg_points_and_reference_line():
    values = [float(i) for i in range(1, 21)]
    svg = chartsvg.qq_svg(values, title="QQ")
    _is_svg(svg)
    assert "QQ" in svg
    # One dot per sample value.
    assert svg.count("<circle") == len(values)
    # The reference line is the only dashed line in the plot.
    assert "stroke-dasharray" in svg


def test_qq_svg_empty():
    svg = chartsvg.qq_svg([])
    _is_svg(svg)
    assert svg.count("<circle") == 0
    # Reference line is still emitted (degenerate range).
    assert "stroke-dasharray" in svg


# --- ecdf_svg --------------------------------------------------------------

def test_ecdf_svg_steps_and_legend():
    series = [
        ("A", [1, 2, 3, 4, 5]),
        ("B", [2, 4, 6]),
    ]
    svg = chartsvg.ecdf_svg(series, title="ECDF")
    _is_svg(svg)
    assert "ECDF" in svg
    # One step path per series.
    assert svg.count("<path") == len(series)
    # Legend swatches: background + border + one swatch per series.
    assert svg.count("<rect") == 2 + len(series)
    for name in ("A", "B"):
        assert name in svg


def test_ecdf_svg_empty():
    svg = chartsvg.ecdf_svg([])
    _is_svg(svg)
    assert svg.count("<path") == 0
    assert "<line" in svg


# --- heatmap_svg -----------------------------------------------------------

def test_heatmap_svg_cells_and_labels():
    matrix = [
        [1.0, 0.5, 0.2],
        [0.5, 1.0, 0.1],
        [0.2, 0.1, 1.0],
    ]
    labels = ["x", "y", "z"]
    svg = chartsvg.heatmap_svg(matrix, labels=labels, title="Corr")
    _is_svg(svg)
    assert "Corr" in svg
    # 9 data cells + a multi-step colour scale => many rects.
    assert svg.count("<rect") > 9
    # viridis colours are emitted as rgb(...) fills.
    assert "rgb(" in svg
    for lab in labels:
        assert lab in svg


def test_heatmap_svg_no_labels():
    svg = chartsvg.heatmap_svg([[1, 2], [3, 4]])
    _is_svg(svg)
    assert svg.count("<rect") > 4  # 4 cells + scale bar
    assert "rgb(" in svg


def test_heatmap_svg_empty():
    svg = chartsvg.heatmap_svg([])
    _is_svg(svg)
    # No cells and no colour scale for empty input (only frame rects).
    assert svg.count("<rect") == 2
    assert "rgb(" not in svg


# --- shared structural checks ----------------------------------------------

def test_default_dimensions():
    svg = chartsvg.line_svg([("a", [(0, 0), (1, 1)])])
    assert 'width="480"' in svg
    assert 'height="320"' in svg


def test_new_charts_default_dimensions():
    for svg in (
        chartsvg.box_svg([("a", [1, 2, 3])]),
        chartsvg.violin_svg([("a", [1, 2, 3])]),
        chartsvg.qq_svg([1, 2, 3, 4]),
        chartsvg.ecdf_svg([("a", [1, 2, 3])]),
        chartsvg.heatmap_svg([[1, 2], [3, 4]]),
    ):
        assert 'width="480"' in svg
        assert 'height="320"' in svg
