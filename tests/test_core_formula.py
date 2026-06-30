"""Formula engine: references, operators, functions, errors, recalc."""

from __future__ import annotations

import math

import pytest

from qcell.core import Sheet
from qcell.core.errors import CellError
from qcell.core.reference import col_to_index, index_to_col, parse_a1, to_a1

# --- references -----------------------------------------------------------


@pytest.mark.parametrize(
    "col,idx",
    [("A", 0), ("Z", 25), ("AA", 26), ("AB", 27), ("AZ", 51), ("BA", 52)],
)
def test_col_index_roundtrip(col, idx):
    assert col_to_index(col) == idx
    assert index_to_col(idx) == col


def test_parse_and_to_a1():
    assert parse_a1("B3") == (2, 1)
    assert parse_a1("$A$1") == (0, 0)
    assert to_a1(2, 1) == "B3"


# --- literals and arithmetic ----------------------------------------------


def test_number_literals():
    s = Sheet()
    s.set("A1", "42")
    s.set("A2", "3.14")
    assert s.get("A1") == 42
    assert s.get("A2") == 3.14


def test_basic_arithmetic():
    s = Sheet()
    s.set("A1", "10")
    s.set("A2", "3")
    s.set("B1", "=A1+A2")
    s.set("B2", "=A1-A2")
    s.set("B3", "=A1*A2")
    s.set("B4", "=A1/A2")
    s.set("B5", "=2^10")
    assert s.get("B1") == 13
    assert s.get("B2") == 7
    assert s.get("B3") == 30
    assert s.get("B4") == pytest.approx(10 / 3)
    assert s.get("B5") == 1024


def test_operator_precedence():
    s = Sheet()
    s.set("A1", "=1+2*3")
    s.set("A2", "=(1+2)*3")
    s.set("A3", "=2^3^2")  # right-assoc -> 2^9 = 512
    assert s.get("A1") == 7
    assert s.get("A2") == 9
    assert s.get("A3") == 512


def test_unary_minus():
    s = Sheet()
    s.set("A1", "=-5+3")
    assert s.get("A1") == -2


# --- functions ------------------------------------------------------------


def test_sum_and_average_over_range():
    s = Sheet()
    for i, v in enumerate([10, 20, 30, 40], start=1):
        s.set(f"A{i}", str(v))
    s.set("B1", "=SUM(A1:A4)")
    s.set("B2", "=AVERAGE(A1:A4)")
    s.set("B3", "=MIN(A1:A4)")
    s.set("B4", "=MAX(A1:A4)")
    s.set("B5", "=COUNT(A1:A4)")
    assert s.get("B1") == 100
    assert s.get("B2") == 25
    assert s.get("B3") == 10
    assert s.get("B4") == 40
    assert s.get("B5") == 4


def test_nested_functions():
    s = Sheet()
    s.set("A1", "9")
    s.set("A2", "=SQRT(A1)")
    s.set("A3", "=ROUND(AVERAGE(2,3,4),1)")
    assert s.get("A2") == 3
    assert s.get("A3") == 3


def test_if_is_lazy():
    s = Sheet()
    s.set("A1", "0")
    # else-branch divides by A1; IF must not evaluate it when condition true.
    s.set("B1", "=IF(A1=0, 99, 1/A1)")
    assert s.get("B1") == 99


def test_text_functions():
    s = Sheet()
    s.set("A1", "hello")
    s.set("A2", "world")
    s.set("B1", '=CONCAT(A1," ",A2)')
    s.set("B2", "=UPPER(A1)")
    s.set("B3", "=LEN(A1)")
    s.set("B4", "=LEFT(A1,3)")
    assert s.get("B1") == "hello world"
    assert s.get("B2") == "HELLO"
    assert s.get("B3") == 5
    assert s.get("B4") == "hel"


def test_string_concat_operator():
    s = Sheet()
    s.set("A1", "foo")
    s.set("B1", '=A1&"bar"')
    assert s.get("B1") == "foobar"


def test_comparison_and_logical():
    s = Sheet()
    s.set("A1", "5")
    s.set("B1", "=A1>3")
    s.set("B2", "=AND(A1>3, A1<10)")
    s.set("B3", "=OR(A1>100, A1<0)")
    s.set("B4", "=NOT(A1>3)")
    assert s.get("B1") is True
    assert s.get("B2") is True
    assert s.get("B3") is False
    assert s.get("B4") is False


# --- errors ---------------------------------------------------------------


def test_div_by_zero():
    s = Sheet()
    s.set("A1", "=1/0")
    assert s.get("A1") == CellError(CellError.DIV0)


def test_unknown_function():
    s = Sheet()
    s.set("A1", "=BOGUS(1)")
    assert s.get("A1") == CellError(CellError.NAME)


def test_error_propagates():
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("A2", "=A1+5")
    assert s.get("A2") == CellError(CellError.DIV0)


def test_circular_reference_detected():
    s = Sheet()
    s.set("A1", "=A2")
    s.set("A2", "=A1")
    assert s.get("A1") == CellError(CellError.CIRC)


# --- recalculation --------------------------------------------------------


def test_dependents_update_on_edit():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "=A1*10")
    assert s.get("A2") == 10
    s.set("A1", "5")
    assert s.get("A2") == 50


def test_chain_recalc():
    s = Sheet()
    s.set("A1", "2")
    s.set("A2", "=A1*2")
    s.set("A3", "=A2*2")
    s.set("A4", "=A3*2")
    assert s.get("A4") == 16
    s.set("A1", "3")
    assert s.get("A4") == 24


def test_format_value():
    assert Sheet.format_value(3.0) == "3"
    assert Sheet.format_value(3.5) == "3.5"
    assert Sheet.format_value(True) == "TRUE"
    assert Sheet.format_value(None) == ""
    assert Sheet.format_value(CellError(CellError.NA)) == "#N/A"


def test_power_function_matches_operator():
    s = Sheet()
    s.set("A1", "=POWER(2,8)")
    assert s.get("A1") == math.pow(2, 8)


def test_absolute_references_evaluate():
    s = Sheet()
    s.set("A1", "7")
    s.set("B1", "=$A$1+1")
    s.set("B2", "=$A1*2")
    s.set("B3", "=A$1+3")
    assert s.get("B1") == 8
    assert s.get("B2") == 14
    assert s.get("B3") == 10


def test_functions_ending_in_digits():
    # LOG10 / ATAN2 must tokenize as function names, not cell refs.
    s = Sheet()
    s.set("A1", "=LOG10(1000)")
    s.set("A2", "=ATAN2(1, 0)")
    assert s.get("A1") == pytest.approx(3)
    assert s.get("A2") == pytest.approx(0)


def test_sheet_repr_html():
    s = Sheet()
    s.set("A1", "Price")
    s.set("A2", "10")
    s.set("A3", "=A2*2")
    h = s._repr_html_()
    assert "<table" in h and "<th>A</th>" in h
    assert "20" in h                                   # computed value rendered
    assert Sheet()._repr_html_() == "<i>empty sheet</i>"
