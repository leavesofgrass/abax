"""Tests for the modern array functions (XLOOKUP, UNIQUE, SORT, FILTER, SEQUENCE)."""

from __future__ import annotations

from abax.core.arrayfuncs import (
    EAGER,
    filter_,
    register,
    sequence,
    sort,
    unique,
    xlookup,
)
from abax.core.errors import CellError
from abax.core.values import RangeValue


def _col(values):
    """Build a single-column RangeValue from a flat list of values."""
    return RangeValue([[v] for v in values])


# --- XLOOKUP ---------------------------------------------------------------


def test_xlookup_exact_hit():
    lookup = _col(["apple", "banana", "cherry"])
    ret = _col([3, 5, 8])
    assert xlookup(["banana", lookup, ret]) == 5


def test_xlookup_not_found_na():
    lookup = _col(["apple", "banana"])
    ret = _col([3, 5])
    result = xlookup(["mango", lookup, ret])
    assert isinstance(result, CellError)
    assert result.code == CellError.NA


def test_xlookup_not_found_with_default():
    lookup = _col(["apple", "banana"])
    ret = _col([3, 5])
    assert xlookup(["mango", lookup, ret, "missing"]) == "missing"


def test_xlookup_first_index_wins():
    lookup = _col(["x", "y", "x"])
    ret = _col([1, 2, 3])
    assert xlookup(["x", lookup, ret]) == 1


# --- UNIQUE ----------------------------------------------------------------


def test_unique_order_and_dedup():
    rng = _col([3, 1, 3, 2, 1, 2])
    assert unique([rng]) == [3, 1, 2]


def test_unique_skips_blanks():
    rng = _col(["a", "", "b", None, "a"])
    assert unique([rng]) == ["a", "b"]


# --- SORT ------------------------------------------------------------------


def test_sort_numeric_ascending():
    rng = _col([3, 1, 2])
    assert sort([rng]) == [1, 2, 3]


def test_sort_numeric_descending():
    rng = _col([3, 1, 2])
    assert sort([rng, False]) == [3, 2, 1]


def test_sort_text_ascending():
    rng = _col(["cherry", "apple", "banana"])
    assert sort([rng]) == ["apple", "banana", "cherry"]


def test_sort_text_descending():
    rng = _col(["cherry", "apple", "banana"])
    assert sort([rng, False]) == ["cherry", "banana", "apple"]


def test_sort_blanks_last():
    rng = _col([2, "", 1])
    assert sort([rng]) == [1, 2, ""]


# --- FILTER ----------------------------------------------------------------


def test_filter_by_condition_column():
    values = _col(["a", "b", "c", "d"])
    condition = _col([1, 0, 1, 0])
    assert filter_([values, condition]) == ["a", "c"]


def test_filter_length_mismatch_value_error():
    values = _col(["a", "b", "c"])
    condition = _col([1, 0])
    result = filter_([values, condition])
    assert isinstance(result, CellError)
    assert result.code == CellError.VALUE


# --- SEQUENCE --------------------------------------------------------------


def test_sequence_rows_only():
    assert sequence([4]) == [1, 2, 3, 4]


def test_sequence_rows_cols():
    assert sequence([2, 3]) == [1, 2, 3, 4, 5, 6]


def test_sequence_start_and_step():
    assert sequence([4, 1, 10, 5]) == [10, 15, 20, 25]


def test_sequence_step_only_with_defaults():
    assert sequence([3, 1, 0, 2]) == [0, 2, 4]


# --- registry --------------------------------------------------------------


def test_eager_has_five_uppercase_keys():
    assert set(EAGER) == {"XLOOKUP", "UNIQUE", "SORT", "FILTER", "SEQUENCE"}
    assert all(name.isupper() for name in EAGER)
    assert all(callable(fn) for fn in EAGER.values())


def test_register_updates_dict():
    functions: dict = {}
    register(functions)
    assert functions == EAGER
    assert functions["FILTER"] is filter_
