"""Tests for the TI-83-style graphing-calculator engine."""

from __future__ import annotations

import pytest

from abax.core.calc.ti_engine import (
    SCREEN_H,
    SCREEN_W,
    STAT_LISTS,
    TIEngine,
    TIError,
    Window,
)


# --- home screen ---------------------------------------------------------
def test_home_eval_basic_and_ans() -> None:
    eng = TIEngine()
    assert eng.home_eval("2+2") == "4"
    assert eng.ans == 4
    assert eng.home_eval("3*Ans") == "12"
    assert eng.ans == 12


def test_home_eval_syntax_error() -> None:
    eng = TIEngine()
    assert eng.home_eval("2+*") == "ERR: SYNTAX"
    # An error must not raise nor corrupt Ans.
    assert eng.ans == 0.0


def test_home_eval_history() -> None:
    eng = TIEngine()
    eng.home_eval("1+1")
    eng.home_eval("2*3")
    hist = eng.history()
    assert hist[-1] == ("2*3", "6")
    assert hist[0] == ("1+1", "2")


def test_home_eval_float_result() -> None:
    eng = TIEngine()
    assert eng.home_eval("1/2") == "0.5"


# --- Y= editor -----------------------------------------------------------
def test_set_and_get_function() -> None:
    eng = TIEngine()
    eng.set_function(1, "X^2")
    assert eng.get_function(1) == "X^2"


def test_set_function_bad_index() -> None:
    eng = TIEngine()
    with pytest.raises(TIError):
        eng.set_function(0, "X")
    with pytest.raises(TIError):
        eng.set_function(11, "X")
    with pytest.raises(TIError):
        eng.get_function(99)


def test_set_function_clear() -> None:
    eng = TIEngine()
    eng.set_function(2, "X+1")
    assert eng.get_function(2) == "X+1"
    eng.set_function(2, "")
    assert eng.get_function(2) == ""


def test_functions_slots() -> None:
    eng = TIEngine()
    assert eng.functions() == [""] * 10
    eng.set_function(1, "X")
    assert eng.functions()[0] == "X"


def test_set_function_invalid_expr() -> None:
    eng = TIEngine()
    with pytest.raises(TIError):
        eng.set_function(1, "X +* 2")


# --- window / zoom -------------------------------------------------------
def test_zoom_standard() -> None:
    eng = TIEngine()
    eng.set_window(xmin=1.0, xmax=2.0)
    eng.zoom_standard()
    w = eng.window
    assert (w.xmin, w.xmax, w.ymin, w.ymax) == (-10.0, 10.0, -10.0, 10.0)


def test_zoom_decimal() -> None:
    eng = TIEngine()
    eng.zoom_decimal()
    w = eng.window
    assert w.xmin == pytest.approx(-4.7)
    assert w.xmax == pytest.approx(4.7)
    assert w.ymin == pytest.approx(-3.1)
    assert w.ymax == pytest.approx(3.1)


def test_set_window() -> None:
    eng = TIEngine()
    eng.set_window(ymin=-5.0, ymax=5.0)
    assert eng.window.ymin == -5.0
    assert eng.window.ymax == 5.0


def test_zoom_fit() -> None:
    eng = TIEngine()
    eng.zoom_standard()
    eng.set_function(1, "X^2")
    eng.zoom_fit()
    # x^2 over -10..10 maxes at 100.
    assert eng.window.ymax == pytest.approx(100.0, rel=0.06)
    assert eng.window.ymin <= 0.5


def test_zoom_fit_empty_is_noop() -> None:
    eng = TIEngine()
    eng.zoom_standard()
    before = (eng.window.ymin, eng.window.ymax)
    eng.zoom_fit()
    assert (eng.window.ymin, eng.window.ymax) == before


# --- graphing ------------------------------------------------------------
def test_graph_pixels_line() -> None:
    eng = TIEngine()
    eng.zoom_standard()
    eng.set_function(1, "X")
    pix = eng.graph_pixels()
    pts = pix[1]
    # One sample per column -> roughly w points.
    assert len(pts) == SCREEN_W
    for px, py in pts:
        assert 0 <= px < SCREEN_W
        assert 0 <= py < SCREEN_H
    # The line y=x runs corner to corner: top-left maps high, bottom-right low,
    # and the mid-screen sample lands near the centre.
    centre_col = round((0.0 - (-10.0)) / 20.0 * (SCREEN_W - 1))
    centre_row = round((10.0 - 0.0) / 20.0 * (SCREEN_H - 1))
    near_centre = [
        p for p in pts if abs(p[0] - centre_col) <= 1 and abs(p[1] - centre_row) <= 1
    ]
    assert near_centre, f"no point near screen centre in {pts}"


def test_graph_pixels_parabola_vertex_low_centre() -> None:
    eng = TIEngine()
    # A window whose ymin is 0 puts the parabola's vertex at the screen bottom.
    eng.set_window(xmin=-10.0, xmax=10.0, ymin=0.0, ymax=100.0)
    eng.set_function(1, "X^2")
    pix = eng.graph_pixels()
    pts = pix[1]
    assert pts, "expected some on-screen points"
    # Vertex (0,0): y=ymin maps to the bottom row of the screen.
    bottom_row = max(py for _px, py in pts)
    assert bottom_row >= SCREEN_H - 2
    # The lowest points sit near the horizontal centre.
    centre_col = round((0.0 - (-10.0)) / 20.0 * (SCREEN_W - 1))
    bottom_pts = [p for p in pts if p[1] == bottom_row]
    assert any(abs(px - centre_col) <= 1 for px, _py in bottom_pts)


def test_graph_pixels_all_in_bounds() -> None:
    eng = TIEngine()
    eng.zoom_standard()
    eng.set_function(1, "sin(X)")
    for pts in eng.graph_pixels().values():
        for px, py in pts:
            assert 0 <= px < SCREEN_W
            assert 0 <= py < SCREEN_H


def test_axes_pixels_centre() -> None:
    eng = TIEngine()
    eng.zoom_standard()
    ax = eng.axes_pixels()
    centre_col = round((0.0 - (-10.0)) / 20.0 * (SCREEN_W - 1))
    centre_row = round((10.0 - 0.0) / 20.0 * (SCREEN_H - 1))
    assert ax["y_axis_col"] == centre_col
    assert ax["x_axis_row"] == centre_row


def test_axes_pixels_off_range() -> None:
    eng = TIEngine()
    eng.set_window(xmin=1.0, xmax=10.0, ymin=1.0, ymax=10.0)
    ax = eng.axes_pixels()
    assert ax["x_axis_row"] is None
    assert ax["y_axis_col"] is None


# --- table ---------------------------------------------------------------
def test_table_parabola() -> None:
    eng = TIEngine()
    eng.set_function(1, "X^2")
    tbl = eng.table(0, 1, 3)
    assert tbl == [["X", "Y1"], ["0", "0"], ["1", "1"], ["2", "4"]]


def test_table_multiple_functions() -> None:
    eng = TIEngine()
    eng.set_function(1, "X")
    eng.set_function(3, "X+1")
    tbl = eng.table(0, 1, 2)
    assert tbl[0] == ["X", "Y1", "Y3"]
    assert tbl[1] == ["0", "0", "1"]
    assert tbl[2] == ["1", "1", "2"]


# --- misc ----------------------------------------------------------------
def test_window_defaults() -> None:
    w = Window()
    assert (w.xmin, w.xmax, w.ymin, w.ymax) == (-10.0, 10.0, -10.0, 10.0)
    assert (w.xscl, w.yscl) == (1.0, 1.0)


def test_screen_constants() -> None:
    assert SCREEN_W == 94
    assert SCREEN_H == 62


# --- letter variables (STO>) — were stubbed -------------------------------


def test_store_and_recall_variable():
    e = TIEngine()
    assert e.home_eval("5->A") == "5"
    assert e.home_eval("A*3") == "15"
    assert e.get_var("A") == 5.0


def test_store_via_arrow_unicode():
    e = TIEngine()
    e.home_eval("7→B")           # 7 → B
    assert e.home_eval("B+1") == "8"


def test_unset_variable_is_zero():
    e = TIEngine()
    assert e.home_eval("C+10") == "10"     # unset C reads as 0


def test_store_method_and_ans():
    e = TIEngine()
    e.store(9, "D")
    assert e.get_var("D") == 9.0
    assert e.ans == 9.0                     # STO also updates Ans
    assert e.home_eval("D*D") == "81"


def test_variables_do_not_break_function_tokens():
    e = TIEngine()
    e.store(3, "A")
    # lowercase function tokens are untouched by variable substitution
    assert e.home_eval("abs(0-A)") == "3"
    assert e.home_eval("9^0.5") == "3"


# --- STAT list editor — were stubbed/missing ------------------------------


def test_stat_lists_start_empty():
    e = TIEngine()
    assert STAT_LISTS == ("L1", "L2", "L3", "L4", "L5", "L6")
    for name in STAT_LISTS:
        assert e.get_list(name) == []


def test_set_get_list_and_case_insensitive():
    e = TIEngine()
    e.set_list("L1", [1, 2, 3])
    assert e.get_list("L1") == [1.0, 2.0, 3.0]
    # lowercase names normalise to the canonical list
    assert e.get_list("l1") == [1.0, 2.0, 3.0]
    # get_list returns a copy — mutating it must not touch the store
    got = e.get_list("L1")
    got.append(99.0)
    assert e.get_list("L1") == [1.0, 2.0, 3.0]


def test_append_and_clear_list():
    e = TIEngine()
    e.append_list("L1", 5)
    e.append_list("L1", 6)
    assert e.get_list("L1") == [5.0, 6.0]
    e.clear_list("L1")
    assert e.get_list("L1") == []


def test_clear_all_lists():
    e = TIEngine()
    e.set_list("L1", [1, 2])
    e.set_list("L2", [3, 4])
    e.clear_all_lists()
    assert e.get_list("L1") == []
    assert e.get_list("L2") == []


def test_unknown_list_raises():
    e = TIEngine()
    with pytest.raises(TIError):
        e.set_list("L9", [1, 2])
    with pytest.raises(TIError):
        e.get_list("XYZ")


# --- STAT CALC: 1-Var Stats -----------------------------------------------


def test_one_var_stats_known_values():
    e = TIEngine()
    e.set_list("L1", [1, 2, 3, 4, 5])
    v = e.one_var_stats("L1")
    assert v["n"] == 5
    assert v["mean"] == pytest.approx(3.0)
    assert v["sum"] == pytest.approx(15.0)
    assert v["sum_sq"] == pytest.approx(55.0)
    assert v["Sx"] == pytest.approx(1.5811388, abs=1e-6)      # sample sd
    assert v["sigma_x"] == pytest.approx(1.4142136, abs=1e-6)  # population sd
    assert v["min"] == pytest.approx(1.0)
    assert v["Q1"] == pytest.approx(2.0)
    assert v["median"] == pytest.approx(3.0)
    assert v["Q3"] == pytest.approx(4.0)
    assert v["max"] == pytest.approx(5.0)


def test_one_var_stats_single_point_population_sd_zero():
    e = TIEngine()
    e.set_list("L1", [7])
    v = e.one_var_stats("L1")
    assert v["n"] == 1
    assert v["mean"] == pytest.approx(7.0)
    assert v["Sx"] == pytest.approx(0.0)       # sample sd undefined -> 0
    assert v["sigma_x"] == pytest.approx(0.0)  # population sd of one point is 0
    assert v["median"] == pytest.approx(7.0)


def test_one_var_stats_empty_raises():
    e = TIEngine()
    with pytest.raises(TIError):
        e.one_var_stats("L1")


# --- STAT CALC: 2-Var Stats & LinReg --------------------------------------


def test_lin_reg_perfectly_linear():
    e = TIEngine()
    e.set_list("L1", [1, 2, 3])
    e.set_list("L2", [2, 4, 6])
    fit = e.lin_reg("L1", "L2")
    assert fit["a"] == pytest.approx(2.0)   # slope
    assert fit["b"] == pytest.approx(0.0)   # intercept
    assert fit["r"] == pytest.approx(1.0)
    assert fit["r2"] == pytest.approx(1.0)
    assert fit["n"] == 3


def test_two_var_stats_known_values():
    e = TIEngine()
    e.set_list("L1", [1, 2, 3])
    e.set_list("L2", [2, 4, 6])
    v = e.two_var_stats("L1", "L2")
    assert v["n"] == 3
    assert v["mean_x"] == pytest.approx(2.0)
    assert v["mean_y"] == pytest.approx(4.0)
    assert v["sum_x"] == pytest.approx(6.0)
    assert v["sum_y"] == pytest.approx(12.0)
    assert v["sum_xy"] == pytest.approx(28.0)   # 1*2 + 2*4 + 3*6
    assert v["sum_x_sq"] == pytest.approx(14.0)
    assert v["sum_y_sq"] == pytest.approx(56.0)


def test_two_var_stats_length_mismatch_raises():
    e = TIEngine()
    e.set_list("L1", [1, 2, 3])
    e.set_list("L2", [1, 2])
    with pytest.raises(TIError):
        e.two_var_stats("L1", "L2")
    with pytest.raises(TIError):
        e.lin_reg("L1", "L2")


def test_lin_reg_empty_raises():
    e = TIEngine()
    with pytest.raises(TIError):
        e.lin_reg("L1", "L2")
