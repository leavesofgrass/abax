"""Tests for :mod:`abax.core.search` — find and replace over a Sheet."""

from __future__ import annotations

import pytest

from abax.core.search import (
    Match,
    SearchError,
    SearchOptions,
    find_all,
    replace_all,
    replace_match,
)
from abax.core.sheet import Sheet


def make_sheet(cells: dict[str, str] | None = None) -> Sheet:
    """Build a Sheet and set the given A1 -> raw mappings."""
    sheet = Sheet()
    for ref, raw in (cells or {}).items():
        sheet.set(ref, raw)
    return sheet


# --- find ----------------------------------------------------------------


def test_plain_text_find():
    sheet = make_sheet({"A1": "hello", "A2": "world", "A3": "hello world"})
    opts = SearchOptions(regex=False)
    refs = [m.ref for m in find_all(sheet, "hello", opts)]
    assert refs == ["A1", "A3"]


def test_regex_find():
    sheet = make_sheet({"A1": "cat", "A2": "dog", "A3": "cot"})
    opts = SearchOptions(regex=True)
    refs = [m.ref for m in find_all(sheet, "c.t", opts)]
    assert refs == ["A1", "A3"]


def test_match_indices():
    sheet = make_sheet({"A1": "xxabcxx"})
    opts = SearchOptions(regex=False)
    (m,) = find_all(sheet, "abc", opts)
    assert (m.start, m.end, m.text) == (2, 5, "xxabcxx")


def test_case_insensitive_default():
    sheet = make_sheet({"A1": "Hello", "A2": "HELLO"})
    refs = [m.ref for m in find_all(sheet, "hello", SearchOptions(regex=False))]
    assert refs == ["A1", "A2"]


def test_case_sensitive():
    sheet = make_sheet({"A1": "Hello", "A2": "hello"})
    opts = SearchOptions(regex=False, case_sensitive=True)
    refs = [m.ref for m in find_all(sheet, "hello", opts)]
    assert refs == ["A2"]


def test_whole_cell():
    sheet = make_sheet({"A1": "cat", "A2": "category", "A3": "a cat"})
    opts = SearchOptions(regex=False, whole_cell=True)
    refs = [m.ref for m in find_all(sheet, "cat", opts)]
    assert refs == ["A1"]


def test_scoped_range():
    sheet = make_sheet(
        {"A1": "x", "B1": "x", "A2": "x", "B2": "x", "C3": "x"}
    )
    opts = SearchOptions(regex=False)
    refs = [m.ref for m in find_all(sheet, "x", opts, rng="A1:B2")]
    assert refs == ["A1", "B1", "A2", "B2"]


def test_skips_empty_cells():
    sheet = make_sheet({"A1": "hit", "A3": "hit"})
    refs = [m.ref for m in find_all(sheet, "hit", SearchOptions(regex=False))]
    assert refs == ["A1", "A3"]


def test_find_display_vs_formula():
    sheet = make_sheet({"A1": "2", "A2": "3", "A3": "=A1+A2"})
    # Formula text: the literal "=A1+A2" contains "A1".
    formula = find_all(sheet, "A1", SearchOptions(regex=False, use_formula=True))
    assert [m.ref for m in formula] == ["A3"]
    # Display text: A3 shows "5"; searching display for "5" finds A3.
    display = find_all(sheet, "5", SearchOptions(regex=False, use_formula=False))
    assert [m.ref for m in display] == ["A3"]


# --- replace -------------------------------------------------------------


def test_replace_count():
    sheet = make_sheet({"A1": "foo", "A2": "foobar", "A3": "baz"})
    n = replace_all(sheet, "foo", "X", SearchOptions(regex=False))
    assert n == 2
    assert sheet.get_raw(0, 0) == "X"
    assert sheet.get_raw(1, 0) == "Xbar"
    assert sheet.get_raw(2, 0) == "baz"


def test_replace_no_change_not_counted():
    sheet = make_sheet({"A1": "abc"})
    n = replace_all(sheet, "zzz", "X", SearchOptions(regex=False))
    assert n == 0


def test_regex_backreference_replace():
    sheet = make_sheet({"A1": "a=b", "A2": "x=y"})
    n = replace_all(sheet, r"(\w+)=(\w+)", r"\2=\1", SearchOptions(regex=True))
    assert n == 2
    assert sheet.get_raw(0, 0) == "b=a"
    assert sheet.get_raw(1, 0) == "y=x"


def test_replace_scoped_range():
    sheet = make_sheet({"A1": "hit", "B1": "hit", "C1": "hit"})
    n = replace_all(sheet, "hit", "X", SearchOptions(regex=False), rng="A1:B1")
    assert n == 2
    assert sheet.get_raw(0, 0) == "X"
    assert sheet.get_raw(0, 1) == "X"
    assert sheet.get_raw(0, 2) == "hit"


def test_on_set_callback_fires():
    sheet = make_sheet({"A1": "foo", "A2": "foo"})
    seen: list[tuple[str, str]] = []
    n = replace_all(
        sheet, "foo", "bar", SearchOptions(regex=False),
        on_set=lambda ref, new: seen.append((ref, new)),
    )
    assert n == 2
    assert seen == [("A1", "bar"), ("A2", "bar")]


def test_replace_match_changes_single_cell():
    sheet = make_sheet({"A1": "foo", "A2": "foo"})
    matches = find_all(sheet, "foo", SearchOptions(regex=False))
    seen: list[tuple[str, str]] = []
    changed = replace_match(
        sheet, matches[0], "foo", "bar", SearchOptions(regex=False),
        on_set=lambda ref, new: seen.append((ref, new)),
    )
    assert changed is True
    assert sheet.get_raw(0, 0) == "bar"
    assert sheet.get_raw(1, 0) == "foo"  # untouched
    assert seen == [("A1", "bar")]


def test_replace_match_no_change_returns_false():
    sheet = make_sheet({"A1": "foo"})
    m = Match(row=0, col=0, ref="A1", text="foo", start=0, end=3)
    changed = replace_match(sheet, m, "zzz", "X", SearchOptions(regex=False))
    assert changed is False
    assert sheet.get_raw(0, 0) == "foo"


# --- options defaults & errors ------------------------------------------


def test_default_options_is_regex():
    # Default SearchOptions() has regex=True; "c.t" matches "cat".
    sheet = make_sheet({"A1": "cat"})
    assert [m.ref for m in find_all(sheet, "c.t")] == ["A1"]


def test_invalid_regex_raises_search_error():
    sheet = make_sheet({"A1": "x"})
    with pytest.raises(SearchError):
        find_all(sheet, "(unclosed", SearchOptions(regex=True))


def test_invalid_regex_raises_on_replace():
    sheet = make_sheet({"A1": "x"})
    with pytest.raises(SearchError):
        replace_all(sheet, "[", "y", SearchOptions(regex=True))


def test_plain_text_special_chars_escaped():
    # In non-regex mode, "a.c" is literal and must NOT match "abc".
    sheet = make_sheet({"A1": "abc", "A2": "a.c"})
    refs = [m.ref for m in find_all(sheet, "a.c", SearchOptions(regex=False))]
    assert refs == ["A2"]
