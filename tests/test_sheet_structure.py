"""Sheet-level row/column insert+delete and error-literal evaluation."""

from __future__ import annotations

from abax.core import Sheet
from abax.core.errors import CellError
from abax.core.workbook import Workbook

# --- error literals --------------------------------------------------------


def test_error_literals_evaluate():
    s = Sheet()
    s.set("A1", "=#REF!")
    s.set("A2", "=#REF!+1")
    s.set("A3", "=IFERROR(#REF!, 99)")
    s.set("A4", "=#N/A")
    s.set("A5", "=#DIV/0!")
    assert isinstance(s.get("A1"), CellError) and str(s.get("A1")) == "#REF!"
    assert str(s.get("A2")) == "#REF!"
    assert s.get("A3") == 99.0
    assert str(s.get("A4")) == "#N/A"
    assert str(s.get("A5")) == "#DIV/0!"


# --- insert / delete rows --------------------------------------------------


def test_insert_rows_shifts_cells_and_formulas():
    s = Sheet()
    s.set("A1", "10")
    s.set("A2", "20")
    s.set("A3", "=A1+A2")
    s.set("B1", "=A3*2")
    s.insert_rows(1, 1)            # insert a blank row before row index 1
    assert s.get_raw(0, 0) == "10"        # A1 unchanged
    assert s.get_raw(2, 0) == "20"        # A2 -> A3
    assert s.get_raw(3, 0) == "=A1+A3"    # A3 -> A4, ref A2 -> A3
    assert s.get("A4") == 30.0
    assert s.get_raw(0, 1) == "=A4*2"     # B1 ref A3 -> A4
    assert s.get("B1") == 60.0


def test_delete_rows_dangling_ref_becomes_ref_error():
    s = Sheet()
    s.set("A1", "5")
    s.set("A2", "=A1*3")
    s.delete_rows(0, 1)           # delete row 1 (A1), which A2 references
    # A2 has moved up to A1 and its ref is now #REF!
    assert s.get_raw(0, 0) == "=#REF!*3"
    assert str(s.get("A1")) == "#REF!"


def test_insert_and_delete_columns():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    s.set("C1", "=A1+B1")
    s.insert_cols(1, 1)           # insert a blank column before B
    assert s.get_raw(0, 3) == "=A1+C1"    # C1 -> D1, ref B1 -> C1
    assert s.get("D1") == 3.0
    s.delete_cols(1, 1)           # delete the blank column -> everything shifts back
    assert s.get_raw(0, 2) == "=A1+B1"
    assert s.get("C1") == 3.0


def test_insert_rows_moves_cell_formats():
    s = Sheet()
    s.set("A2", "0.25")
    s.cell_formats[(1, 0)] = "percent"
    s.insert_rows(0, 1)           # push everything down one
    assert s.get_raw(2, 0) == "0.25"
    assert s.cell_formats.get((2, 0)) == "percent"
    assert (1, 0) not in s.cell_formats


def test_cross_sheet_reference_shifts_within_workbook():
    s1 = Sheet("Sheet1")
    s2 = Sheet("Sheet2")
    _wb = Workbook.from_sheets([s1, s2])      # keep the workbook alive (wires the sheets)
    s1.set("A5", "100")
    s2.set("A1", "=Sheet1!A5 + 1")
    assert s2.get("A1") == 101.0
    s1.insert_rows(0, 1)          # editing Sheet1 shifts the Sheet1!A5 ref on Sheet2
    # re-tokenizing drops internal whitespace (same as translate.shift_formula)
    assert s2.get_raw(0, 0) == "=Sheet1!A6+1"
    assert s2.get("A1") == 101.0  # still resolves (A5 moved to A6)
