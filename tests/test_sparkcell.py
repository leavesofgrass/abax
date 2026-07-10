"""In-cell SPARKLINE — unicode text fallback, SVG rendering, and the formula."""

from __future__ import annotations

from abax.core.errors import CellError, is_error
from abax.core.sparkcell import Sparkline, _sparkline, register
from abax.core.values import RangeValue

_RAMP = "▁▂▃▄▅▆▇█"


# --- unicode text fallback -------------------------------------------------

def test_line_text_uses_low_to_high_ramp():
    """A monotonic-increasing series maps to the ramp, lowest -> highest char."""
    text = str(Sparkline([1, 2, 3, 4, 5, 6, 7, 8], "line"))
    # Every glyph must come from the block ramp.
    assert all(ch in _RAMP for ch in text)
    # First char is the floor block, last is the ceiling block, and the sequence
    # is non-decreasing across the ramp (a rising trend).
    assert text[0] == _RAMP[0]
    assert text[-1] == _RAMP[-1]
    idxs = [_RAMP.index(ch) for ch in text]
    assert idxs == sorted(idxs)
    assert idxs[0] < idxs[-1]


def test_flat_series_sits_on_mid_ramp():
    text = str(Sparkline([5, 5, 5], "line"))
    # A flat series rests on the mid rung (index (len-1)//2), not the floor.
    assert set(text) == {_RAMP[(len(_RAMP) - 1) // 2]}


def test_winloss_text_glyphs():
    """[1, -1, 0] -> up / down / zero glyphs, in order."""
    text = str(Sparkline([1, -1, 0], "winloss"))
    assert text == "▀▄·"


def test_empty_sparkline_str_is_blank():
    assert str(Sparkline([], "line")) == ""


# --- SVG rendering ---------------------------------------------------------

def test_line_to_svg_has_polyline():
    svg = Sparkline([1, 2, 3, 2, 4], "line").to_svg()
    assert "<svg" in svg
    assert svg.rstrip().endswith("</svg>")
    assert "<polyline" in svg


def test_bar_to_svg_has_rects():
    svg = Sparkline([1, 2, 3], "bar").to_svg()
    assert "<svg" in svg
    assert "<rect" in svg
    # One bar per value.
    assert svg.count("<rect") == 3


def test_winloss_to_svg_has_rects():
    svg = Sparkline([1, -1, 0], "winloss").to_svg()
    assert "<svg" in svg
    assert "<rect" in svg
    assert svg.count("<rect") == 3


# --- the SPARKLINE formula -------------------------------------------------

def test_sparkline_from_list_returns_sparkline():
    result = _sparkline([[1, 2, 3]])
    assert isinstance(result, Sparkline)
    assert result.kind == "line"
    assert result.values == [1.0, 2.0, 3.0]


def test_sparkline_from_rangevalue():
    rng = RangeValue([[1, 2], [3, 4]])
    result = _sparkline([rng])
    assert isinstance(result, Sparkline)
    assert result.values == [1.0, 2.0, 3.0, 4.0]


def test_sparkline_type_and_color_args():
    result = _sparkline([[1, -1, 2], "winloss", "#ff0000"])
    assert isinstance(result, Sparkline)
    assert result.kind == "winloss"
    assert result.color == "#ff0000"
    # "column" is an alias for the bar chart.
    assert _sparkline([[1, 2], "column"]).kind == "bar"


def test_blanks_and_text_are_skipped():
    result = _sparkline([[1, None, "hello", 2, "", 3]])
    assert isinstance(result, Sparkline)
    assert result.values == [1.0, 2.0, 3.0]


def test_empty_numeric_series_is_value_error():
    result = _sparkline([[None, "x", ""]])
    assert is_error(result)
    assert result == CellError(CellError.VALUE)


def test_empty_range_is_value_error():
    result = _sparkline([RangeValue([[]])])
    assert is_error(result)
    assert result == CellError(CellError.VALUE)


def test_unknown_type_is_value_error():
    result = _sparkline([[1, 2, 3], "pie"])
    assert is_error(result)
    assert result == CellError(CellError.VALUE)


def test_error_in_input_propagates():
    err = CellError(CellError.DIV0)
    # An error as the first argument propagates unchanged.
    assert _sparkline([err]) == err
    # An error inside the flattened range propagates too.
    assert _sparkline([[1, err, 3]]) == err


# --- registration ----------------------------------------------------------

def test_register_adds_sparkline():
    table: dict = {}
    register(table)
    assert "SPARKLINE" in table
    assert table["SPARKLINE"] is _sparkline
