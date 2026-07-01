"""Structural edits (insert/delete row·col) shift named ranges and data
validations, not just cell formulas and conditional-format rules."""

from __future__ import annotations

from abax.core.validation import list_rule
from abax.core.workbook import Workbook


def _wb_with_column():
    wb = Workbook()
    s = wb.sheet
    for i, v in enumerate([10, 20, 30], 1):  # A1=10, A2=20, A3=30
        s.set(f"A{i}", str(v))
    return wb, s


# --- named ranges ----------------------------------------------------------

def test_named_range_shifts_on_row_insert_and_formula_stays_correct():
    wb, s = _wb_with_column()
    wb.names.define("Vals", "A1:A3")
    s.set("C1", "=SUM(Vals)")
    wb.invalidate_caches()
    assert s.get("C1") == 60.0

    s.insert_rows(0, 1)                       # data -> A2:A4, C1 -> C2
    wb.invalidate_caches()
    assert wb.names.lookup("Vals") == "A2:A4"
    assert s.get("C2") == 60.0                # SUM(Vals) still sums the moved data


def test_named_single_cell_shifts_on_row_insert():
    wb, s = _wb_with_column()
    wb.names.define("Tax", "A2")
    s.insert_rows(0, 1)
    assert wb.names.lookup("Tax") == "A3"


def test_named_range_shifts_on_col_insert():
    wb, s = _wb_with_column()
    wb.names.define("Row", "B1:D1")
    s.insert_cols(0, 1)
    assert wb.names.lookup("Row") == "C1:E1"


def test_named_range_clamps_on_partial_delete():
    wb, s = _wb_with_column()
    wb.names.define("Vals", "A2:A5")
    s.delete_rows(2, 2)                        # delete rows 2,3 -> A2:A5 becomes A2:A3
    assert wb.names.lookup("Vals") == "A2:A3"


def test_named_range_removed_when_fully_deleted():
    wb, s = _wb_with_column()
    wb.names.define("Gone", "A2:A3")
    s.delete_rows(1, 2)                        # delete rows 2,3 entirely
    assert wb.names.lookup("Gone") is None


def test_qualified_name_shifts_only_on_matching_sheet():
    wb = Workbook()
    s1 = wb.sheet
    s2 = wb.add_sheet("Sheet2")
    wb.names.define("Q", "Sheet2!A2:A3")

    s1.insert_rows(0, 1)                       # editing Sheet1 must NOT touch Q
    assert wb.names.lookup("Q") == "Sheet2!A2:A3"

    s2.insert_rows(0, 1)                       # editing Sheet2 shifts Q
    assert wb.names.lookup("Q") == "Sheet2!A3:A4"


# --- data validations ------------------------------------------------------

def test_validation_range_shifts_on_row_insert():
    wb = Workbook()
    s = wb.sheet
    s.validations.append((1, 1, 3, 1, list_rule(("a", "b"))))   # rows 1-3, col B
    s.insert_rows(0, 2)
    assert s.validations[0][:4] == (3, 1, 5, 1)
    assert s.validation_for(4, 1) is not None                   # was row 2, now row 4


def test_validation_range_shifts_on_col_insert():
    wb = Workbook()
    s = wb.sheet
    s.validations.append((0, 1, 0, 3, list_rule(("a", "b"))))   # row 0, cols B-D
    s.insert_cols(1, 1)
    assert s.validations[0][:4] == (0, 2, 0, 4)


def test_validation_clamps_on_partial_delete():
    wb = Workbook()
    s = wb.sheet
    s.validations.append((1, 0, 5, 0, list_rule(("a", "b"))))   # rows 1-5, col A
    s.delete_rows(2, 2)                                          # rows 2,3 gone
    assert s.validations[0][:4] == (1, 0, 3, 0)


def test_validation_removed_when_fully_deleted():
    wb = Workbook()
    s = wb.sheet
    s.validations.append((1, 1, 2, 1, list_rule(("a", "b"))))   # rows 1-2
    s.delete_rows(1, 2)
    assert s.validations == []
