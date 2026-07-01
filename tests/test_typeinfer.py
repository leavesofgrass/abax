"""Tests for abax.core.typeinfer — pure-stdlib column type inference."""

from __future__ import annotations

import datetime

from abax.core.typeinfer import (
    coerce,
    infer_column_type,
    infer_types,
    infer_value_type,
)

# --- infer_value_type -----------------------------------------------------


def test_value_int():
    assert infer_value_type("42") == "int"
    assert infer_value_type("-7") == "int"
    assert infer_value_type("+3") == "int"


def test_value_float():
    assert infer_value_type("3.14") == "float"
    assert infer_value_type("1e5") == "float"
    assert infer_value_type("-2.5e-3") == "float"
    assert infer_value_type(".5") == "float"


def test_value_int_not_float():
    # An integer-looking value is "int", never "float".
    assert infer_value_type("100") == "int"


def test_value_bool():
    for word in ("true", "FALSE", "Yes", "no", "True"):
        assert infer_value_type(word) == "bool"


def test_value_date():
    assert infer_value_type("2026-06-29") == "date"


def test_value_bad_date_is_text():
    assert infer_value_type("2026-13-40") == "text"


def test_value_empty():
    assert infer_value_type("") == "empty"


def test_value_text():
    assert infer_value_type("hello") == "text"
    assert infer_value_type("inf") == "text"
    assert infer_value_type("nan") == "text"


# --- infer_column_type ----------------------------------------------------


def test_column_int():
    assert infer_column_type(["1", "2", "3"]) == "int"


def test_column_int_and_float_promotes():
    assert infer_column_type(["1", "2.5"]) == "float"


def test_column_mixed_is_text():
    assert infer_column_type(["1", "x"]) == "text"


def test_column_ignores_empties():
    assert infer_column_type(["1", "", "2", ""]) == "int"
    assert infer_column_type(["1", "", "2.0"]) == "float"


def test_column_all_empty():
    assert infer_column_type(["", "", ""]) == "empty"
    assert infer_column_type([]) == "empty"


def test_column_bool():
    assert infer_column_type(["true", "no", "YES"]) == "bool"


def test_column_date():
    assert infer_column_type(["2026-01-01", "2026-06-29"]) == "date"


# --- infer_types ----------------------------------------------------------


def test_infer_types_with_header():
    rows = [["a", "b"], ["1", "x"], ["2", "y"]]
    assert infer_types(rows) == ["int", "text"]


def test_infer_types_without_header():
    rows = [["1", "x"], ["2", "y"]]
    assert infer_types(rows, header=False) == ["int", "text"]


def test_infer_types_header_only():
    assert infer_types([["a", "b"]]) == []


def test_infer_types_empty():
    assert infer_types([]) == []


def test_infer_types_ragged_rows():
    rows = [["a", "b", "c"], ["1", "2"], ["3", "4", "5"]]
    assert infer_types(rows) == ["int", "int", "int"]


def test_infer_types_mixed_columns():
    rows = [
        ["id", "price", "active", "when"],
        ["1", "9.99", "true", "2026-06-29"],
        ["2", "19", "no", "2026-07-01"],
    ]
    assert infer_types(rows) == ["int", "float", "bool", "date"]


# --- coerce ---------------------------------------------------------------


def test_coerce_int():
    assert coerce("42", "int") == 42
    assert isinstance(coerce("42", "int"), int)


def test_coerce_float():
    assert coerce("3.14", "float") == 3.14


def test_coerce_bool():
    assert coerce("true", "bool") is True
    assert coerce("no", "bool") is False


def test_coerce_date():
    assert coerce("2026-06-29", "date") == datetime.date(2026, 6, 29)


def test_coerce_text():
    assert coerce("hello", "text") == "hello"


def test_coerce_empty_is_none():
    assert coerce("", "int") is None
    assert coerce("", "text") is None
    assert coerce("", "date") is None


def test_coerce_bad_returns_original():
    assert coerce("x", "int") == "x"
    assert coerce("not-a-date", "date") == "not-a-date"
    assert coerce("maybe", "bool") == "maybe"
