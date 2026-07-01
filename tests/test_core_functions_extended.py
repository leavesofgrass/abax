"""Extended function library: lookups, conditional aggregation, text, date, info."""

from __future__ import annotations

import pytest

from abax.core import Sheet
from abax.core.errors import CellError


def _grid(rows):
    s = Sheet()
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            s.set(f"{chr(ord('A') + c)}{r + 1}", str(val))
    return s


# --- range shape regression -----------------------------------------------


def test_aggregate_over_2d_range():
    s = _grid([[1, 2], [3, 4]])
    s.set("D1", "=SUM(A1:B2)")
    s.set("D2", "=AVERAGE(A1:B2)")
    s.set("D3", "=MAX(A1:B2)")
    assert s.get("D1") == 10
    assert s.get("D2") == 2.5
    assert s.get("D3") == 4


# --- lookup ----------------------------------------------------------------


def test_vlookup_exact():
    s = _grid([["apple", 3], ["banana", 5], ["cherry", 8]])
    s.set("D1", '=VLOOKUP("banana", A1:B3, 2, FALSE)')
    assert s.get("D1") == 5


def test_vlookup_not_found_is_na():
    s = _grid([["apple", 3], ["banana", 5]])
    s.set("D1", '=VLOOKUP("kiwi", A1:B2, 2, FALSE)')
    assert s.get("D1") == CellError(CellError.NA)


def test_vlookup_approximate_sorted():
    s = _grid([[10, "low"], [20, "mid"], [30, "high"]])
    s.set("D1", "=VLOOKUP(25, A1:B3, 2, TRUE)")
    assert s.get("D1") == "mid"


def test_hlookup():
    s = _grid([["q1", "q2", "q3"], [100, 200, 300]])
    s.set("A4", '=HLOOKUP("q2", A1:C2, 2, FALSE)')
    assert s.get("A4") == 200


def test_index_and_match():
    s = _grid([["a", 1], ["b", 2], ["c", 3]])
    s.set("D1", "=INDEX(A1:B3, 2, 2)")
    s.set("D2", '=MATCH("c", A1:A3, 0)')
    assert s.get("D1") == 2
    assert s.get("D2") == 3


def test_index_match_combo():
    s = _grid([["apple", 3], ["banana", 5], ["cherry", 8]])
    s.set("D1", '=INDEX(B1:B3, MATCH("cherry", A1:A3, 0))')
    assert s.get("D1") == 8


# --- conditional aggregation ----------------------------------------------


def test_sumif_countif_averageif():
    s = Sheet()
    for i, v in enumerate([5, 15, 25, 35], start=1):
        s.set(f"A{i}", str(v))
    s.set("C1", '=SUMIF(A1:A4, ">10")')
    s.set("C2", '=COUNTIF(A1:A4, ">10")')
    s.set("C3", '=AVERAGEIF(A1:A4, ">10")')
    assert s.get("C1") == 75
    assert s.get("C2") == 3
    assert s.get("C3") == 25


def test_sumif_with_separate_sum_range():
    s = _grid([["x", 1], ["y", 2], ["x", 4]])
    s.set("D1", '=SUMIF(A1:A3, "x", B1:B3)')
    assert s.get("D1") == 5


def test_countif_wildcard():
    s = _grid([["apple"], ["apricot"], ["banana"]])
    s.set("C1", '=COUNTIF(A1:A3, "ap*")')
    assert s.get("C1") == 2


# --- logical / control flow -----------------------------------------------


def test_iferror():
    s = Sheet()
    s.set("A1", '=IFERROR(1/0, "oops")')
    s.set("A2", "=IFERROR(10/2, 99)")
    assert s.get("A1") == "oops"
    assert s.get("A2") == 5


def test_ifs():
    s = Sheet()
    s.set("A1", "75")
    s.set("B1", '=IFS(A1>=90,"A", A1>=80,"B", A1>=70,"C", TRUE,"F")')
    assert s.get("B1") == "C"


def test_switch():
    s = Sheet()
    s.set("A1", "2")
    s.set("B1", '=SWITCH(A1, 1,"one", 2,"two", "other")')
    assert s.get("B1") == "two"


def test_choose_is_lazy():
    s = Sheet()
    s.set("A1", "0")
    # the 3rd option divides by zero but must not be evaluated
    s.set("B1", "=CHOOSE(1, 42, 1/A1, 1/A1)")
    assert s.get("B1") == 42


def test_xor():
    s = Sheet()
    s.set("A1", "=XOR(TRUE, FALSE)")
    s.set("A2", "=XOR(TRUE, TRUE)")
    assert s.get("A1") is True
    assert s.get("A2") is False


# --- math extras -----------------------------------------------------------


def test_rounding_family():
    s = Sheet()
    s.set("A1", "=ROUNDUP(2.1, 0)")
    s.set("A2", "=ROUNDDOWN(2.9, 0)")
    s.set("A3", "=CEILING(2.1, 1)")
    s.set("A4", "=FLOOR(2.9, 1)")
    s.set("A5", "=TRUNC(2.78, 1)")
    assert s.get("A1") == 3
    assert s.get("A2") == 2
    assert s.get("A3") == 3
    assert s.get("A4") == 2
    assert s.get("A5") == 2.7


def test_gcd_lcm_sumproduct():
    s = _grid([[2, 3], [4, 5]])
    s.set("D1", "=GCD(12, 18)")
    s.set("D2", "=LCM(4, 6)")
    s.set("D3", "=SUMPRODUCT(A1:A2, B1:B2)")  # 2*3 + 4*5 = 26
    assert s.get("D1") == 6
    assert s.get("D2") == 12
    assert s.get("D3") == 26


def test_statistics_functions():
    s = Sheet()
    for i, v in enumerate([2, 4, 4, 4, 5, 5, 7, 9], start=1):
        s.set(f"A{i}", str(v))
    s.set("C1", "=PERCENTILE(A1:A8, 0.5)")  # median = 4.5
    s.set("C2", "=QUARTILE(A1:A8, 2)")  # also median
    s.set("C3", "=GEOMEAN(1, 4, 16)")  # 4
    assert s.get("C1") == pytest.approx(4.5)
    assert s.get("C2") == pytest.approx(4.5)
    assert s.get("C3") == pytest.approx(4)


def test_correlation():
    s = Sheet()
    for i, (x, y) in enumerate([(1, 2), (2, 4), (3, 6), (4, 8)], start=1):
        s.set(f"A{i}", str(x))
        s.set(f"B{i}", str(y))
    s.set("D1", "=CORREL(A1:A4, B1:B4)")  # perfectly linear -> 1
    assert s.get("D1") == pytest.approx(1.0)


def test_stdev_and_mod():
    s = Sheet()
    for i, v in enumerate([2, 4, 4, 4, 5, 5, 7, 9], start=1):
        s.set(f"A{i}", str(v))
    s.set("C1", "=STDEVP(A1:A8)")
    s.set("C2", "=MOD(10, 3)")
    s.set("C3", "=MOD(-10, 3)")  # Excel sign-follows-divisor -> 2
    assert s.get("C1") == pytest.approx(2.0)
    assert s.get("C2") == 1
    assert s.get("C3") == 2


# --- text extras -----------------------------------------------------------


def test_text_functions_extended():
    s = Sheet()
    s.set("A1", "hello world")
    s.set("B1", "=PROPER(A1)")
    s.set("B2", '=SUBSTITUTE(A1, "o", "0")')
    s.set("B3", '=FIND("world", A1)')
    s.set("B4", "=REPT(\"ab\", 3)")
    s.set("B5", "=VALUE(\"42\")")
    assert s.get("B1") == "Hello World"
    assert s.get("B2") == "hell0 w0rld"
    assert s.get("B3") == 7
    assert s.get("B4") == "ababab"
    assert s.get("B5") == 42


# --- date / time -----------------------------------------------------------


def test_date_functions():
    s = Sheet()
    s.set("A1", "=DATE(2026, 6, 27)")
    s.set("B1", "=YEAR(A1)")
    s.set("B2", "=MONTH(A1)")
    s.set("B3", "=DAY(A1)")
    s.set("B4", "=WEEKDAY(A1)")  # 2026-06-27 is a Saturday -> 7
    assert s.get("A1") == "2026-06-27"
    assert s.get("B1") == 2026
    assert s.get("B2") == 6
    assert s.get("B3") == 27
    assert s.get("B4") == 7


def test_datedif_and_edate():
    s = Sheet()
    s.set("A1", "=DATEDIF(\"2026-01-01\", \"2026-06-27\", \"M\")")
    s.set("A2", "=EDATE(\"2026-01-31\", 1)")  # clamps to end of Feb
    assert s.get("A1") == 5
    assert s.get("A2") == "2026-02-28"


# --- info ------------------------------------------------------------------


def test_info_functions():
    s = Sheet()
    s.set("A1", "5")
    s.set("A2", "hi")
    s.set("B1", "=ISNUMBER(A1)")
    s.set("B2", "=ISTEXT(A2)")
    s.set("B3", "=ISBLANK(Z9)")
    s.set("B4", "=ISERROR(1/0)")
    assert s.get("B1") is True
    assert s.get("B2") is True
    assert s.get("B3") is True
    assert s.get("B4") is True


# --- units / complex / matrix-scalar (iteration 6-8) -----------------------


def test_convert_function():
    s = Sheet()
    s.set("A1", '=CONVERT(100, "km", "mi")')
    s.set("A2", '=CONVERT(32, "F", "C")')
    s.set("A3", '=CONVERT(1, "kWh", "J")')
    s.set("A4", '=CONVERT(1, "m", "kg")')   # cross-category -> #N/A
    assert abs(s.get("A1") - 62.137119) < 1e-4
    assert abs(s.get("A2") - 0.0) < 1e-9
    assert s.get("A3") == 3600000.0
    assert str(s.get("A4")) == "#N/A"


def test_complex_and_mdeterm_functions():
    s = Sheet()
    s.set("A1", '=IMSUM("3+4i", "1-2i")')
    s.set("A2", '=IMABS("3+4i")')
    s.set("C1", "1"); s.set("D1", "2"); s.set("C2", "3"); s.set("D2", "4")
    s.set("A3", "=MDETERM(C1:D2)")
    assert s.get("A1") == "4+2i"
    assert s.get("A2") == 5.0
    assert s.get("A3") == -2.0


# --- signal / data (iteration 9) -------------------------------------------


def test_interp_and_rms_functions():
    s = Sheet()
    for i, (x, y) in enumerate([(1, 10), (2, 20), (3, 30), (4, 45)], start=1):
        s.set(f"A{i}", str(x))
        s.set(f"B{i}", str(y))
    s.set("D1", "=INTERP(2.5, A1:A4, B1:B4)")
    s.set("D2", "=RMS(B1:B4)")
    s.set("D3", "=INTERP(2.5, A1:A4, B1:B3)")  # length mismatch -> #VALUE!
    assert s.get("D1") == 25.0
    assert abs(s.get("D2") - 29.2617) < 1e-3
    assert str(s.get("D3")) == "#VALUE!"
