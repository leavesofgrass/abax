"""Reference/context functions (ROW, COLUMN, ROWS, COLUMNS, OFFSET, INDIRECT,
ADDRESS) — they see the calling cell and the raw reference, via EvalContext."""

from __future__ import annotations

import pytest

from abax.core.workbook import Workbook


@pytest.fixture()
def grid():
    wb = Workbook()
    s = wb.sheets[0]
    for r in range(5):
        for c in range(3):
            s.set_cell(r, c, str((r + 1) * 10 + c))  # A1=10, B1=11, A2=20, ...
    return s


def _put_get(sheet, formula, at="E1"):
    sheet.set(at, formula)
    return sheet.get(at)


def test_row_column_no_arg(grid):
    assert _put_get(grid, "=ROW()", "E1") == 1.0       # E1 is row 0
    assert _put_get(grid, "=COLUMN()", "E2") == 5.0     # column E == 5


def test_row_column_of_reference(grid):
    assert _put_get(grid, "=ROW(C4)") == 4.0
    assert _put_get(grid, "=COLUMN(C4)") == 3.0


def test_rows_columns(grid):
    assert _put_get(grid, "=ROWS(A1:A10)") == 10.0
    assert _put_get(grid, "=COLUMNS(A1:C1)") == 3.0


def test_offset_single_cell(grid):
    assert _put_get(grid, "=OFFSET(A1,1,1)") == 21    # B2 == 21


def test_offset_range_in_aggregate(grid):
    assert _put_get(grid, "=SUM(OFFSET(A1,0,0,3,1))") == 60.0   # A1:A3 = 10+20+30
    assert _put_get(grid, "=SUM(OFFSET(A1,0,0,1,3))") == 33.0   # A1:C1 = 10+11+12


def test_offset_negative_is_ref_error(grid):
    assert "REF" in str(_put_get(grid, "=OFFSET(A1,-1,0)")).upper()


def test_indirect(grid):
    assert _put_get(grid, '=INDIRECT("A2")') == 20
    assert _put_get(grid, '=SUM(INDIRECT("A1:A3"))') == 60.0
    assert "REF" in str(_put_get(grid, '=INDIRECT("not a ref")')).upper()


def test_address(grid):
    assert _put_get(grid, "=ADDRESS(2,3)") == "$C$2"
    assert _put_get(grid, "=ADDRESS(2,3,4)") == "C2"
    assert _put_get(grid, "=ADDRESS(2,3,2)") == "C$2"
    assert _put_get(grid, '=ADDRESS(1,1,1,TRUE,"Sheet2")') == "Sheet2!$A$1"


def test_is_function_recognizes_context_names():
    from abax.core.completion import is_function, signature

    for name in ("ROW", "OFFSET", "INDIRECT", "ADDRESS"):
        assert is_function(name)
        assert signature(name).startswith(name + "(")
