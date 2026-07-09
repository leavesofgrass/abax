"""Tests for the business/executive SVG chart renderers in chartsvg."""

from __future__ import annotations

from abax.core.science.chartsvg import (
    sparkline_svg,
    sunburst_svg,
    treemap_svg,
    waterfall_svg,
)


def _count(svg: str, tag: str) -> int:
    return svg.count("<" + tag)


# --- waterfall --------------------------------------------------------------

def test_waterfall_basic():
    svg = waterfall_svg(["A", "B", "C"], [10.0, -4.0, 6.0], total=True)
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    # 3 delta bars + 1 total bar + the frame background + border rects.
    assert _count(svg, "rect") == 3 + 1 + 2


def test_waterfall_no_total():
    svg = waterfall_svg(["A", "B"], [5.0, 3.0], total=False)
    assert svg.startswith("<svg")
    # 2 delta bars + background + border, no total bar.
    assert _count(svg, "rect") == 2 + 2


def test_waterfall_empty():
    svg = waterfall_svg([], [])
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")


# --- sunburst ---------------------------------------------------------------

def test_sunburst_basic():
    tree = {
        "name": "root",
        "children": [
            {"name": "a", "children": [
                {"name": "a1", "value": 3},
                {"name": "a2", "value": 1},
            ]},
            {"name": "b", "value": 4},
        ],
    }
    svg = sunburst_svg(tree)
    assert svg.startswith("<svg")
    # ring segments: a, b (depth 0) + a1, a2 (depth 1) = 4 paths.
    assert _count(svg, "path") == 4


def test_sunburst_empty():
    assert sunburst_svg({}).startswith("<svg")
    assert sunburst_svg({"name": "x"}).startswith("<svg")
    assert sunburst_svg(None).startswith("<svg")  # type: ignore[arg-type]
    # No children -> no ring segments.
    assert _count(sunburst_svg({"name": "x", "value": 1}), "path") == 0


# --- treemap ----------------------------------------------------------------

def test_treemap_basic():
    svg = treemap_svg([("A", 5.0), ("B", 3.0), ("C", 2.0)])
    assert svg.startswith("<svg")
    # background rect + 3 cell rects.
    assert _count(svg, "rect") == 1 + 3


def test_treemap_dict_items():
    svg = treemap_svg([{"name": "A", "value": 5}, {"name": "B", "value": 5}])
    assert svg.startswith("<svg")
    assert _count(svg, "rect") == 1 + 2


def test_treemap_empty_and_degenerate():
    assert treemap_svg([]).startswith("<svg")
    # All non-positive -> dropped, only the background rect remains.
    svg = treemap_svg([("A", 0.0), ("B", -1.0)])
    assert svg.startswith("<svg")
    assert _count(svg, "rect") == 1


# --- sparkline --------------------------------------------------------------

def test_sparkline_basic():
    svg = sparkline_svg([1.0, 3.0, 2.0, 5.0, 4.0])
    assert svg.startswith("<svg")
    assert _count(svg, "polyline") == 1
    assert _count(svg, "circle") == 1  # last-point marker


def test_sparkline_no_marker():
    svg = sparkline_svg([1.0, 2.0, 3.0], marker=False)
    assert _count(svg, "polyline") == 1
    assert _count(svg, "circle") == 0


def test_sparkline_flat_and_empty():
    # All-equal values must not divide by zero.
    flat = sparkline_svg([2.0, 2.0, 2.0])
    assert flat.startswith("<svg")
    assert _count(flat, "polyline") == 1
    # Empty -> valid SVG, no polyline.
    empty = sparkline_svg([])
    assert empty.startswith("<svg")
    assert _count(empty, "polyline") == 0
