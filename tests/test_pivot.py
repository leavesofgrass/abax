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


# --------------------------------------------------------------------------- #
# margins / grand totals                                                       #
# --------------------------------------------------------------------------- #
# A small fixed category (X/Y) x region (East/West) table with known numbers.
#   sales:  X/East=100  X/West=200  Y/East=50  Y/West=150   grand=500
#   units:  X/East=2    X/West=4    Y/East=1   Y/West=3
MARGIN_ROWS = [
    ["category", "region", "sales", "units"],
    ["X", "East", "100", "2"],
    ["X", "West", "200", "4"],
    ["Y", "East", "50", "1"],
    ["Y", "West", "150", "3"],
]


def test_pivot_table_backward_compatible():
    """Classic 3-arg call is unchanged (no margins, no percent, no extra cols)."""
    out = pivot_table(MARGIN_ROWS, "category", "region", "sales", "sum")
    assert out[0] == ["category", "East", "West"]
    assert out[1] == ["X", "100", "200"]
    assert out[2] == ["Y", "50", "150"]


def test_pivot_table_margins_layout_and_grand_total():
    out = pivot_table(MARGIN_ROWS, "category", "region", "sales", "sum",
                      margins=True)
    assert out[0] == ["category", "East", "West", "Total"]
    assert out[1] == ["X", "100", "200", "300"]
    assert out[2] == ["Y", "50", "150", "200"]
    # Totals row: column sums, then the grand total in the corner.
    assert out[3] == ["Total", "150", "350", "500"]

    # Oracle: the grand total equals the sum of the body cells.
    body = [MARGIN_ROWS[r][2] for r in range(1, len(MARGIN_ROWS))]
    grand = out[3][-1]
    assert float(grand) == sum(float(v) for v in body)
    # And equals the sum of the totals row body and the totals column.
    assert float(grand) == float(out[3][1]) + float(out[3][2])
    assert float(grand) == float(out[1][-1]) + float(out[2][-1])


def test_pivot_table_margins_custom_name():
    out = pivot_table(MARGIN_ROWS, "category", "region", "sales", "sum",
                      margins=True, margins_name="ALL")
    assert out[0][-1] == "ALL"
    assert out[-1][0] == "ALL"


def test_pivot_table_margins_mean_pools_raw_data():
    """A mean margin is the mean of the *raw* rows, not a mean of cell means."""
    out = pivot_table(MARGIN_ROWS, "category", "region", "units", "mean",
                      margins=True)
    # Grand mean of units {2,4,1,3} = 2.5 (a naive mean-of-cell-means also 2.5
    # here, but the row-margin below distinguishes them).
    assert out[-1][-1] == "2.5"
    # X row margin = mean(2, 4) = 3 ; Y row margin = mean(1, 3) = 2.
    assert out[1][-1] == "3"
    assert out[2][-1] == "2"


# --------------------------------------------------------------------------- #
# percent-of-total                                                             #
# --------------------------------------------------------------------------- #
def test_pivot_table_percent_of_grand():
    out = pivot_table(MARGIN_ROWS, "category", "region", "sales", "sum",
                      pct_of="grand")
    assert out[0] == ["category", "East", "West"]
    # Oracle: each cell = value / grand_total * 100. grand = 500.
    assert out[1] == ["X", "20", "40"]      # 100/500, 200/500
    assert out[2] == ["Y", "10", "30"]      # 50/500, 150/500
    # Spot-check the oracle directly on one cell.
    assert float(out[1][1]) == pytest.approx(100 / 500 * 100)


def test_pivot_table_percent_of_grand_fraction():
    out = pivot_table(MARGIN_ROWS, "category", "region", "sales", "sum",
                      pct_of="grand", as_percent=False)
    assert out[1] == ["X", "0.2", "0.4"]
    assert out[2] == ["Y", "0.1", "0.3"]


def test_pivot_table_percent_of_row():
    out = pivot_table(MARGIN_ROWS, "category", "region", "sales", "sum",
                      pct_of="row")
    # X row: 100/300, 200/300 ; Y row: 50/200, 150/200.
    assert float(out[1][1]) == pytest.approx(100 / 300 * 100)
    assert float(out[1][2]) == pytest.approx(200 / 300 * 100)
    assert float(out[2][1]) == pytest.approx(50 / 200 * 100)
    assert float(out[2][2]) == pytest.approx(150 / 200 * 100)


def test_pivot_table_percent_of_col():
    out = pivot_table(MARGIN_ROWS, "category", "region", "sales", "sum",
                      pct_of="col")
    # East col total = 150 ; West col total = 350.
    assert float(out[1][1]) == pytest.approx(100 / 150 * 100)
    assert float(out[2][1]) == pytest.approx(50 / 150 * 100)
    assert float(out[1][2]) == pytest.approx(200 / 350 * 100)


def test_pivot_table_percent_with_margins_totals_are_100():
    out = pivot_table(MARGIN_ROWS, "category", "region", "sales", "sum",
                      pct_of="row", margins=True)
    assert out[0] == ["category", "East", "West", "Total"]
    # Each row's Total margin cell is 100 (the whole).
    assert out[1][-1] == "100"
    assert out[2][-1] == "100"
    # Bottom totals row measured against the grand total.
    assert float(out[-1][1]) == pytest.approx(150 / 500 * 100)
    assert float(out[-1][2]) == pytest.approx(350 / 500 * 100)
    assert out[-1][-1] == "100"


def test_pivot_table_percent_col_with_margins_bottom_is_100():
    out = pivot_table(MARGIN_ROWS, "category", "region", "sales", "sum",
                      pct_of="col", margins=True)
    # Each column's bottom (Total) cell is 100.
    assert out[-1][1] == "100"
    assert out[-1][2] == "100"
    assert out[-1][-1] == "100"


def test_pivot_table_percent_unknown_mode_raises():
    with pytest.raises(PivotError):
        pivot_table(MARGIN_ROWS, "category", "region", "sales", pct_of="bogus")


# --------------------------------------------------------------------------- #
# multiple value fields                                                        #
# --------------------------------------------------------------------------- #
def test_pivot_table_multi_value_two_aggs():
    out = pivot_table(MARGIN_ROWS, "category", "region",
                      value_cols=["sales", "units"], aggs=["sum", "mean"])
    assert out[0] == [
        "category",
        "East - sum(sales)", "East - mean(units)",
        "West - sum(sales)", "West - mean(units)",
    ]
    # X: East sales=100, East units mean=2, West sales=200, West units mean=4.
    assert out[1] == ["X", "100", "2", "200", "4"]
    assert out[2] == ["Y", "50", "1", "150", "3"]
    # Oracle: both aggregates present and correct for one (index, column) cell.
    hdr = out[0]
    x = out[1]
    assert x[hdr.index("East - sum(sales)")] == "100"
    assert x[hdr.index("East - mean(units)")] == "2"


def test_pivot_table_multi_value_default_agg_applies_to_all():
    out = pivot_table(MARGIN_ROWS, "category", "region",
                      value_cols=["sales", "units"], agg="sum")
    # No aggs list -> agg="sum" for every field.
    assert out[0] == [
        "category",
        "East - sum(sales)", "East - sum(units)",
        "West - sum(sales)", "West - sum(units)",
    ]
    assert out[1] == ["X", "100", "2", "200", "4"]


def test_pivot_table_multi_value_with_margins():
    out = pivot_table(MARGIN_ROWS, "category", "region",
                      value_cols=["sales", "units"], aggs=["sum", "mean"],
                      margins=True)
    hdr = out[0]
    assert hdr[-2:] == ["Total - sum(sales)", "Total - mean(units)"]
    # X margin: sum(sales)=300, mean(units)=mean(2,4)=3.
    assert out[1][-2:] == ["300", "3"]
    # Bottom totals row: grand sum(sales)=500, grand mean(units)=2.5.
    assert out[-1][0] == "Total"
    assert out[-1][-2:] == ["500", "2.5"]


def test_pivot_table_multi_value_percent_per_field():
    out = pivot_table(MARGIN_ROWS, "category", "region",
                      value_cols=["sales", "units"], aggs=["sum", "sum"],
                      pct_of="grand")
    # sales grand=500, units grand=10. Percent is computed per field.
    hdr = out[0]
    x = out[1]
    assert float(x[hdr.index("East - sum(sales)")]) == pytest.approx(100 / 500 * 100)
    assert float(x[hdr.index("East - sum(units)")]) == pytest.approx(2 / 10 * 100)


def test_pivot_table_multi_value_errors():
    with pytest.raises(PivotError):
        pivot_table(MARGIN_ROWS, "category", "region",
                    value_cols=["sales", "units"], aggs=["sum"])  # length mismatch
    with pytest.raises(PivotError):
        pivot_table(MARGIN_ROWS, "category", "region", value_cols=[])  # empty
    with pytest.raises(PivotError):
        pivot_table(MARGIN_ROWS, "category", "region")  # no value spec at all
