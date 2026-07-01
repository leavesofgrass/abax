"""Tests for the multi-column sort + filter engine (`core/sortfilter.py`)."""

from __future__ import annotations

import pytest

from abax.core.sortfilter import (
    SortFilterError,
    filter_rows,
    match,
    sort_order,
    sort_rows,
)

# --- single-key sorting ----------------------------------------------------


def test_numeric_ascending():
    rows = [["3"], ["1"], ["2"], ["10"]]
    assert sort_order(rows, [(0, False)]) == [1, 2, 0, 3]


def test_numeric_descending():
    rows = [["3"], ["1"], ["2"], ["10"]]
    assert sort_order(rows, [(0, True)]) == [3, 0, 2, 1]


def test_text_ascending_case_insensitive():
    rows = [["banana"], ["Apple"], ["cherry"]]
    assert sort_rows(rows, [(0, False)]) == [["Apple"], ["banana"], ["cherry"]]


def test_blanks_sort_last_ascending():
    rows = [["2"], [""], ["1"], ["text"]]
    # numbers, then text, then blank last
    assert sort_rows(rows, [(0, False)]) == [["1"], ["2"], ["text"], [""]]


def test_blanks_sort_last_descending():
    rows = [["2"], [""], ["1"], ["text"]]
    order = sort_order(rows, [(0, True)])
    # blank stays last even descending; rest reversed (text, 2, 1)
    assert order[-1] == 1  # the blank row
    assert sort_rows(rows, [(0, True)]) == [["text"], ["2"], ["1"], [""]]


# --- multi-key sorting -----------------------------------------------------


def test_multi_key_primary_asc_secondary_desc():
    rows = [
        ["1", "a"],
        ["1", "c"],
        ["1", "b"],
        ["2", "x"],
    ]
    # primary col0 asc; within col0==1, col1 desc -> c, b, a
    assert sort_rows(rows, [(0, False), (1, True)]) == [
        ["1", "c"],
        ["1", "b"],
        ["1", "a"],
        ["2", "x"],
    ]


def test_sort_order_is_valid_permutation():
    rows = [["3"], ["1"], ["2"], ["2"], ["5"]]
    order = sort_order(rows, [(0, False)])
    assert sorted(order) == list(range(len(rows)))


def test_sort_is_stable_on_equal_keys():
    rows = [["5", "first"], ["5", "second"], ["5", "third"]]
    assert sort_order(rows, [(0, False)]) == [0, 1, 2]


# --- error cases (sorting) -------------------------------------------------


def test_empty_keys_raises():
    with pytest.raises(SortFilterError):
        sort_order([["a"]], [])


def test_sort_out_of_range_col_raises():
    with pytest.raises(SortFilterError):
        sort_order([["a"]], [(3, False)])


# --- match -----------------------------------------------------------------


def test_match_numeric():
    assert match("5", "gt", "3") is True
    assert match("5", "lt", "3") is False
    assert match("5", "ge", "5") is True
    assert match("5", "le", "5") is True
    assert match("5", "eq", "5") is True
    assert match("5", "ne", "3") is True


def test_match_string():
    assert match("apple", "contains", "ppl") is True
    assert match("apple", "ncontains", "xyz") is True
    assert match("apple", "startswith", "ap") is True
    assert match("apple", "endswith", "le") is True
    # case-insensitive
    assert match("Apple", "contains", "PPL") is True


def test_match_blank_nonblank():
    assert match("", "blank") is True
    assert match("x", "blank") is False
    assert match("x", "nonblank") is True
    assert match("", "nonblank") is False


def test_match_between():
    assert match("5", "between", "1|10") is True
    assert match("11", "between", "1|10") is False
    assert match("1", "between", "1|10") is True  # inclusive
    assert match("10", "between", "1|10") is True


def test_match_unknown_op_raises():
    with pytest.raises(SortFilterError):
        match("x", "bogus", "y")


def test_match_falls_back_to_string_when_not_both_numeric():
    # value numeric, operand not -> string compare
    assert match("5", "eq", "5x") is False
    assert match("apple", "gt", "Apple") is False  # equal lower-cased


# --- filter_rows -----------------------------------------------------------


def test_filter_and_of_two_predicates():
    rows = [
        ["1", "apple"],
        ["5", "apricot"],
        ["8", "banana"],
        ["6", "apple"],
    ]
    idx = filter_rows(rows, [(0, "gt", "3"), (1, "startswith", "ap")])
    assert idx == [1, 3]


def test_filter_empty_predicates_returns_all():
    rows = [["a"], ["b"], ["c"]]
    assert filter_rows(rows, []) == [0, 1, 2]


def test_filter_out_of_range_raises():
    with pytest.raises(SortFilterError):
        filter_rows([["a"]], [(2, "eq", "a")])
