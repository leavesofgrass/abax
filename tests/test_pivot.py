"""Tests for the group-by / pivot-table engine (``abax.core.pivot``)."""

from __future__ import annotations

import pytest

from abax.core.pivot import (
    AGGREGATIONS,
    PivotError,
    crosstab,
    group_by,
    pivot_table,
)

ROWS = [
    ["dept", "city", "amt"],
    ["A", "NY", "10"],
    ["A", "LA", "20"],
    ["B", "NY", "5"],
    ["A", "NY", "30"],
]


# --------------------------------------------------------------------------- #
# group_by                                                                     #
# --------------------------------------------------------------------------- #
def test_group_by_sum():
    out = group_by(ROWS, ["dept"], "amt", "sum")
    assert out[0] == ["dept", "sum(amt)"]
    assert out[1:] == [["A", "60"], ["B", "5"]]


def test_group_by_mean():
    out = group_by(ROWS, ["dept"], "amt", "mean")
    assert out[1:] == [["A", "20"], ["B", "5"]]


def test_group_by_count():
    out = group_by(ROWS, ["dept"], "amt", "count")
    assert out[0] == ["dept", "count(amt)"]
    assert out[1:] == [["A", "3"], ["B", "1"]]


def test_group_by_multi_col_sorted():
    out = group_by(ROWS, ["dept", "city"], "amt", "sum")
    assert out[0] == ["dept", "city", "sum(amt)"]
    assert out[1:] == [
        ["A", "LA", "20"],
        ["A", "NY", "40"],
        ["B", "NY", "5"],
    ]


def test_group_by_min_max_median():
    assert group_by(ROWS, ["dept"], "amt", "min")[1:] == [["A", "10"], ["B", "5"]]
    assert group_by(ROWS, ["dept"], "amt", "max")[1:] == [["A", "30"], ["B", "5"]]
    assert group_by(ROWS, ["dept"], "amt", "median")[1:] == [["A", "20"], ["B", "5"]]


def test_group_by_std_sample():
    out = group_by(ROWS, ["dept"], "amt", "std")
    # A = stdev(10, 20, 30) = 10 ; B has one value -> "0".
    assert out[1] == ["A", "10"]
    assert out[2] == ["B", "0"]


def test_group_by_natural_numeric_sort():
    rows = [["k", "v"], ["10", "1"], ["2", "1"], ["1", "1"]]
    out = group_by(rows, ["k"], "v", "sum")
    assert [r[0] for r in out[1:]] == ["1", "2", "10"]


def test_group_by_lexical_sort_when_not_all_numeric():
    rows = [["k", "v"], ["b", "1"], ["a", "1"], ["10", "1"]]
    out = group_by(rows, ["k"], "v", "sum")
    assert [r[0] for r in out[1:]] == ["10", "a", "b"]


# --------------------------------------------------------------------------- #
# blanks / non-numeric / nunique / first                                      #
# --------------------------------------------------------------------------- #
def test_numeric_agg_ignores_blanks_and_text():
    rows = [
        ["g", "v"],
        ["A", "10"],
        ["A", ""],
        ["A", "abc"],
        ["A", "20"],
    ]
    assert group_by(rows, ["g"], "v", "sum")[1] == ["A", "30"]
    assert group_by(rows, ["g"], "v", "mean")[1] == ["A", "15"]
    # count counts non-blank entries (incl. "abc"); nunique distinct non-blank.
    assert group_by(rows, ["g"], "v", "count")[1] == ["A", "3"]
    assert group_by(rows, ["g"], "v", "nunique")[1] == ["A", "3"]


def test_numeric_agg_all_blank_group_is_empty():
    rows = [["g", "v"], ["A", ""], ["A", ""]]
    assert group_by(rows, ["g"], "v", "sum")[1] == ["A", ""]
    assert group_by(rows, ["g"], "v", "std")[1] == ["A", ""]


def test_first_skips_blanks():
    rows = [["g", "v"], ["A", ""], ["A", "x"], ["A", "y"]]
    assert group_by(rows, ["g"], "v", "first")[1] == ["A", "x"]
    rows_empty = [["g", "v"], ["A", ""]]
    assert group_by(rows_empty, ["g"], "v", "first")[1] == ["A", ""]


def test_ragged_rows_tolerated():
    rows = [["g", "v"], ["A"], ["A", "5"]]
    # First A row has a missing value cell -> blank, ignored by sum.
    assert group_by(rows, ["g"], "v", "sum")[1] == ["A", "5"]


# --------------------------------------------------------------------------- #
# pivot_table                                                                  #
# --------------------------------------------------------------------------- #
def test_pivot_table_sum():
    out = pivot_table(ROWS, "dept", "city", "amt", "sum")
    assert out[0] == ["dept", "LA", "NY"]
    assert out[1] == ["A", "20", "40"]
    assert out[2] == ["B", "", "5"]


def test_pivot_table_count():
    out = pivot_table(ROWS, "dept", "city", "amt", "count")
    assert out[0] == ["dept", "LA", "NY"]
    assert out[1] == ["A", "1", "2"]
    assert out[2] == ["B", "", "1"]


# --------------------------------------------------------------------------- #
# crosstab                                                                     #
# --------------------------------------------------------------------------- #
def test_crosstab_counts():
    out = crosstab(ROWS, "dept", "city")
    assert out[0] == ["dept", "LA", "NY"]
    assert out[1] == ["A", "1", "2"]
    assert out[2] == ["B", "0", "1"]


# --------------------------------------------------------------------------- #
# errors                                                                       #
# --------------------------------------------------------------------------- #
def test_pivot_error_missing_column():
    with pytest.raises(PivotError):
        group_by(ROWS, ["nope"], "amt", "sum")
    with pytest.raises(PivotError):
        group_by(ROWS, ["dept"], "nope", "sum")
    with pytest.raises(PivotError):
        pivot_table(ROWS, "dept", "nope", "amt")
    with pytest.raises(PivotError):
        crosstab(ROWS, "nope", "city")


def test_pivot_error_unknown_agg():
    with pytest.raises(PivotError):
        group_by(ROWS, ["dept"], "amt", "bogus")
    with pytest.raises(PivotError):
        pivot_table(ROWS, "dept", "city", "amt", "bogus")


def test_aggregations_registry_shape():
    expected = {
        "sum", "mean", "count", "min", "max",
        "median", "std", "nunique", "first",
    }
    assert set(AGGREGATIONS) == expected
    assert all(isinstance(v, str) for v in AGGREGATIONS.values())
