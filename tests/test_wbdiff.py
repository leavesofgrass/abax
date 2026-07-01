"""Tests for :mod:`abax.core.wbdiff`."""

from __future__ import annotations

from abax.core.sheet import Sheet
from abax.core.wbdiff import diff_sheets, diff_workbooks, summary
from abax.core.workbook import Workbook


def _sheet(name, cells):
    """Build a Sheet from a {(row, col): raw} mapping."""
    s = Sheet(name)
    for (r, c), raw in cells.items():
        s.set_cell(r, c, raw)
    return s


def test_diff_sheets_changed_added_removed():
    a = _sheet("S", {(0, 0): "1", (0, 1): "keep", (1, 0): "gone"})
    b = _sheet("S", {(0, 0): "2", (0, 1): "keep", (2, 2): "new"})
    changes = diff_sheets(a, b)

    assert changes == [
        {"row": 0, "col": 0, "a": "1", "b": "2", "kind": "changed"},
        {"row": 1, "col": 0, "a": "gone", "b": "", "kind": "removed"},
        {"row": 2, "col": 2, "a": "", "b": "new", "kind": "added"},
    ]


def test_diff_sheets_ordered_by_row_then_col():
    a = _sheet("S", {})
    b = _sheet("S", {(1, 0): "a", (0, 1): "b", (0, 0): "c"})
    coords = [(ch["row"], ch["col"]) for ch in diff_sheets(a, b)]
    assert coords == [(0, 0), (0, 1), (1, 0)]


def test_diff_sheets_identical_is_empty():
    a = _sheet("S", {(0, 0): "x", (3, 4): "=A1+1"})
    b = _sheet("S", {(0, 0): "x", (3, 4): "=A1+1"})
    assert diff_sheets(a, b) == []


def test_diff_workbooks_shared_and_only_sheets():
    wb_a = Workbook.from_sheets([
        _sheet("Data", {(0, 0): "1"}),
        _sheet("OnlyA", {(0, 0): "left"}),
    ])
    wb_b = Workbook.from_sheets([
        _sheet("Data", {(0, 0): "2"}),
        _sheet("OnlyB", {(0, 0): "right"}),
    ])

    diff = diff_workbooks(wb_a, wb_b)

    assert diff["only_in_a"] == ["OnlyA"]
    assert diff["only_in_b"] == ["OnlyB"]
    assert list(diff["sheets"].keys()) == ["Data"]
    assert diff["sheets"]["Data"] == [
        {"row": 0, "col": 0, "a": "1", "b": "2", "kind": "changed"},
    ]


def test_summary_text():
    wb_a = Workbook.from_sheets([
        _sheet("Data", {(0, 0): "1", (1, 0): "gone"}),
        _sheet("OnlyA", {(0, 0): "left"}),
    ])
    wb_b = Workbook.from_sheets([
        _sheet("Data", {(0, 0): "2", (2, 0): "new"}),
    ])

    diff = diff_workbooks(wb_a, wb_b)
    # Data: (0,0) changed, (1,0) removed, (2,0) added -> 1/1/1 over 1 sheet.
    assert summary(diff) == (
        "1 changed, 1 added, 1 removed across 1 sheet(s); 1 sheet only in A"
    )


def test_summary_no_only_sheets():
    wb_a = Workbook.from_sheets([_sheet("Data", {(0, 0): "1"})])
    wb_b = Workbook.from_sheets([_sheet("Data", {(0, 0): "2"})])
    diff = diff_workbooks(wb_a, wb_b)
    assert summary(diff) == "1 changed, 0 added, 0 removed across 1 sheet(s)"
