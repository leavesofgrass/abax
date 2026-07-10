"""Tests for the field-area pivot builder (core.pivotspec)."""

from __future__ import annotations

import pytest

from abax.core.pivot import PivotError
from abax.core.pivotspec import (
    ALL,
    PivotSpec,
    build_pivot,
    distinct_values,
    field_names,
    filter_values,
)

# region -> quarter -> product -> sales
DATA = [
    ["region", "quarter", "product", "sales"],
    ["West", "Q1", "A", "10"],
    ["West", "Q2", "A", "20"],
    ["East", "Q1", "B", "5"],
    ["East", "Q2", "B", "7"],
    ["West", "Q1", "B", "3"],
]


def test_field_names_and_distinct():
    assert field_names(DATA) == ["region", "quarter", "product", "sales"]
    assert distinct_values(DATA, "region") == ["East", "West"]
    assert distinct_values(DATA, "quarter") == ["Q1", "Q2"]


def test_filter_values_offers_all_then_distinct():
    # filter_values reuses distinct_values but leads with the ALL sentinel so a
    # picker can default to "no restriction".
    assert filter_values(DATA, "quarter") == [ALL, "Q1", "Q2"]
    assert filter_values(DATA, "region") == [ALL, "East", "West"]


def test_group_by_mode_single_value():
    spec = PivotSpec(row_fields=["region"], value_fields=["sales"], aggs=["sum"])
    out = build_pivot(DATA, spec)
    assert out[0] == ["region", "sum(sales)"]
    body = {r[0]: r[1] for r in out[1:]}
    assert body["West"] == "33"   # 10 + 20 + 3
    assert body["East"] == "12"   # 5 + 7


def test_group_by_multi_value_merges_columns():
    spec = PivotSpec(row_fields=["region"], value_fields=["sales", "sales"],
                     aggs=["sum", "max"])
    out = build_pivot(DATA, spec)
    assert out[0] == ["region", "sum(sales)", "max(sales)"]
    row = {r[0]: r for r in out[1:]}
    assert row["West"][1] == "33" and row["West"][2] == "20"
    assert row["East"][1] == "12" and row["East"][2] == "7"


def test_pivot_mode_with_column_field():
    spec = PivotSpec(row_fields=["region"], column_field="quarter",
                     value_fields=["sales"], aggs=["sum"])
    out = build_pivot(DATA, spec)
    assert out[0] == ["region", "Q1", "Q2"]
    by_region = {r[0]: r for r in out[1:]}
    assert by_region["West"] == ["West", "13", "20"]   # Q1: 10+3, Q2: 20
    assert by_region["East"] == ["East", "5", "7"]


def test_pivot_multi_row_yields_nested_columns():
    # Two row fields + a column field → separate leading columns (true nested
    # rows), NOT a single "region / product" joined string.
    spec = PivotSpec(row_fields=["region", "product"], column_field="quarter",
                     value_fields=["sales"], aggs=["sum"])
    out = build_pivot(DATA, spec)
    assert out[0] == ["region", "product", "Q1", "Q2"]
    assert "region / product" not in out[0]
    body = {(r[0], r[1]): r for r in out[1:]}
    assert body[("East", "B")] == ["East", "B", "5", "7"]
    assert body[("West", "A")] == ["West", "A", "10", "20"]
    assert body[("West", "B")] == ["West", "B", "3", ""]   # no Q2 for West/B


def test_pivot_nested_rows_with_margins():
    # Nested rows still pass margins through: Total row keeps its label in the
    # first leading column, the rest blank.
    spec = PivotSpec(row_fields=["region", "product"], column_field="quarter",
                     value_fields=["sales"], aggs=["sum"], margins=True)
    out = build_pivot(DATA, spec)
    assert out[0] == ["region", "product", "Q1", "Q2", "Total"]
    assert out[-1] == ["Total", "", "18", "27", "45"]


def test_pivot_single_row_with_column_unchanged():
    # The single-row-field path must stay exactly as before (one index column).
    spec = PivotSpec(row_fields=["region"], column_field="quarter",
                     value_fields=["sales"], aggs=["sum"])
    out = build_pivot(DATA, spec)
    assert out[0] == ["region", "Q1", "Q2"]


def test_filters_restrict_rows():
    spec = PivotSpec(row_fields=["region"], value_fields=["sales"], aggs=["sum"],
                     filters={"quarter": "Q1"})
    out = build_pivot(DATA, spec)
    body = {r[0]: r[1] for r in out[1:]}
    assert body["West"] == "13"   # only Q1 rows: 10 + 3
    assert body["East"] == "5"


def test_filter_all_is_noop():
    spec = PivotSpec(row_fields=["region"], value_fields=["sales"], aggs=["sum"],
                     filters={"quarter": ALL})
    out = build_pivot(DATA, spec)
    assert {r[0]: r[1] for r in out[1:]}["West"] == "33"


def test_margins_and_pct_pass_through():
    spec = PivotSpec(row_fields=["region"], column_field="quarter",
                     value_fields=["sales"], aggs=["sum"], margins=True)
    out = build_pivot(DATA, spec)
    assert out[0][-1] == "Total"           # grand-total column
    assert out[-1][0] == "Total"           # grand-total row


def test_normalized_aggs_pads_default_sum():
    spec = PivotSpec(row_fields=["region"], value_fields=["sales", "sales"], aggs=["max"])
    assert spec.normalized_aggs() == ["max", "sum"]


def test_missing_required_areas_raise():
    with pytest.raises(PivotError):
        build_pivot(DATA, PivotSpec(value_fields=["sales"]))       # no rows
    with pytest.raises(PivotError):
        build_pivot(DATA, PivotSpec(row_fields=["region"]))        # no values
    with pytest.raises(PivotError):
        build_pivot([], PivotSpec(row_fields=["r"], value_fields=["v"]))  # no data
