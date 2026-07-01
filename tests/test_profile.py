"""Tests for qcell.core.profile — column & sheet data profiling."""

from __future__ import annotations

import statistics

from qcell.core.profile import profile_column, profile_sheet
from qcell.core.sheet import Sheet


def test_numeric_column_stats():
    values = [10, 20, 30, 40, 50]
    prof = profile_column(values)

    assert prof["dtype"] == "int"
    assert prof["count"] == 5
    assert prof["missing"] == 0
    assert prof["unique"] == 5
    assert prof["min"] == 10
    assert prof["max"] == 50
    assert prof["mean"] == 30
    assert prof["median"] == 30
    assert prof["std"] == statistics.pstdev([10, 20, 30, 40, 50])
    q1, _q2, q3 = statistics.quantiles([10, 20, 30, 40, 50], n=4)
    assert prof["q1"] == q1
    assert prof["q3"] == q3


def test_float_column_is_float():
    prof = profile_column([1.5, 2.5, "3.5", None])
    assert prof["dtype"] == "float"
    assert prof["count"] == 3
    assert prof["missing"] == 1
    assert prof["min"] == 1.5
    assert prof["max"] == 3.5
    assert prof["mean"] == statistics.mean([1.5, 2.5, 3.5])


def test_single_value_numeric_std_and_quartiles():
    prof = profile_column([42])
    assert prof["dtype"] == "int"
    assert prof["std"] == 0.0
    assert prof["q1"] == 42
    assert prof["q3"] == 42


def test_text_column_top_and_max_len():
    values = ["apple", "banana", "apple", "cherry", "banana", "apple", "fig"]
    prof = profile_column(values)

    assert prof["dtype"] == "text"
    assert prof["count"] == 7
    assert prof["unique"] == 4
    assert prof["max_len"] == len("banana")
    # apple x3 (first seen), banana x2 (second seen), then singletons.
    assert prof["top"][0] == ("apple", 3)
    assert prof["top"][1] == ("banana", 2)
    assert len(prof["top"]) == 4


def test_top_capped_at_five():
    values = ["a", "b", "c", "d", "e", "f", "g"]
    prof = profile_column(values)
    assert len(prof["top"]) == 5


def test_missing_counts_none_and_empty_string():
    values = [1, None, 2, "", 3, None]
    prof = profile_column(values)
    assert prof["count"] == 3
    assert prof["missing"] == 3
    assert prof["dtype"] == "int"


def test_mixed_int_and_text_is_text():
    prof = profile_column([1, 2, "hello", 4])
    assert prof["dtype"] == "text"
    assert "top" in prof
    assert "mean" not in prof


def test_bool_column_is_bool():
    prof = profile_column([True, False, True, True])
    assert prof["dtype"] == "bool"
    assert prof["count"] == 4
    # numeric stats computed over 1/0 encoding
    assert prof["mean"] == statistics.mean([1.0, 0.0, 1.0, 1.0])
    assert prof["min"] == 0.0
    assert prof["max"] == 1.0


def test_empty_column():
    prof = profile_column([None, "", None])
    assert prof["dtype"] == "empty"
    assert prof["count"] == 0
    assert prof["missing"] == 3
    assert prof["unique"] == 0


def test_profile_sheet_with_header_row():
    sheet = Sheet(name="Data")
    headers = ["Name", "Age", "Score"]
    for col, h in enumerate(headers):
        sheet.set_cell(0, col, h)
    rows = [
        ["Alice", "30", "9.5"],
        ["Bob", "25", "8.0"],
        ["Carol", "35", "7.5"],
    ]
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            sheet.set_cell(r, c, val)

    profs = profile_sheet(sheet, header_row=True)

    assert len(profs) == 3
    assert [p["name"] for p in profs] == ["Name", "Age", "Score"]

    name_col, age_col, score_col = profs
    assert name_col["dtype"] == "text"
    assert name_col["count"] == 3  # header not counted as data

    assert age_col["dtype"] == "int"
    assert age_col["count"] == 3
    assert age_col["min"] == 25
    assert age_col["max"] == 35

    assert score_col["dtype"] == "float"
    assert score_col["count"] == 3


def test_profile_sheet_without_header_uses_column_letters():
    sheet = Sheet(name="Raw")
    sheet.set_cell(0, 0, "10")
    sheet.set_cell(1, 0, "20")
    sheet.set_cell(0, 1, "x")
    sheet.set_cell(1, 1, "y")

    profs = profile_sheet(sheet, header_row=False)

    assert len(profs) == 2
    assert [p["name"] for p in profs] == ["A", "B"]
    assert profs[0]["dtype"] == "int"
    assert profs[0]["count"] == 2  # first row IS data here
    assert profs[1]["dtype"] == "text"
