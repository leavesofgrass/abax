"""Tests for the stream-to-cells pipe helper (abax.core.pipe)."""

from __future__ import annotations

import pytest

from abax.core.pipe import PipeError, apply_stream, parse_target, split_stream
from abax.core.workbook import Workbook


# --- parse_target -------------------------------------------------------------

def test_parse_target_with_sheet():
    assert parse_target("Sheet1!B3") == ("Sheet1", 2, 1)


def test_parse_target_bare_ref():
    assert parse_target("A1") == (None, 0, 0)


def test_parse_target_range_uses_top_left_anchor():
    assert parse_target("Sheet1!A1:C9") == ("Sheet1", 0, 0)


def test_parse_target_range_normalises_to_top_left():
    # A "reversed" range still anchors at the true top-left.
    assert parse_target("C9:A1") == (None, 0, 0)


def test_parse_target_quoted_sheet_name():
    assert parse_target("'My Sheet'!A1") == ("My Sheet", 0, 0)


@pytest.mark.parametrize("bad", ["", "   ", "Sheet1!", "!A1", "ZZ", "1A", "Sheet1!nope"])
def test_parse_target_malformed_raises(bad):
    with pytest.raises(PipeError):
        parse_target(bad)


# --- split_stream -------------------------------------------------------------

def test_split_stream_csv():
    assert split_stream("a,b\nc,d\n") == [["a", "b"], ["c", "d"]]


def test_split_stream_tab_autodetect():
    assert split_stream("a\tb\nc\td") == [["a", "b"], ["c", "d"]]


def test_split_stream_tab_wins_over_comma():
    # A tab anywhere makes the whole stream tab-delimited; commas stay in-cell.
    assert split_stream("a,1\tb\nc\td") == [["a,1", "b"], ["c", "d"]]


def test_split_stream_single_column_fallback():
    assert split_stream("hello\nworld\n") == [["hello"], ["world"]]


def test_split_stream_csv_quote_stripping():
    # A surrounding double-quote pair is stripped per field; this is a simple
    # field-unquote, NOT a quote-aware RFC-4180 parse (a comma inside quotes is
    # still a delimiter), so keep the sample free of intra-field delimiters.
    assert split_stream('"a","bc"\n"d",e') == [["a", "bc"], ["d", "e"]]


def test_split_stream_explicit_delimiter():
    assert split_stream("a|b\nc|d", delimiter="|") == [["a", "b"], ["c", "d"]]


def test_split_stream_crlf_and_cr():
    assert split_stream("a,b\r\nc,d\rE,f") == [["a", "b"], ["c", "d"], ["E", "f"]]


def test_split_stream_empty_writes_nothing():
    assert split_stream("") == []


def test_split_stream_ragged_is_fine():
    assert split_stream("a,b,c\nd\n") == [["a", "b", "c"], ["d"]]


def test_split_stream_drops_only_one_trailing_blank():
    # Two trailing newlines -> one genuine blank row remains.
    assert split_stream("a\n\n") == [["a"], [""]]


# --- apply_stream -------------------------------------------------------------

def test_apply_stream_lays_grid_and_counts():
    wb = Workbook()
    sheet = wb.sheet
    rows, cells = apply_stream(sheet, "B2", "1,2\n3,4")
    assert (rows, cells) == (2, 4)
    # B2/C2/B3/C3 -> zero-based (1,1) (1,2) (2,1) (2,2).
    assert sheet.get_raw(1, 1) == "1"
    assert sheet.get_raw(1, 2) == "2"
    assert sheet.get_raw(2, 1) == "3"
    assert sheet.get_raw(2, 2) == "4"


def test_apply_stream_empty_writes_nothing():
    wb = Workbook()
    assert apply_stream(wb.sheet, "A1", "") == (0, 0)


def test_apply_stream_ignores_sheet_name_for_write():
    # The sheet-name part of the target does not redirect the write; the passed
    # sheet is the one written.
    wb = Workbook()
    sheet = wb.sheet
    rows, cells = apply_stream(sheet, "Nonexistent!A1", "x")
    assert (rows, cells) == (1, 1)
    assert sheet.get_raw(0, 0) == "x"


def test_apply_stream_bad_target_raises():
    wb = Workbook()
    with pytest.raises(PipeError):
        apply_stream(wb.sheet, "not-a-cell", "x")
