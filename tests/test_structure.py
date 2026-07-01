"""Tests for structural formula-reference adjustment (``core.structure``)."""

from __future__ import annotations

from abax.core.structure import (
    REF_ERROR,
    adjust_formula,
    adjust_range,
    adjust_reference,
    shift_coord,
)

# --- shift_coord ----------------------------------------------------------

def test_shift_coord_insert():
    assert shift_coord(5, 3, +1) == 6  # at/after index moves
    assert shift_coord(2, 3, +1) == 2  # before index stays
    assert shift_coord(3, 3, +1) == 4  # exactly at index moves


def test_shift_coord_delete_single():
    assert shift_coord(5, 3, -1) == 4  # after the deleted line
    assert shift_coord(3, 3, -1) is None  # the deleted line
    assert shift_coord(2, 3, -1) == 2  # before the deleted line


def test_shift_coord_delete_multi():
    assert shift_coord(10, 2, -3) == 7  # well past the block
    assert shift_coord(3, 2, -3) is None  # inside the block (2,3,4)
    assert shift_coord(2, 2, -3) is None  # first deleted line
    assert shift_coord(4, 2, -3) is None  # last deleted line
    assert shift_coord(1, 2, -3) == 1  # before the block
    assert shift_coord(5, 2, -3) == 2  # first survivor after block


# Helper: adjust a same-sheet formula on "Sheet1".
def adj(raw, axis, index, delta):
    return adjust_formula(raw, "Sheet1", "Sheet1", axis, index, delta)


# --- insert row at index 4 (1-based row 5) --------------------------------

def test_insert_row():
    assert adj("=A1", "row", 4, 1) == "=A1"  # above, untouched
    assert adj("=A5", "row", 4, 1) == "=A6"  # at index, shifts
    assert adj("=$A$5", "row", 4, 1) == "=$A$6"  # absolute STILL shifts
    assert adj("=B2+A10", "row", 4, 1) == "=B2+A11"
    assert adj("=SUM(A1:A4)", "row", 4, 1) == "=SUM(A1:A4)"  # entirely above
    assert adj("=SUM(A1:A10)", "row", 4, 1) == "=SUM(A1:A11)"  # spans
    assert adj("=SUM(A5:A8)", "row", 4, 1) == "=SUM(A6:A9)"  # entirely below


# --- insert column at index 1 (col B) -------------------------------------

def test_insert_column():
    assert adj("=A1", "col", 1, 1) == "=A1"  # col A untouched
    assert adj("=B1", "col", 1, 1) == "=C1"
    assert adj("=$B$1", "col", 1, 1) == "=$C$1"
    assert adj("=SUM(A1:C1)", "col", 1, 1) == "=SUM(A1:D1)"


# --- delete row at index 4 (1-based row 5) --------------------------------

def test_delete_row():
    assert adj("=A5", "row", 4, -1) == "=#REF!"  # target deleted
    assert adj("=A6", "row", 4, -1) == "=A5"  # below shifts up
    assert adj("=A1", "row", 4, -1) == "=A1"  # above untouched
    assert adj("=SUM(A1:A10)", "row", 4, -1) == "=SUM(A1:A9)"
    assert adj("=SUM(A5:A5)", "row", 4, -1) == "=SUM(#REF!)"  # whole range gone


def test_delete_row_clamps():
    # start endpoint is the deleted row -> clamp start to survivor at index 4
    assert adj("=SUM(A5:A8)", "row", 4, -1) == "=SUM(A5:A7)"
    # end endpoint is the deleted row -> clamp end to index-1 (row 4, 1-based)
    assert adj("=SUM(A2:A5)", "row", 4, -1) == "=SUM(A2:A4)"


def test_delete_multi_row_clamps():
    # delete rows index 2..4 (3 lines).  Range A1:A10 -> A1:A7
    assert adj("=SUM(A1:A10)", "row", 2, -3) == "=SUM(A1:A7)"
    # range fully inside deleted block -> REF_ERROR
    assert adj("=SUM(A3:A4)", "row", 2, -3) == "=SUM(#REF!)"


# --- cross-sheet targeting ------------------------------------------------

def test_cross_sheet_formula_on_other_sheet():
    # editing Sheet1; formula lives on Sheet2. Only the Sheet1! ref shifts.
    out = adjust_formula("=Sheet1!A5 + B5", "Sheet1", "Sheet2", "row", 4, 1)
    assert out == "=Sheet1!A6+B5"


def test_cross_sheet_formula_on_edited_sheet():
    # editing Sheet1; formula on Sheet1. Local ref shifts, Sheet2! ref doesn't.
    out = adjust_formula("=A5 + Sheet2!A5", "Sheet1", "Sheet1", "row", 4, 1)
    assert out == "=A6+Sheet2!A5"


def test_quoted_sheet_name():
    out = adjust_formula("='My Sheet'!A5", "My Sheet", "Other", "row", 4, 1)
    assert out == "='My Sheet'!A6"


def test_sheet_match_case_insensitive():
    out = adjust_formula("=sheet1!A5", "Sheet1", "Other", "row", 4, 1)
    assert out == "=sheet1!A6"


# --- adjust_reference / adjust_range direct -------------------------------

def test_adjust_reference_deleted_single():
    assert adjust_reference("A5", "Sheet1", "Sheet1", "row", 4, -1) == REF_ERROR


def test_adjust_reference_other_sheet_untouched():
    # bare ref on a formula that lives on Sheet2, editing Sheet1 -> no change
    assert adjust_reference("A5", "Sheet1", "Sheet2", "row", 4, 1) == "A5"


def test_adjust_range_preserves_qualifier_and_dollars():
    out = adjust_range("Sheet1!$A$5:$A$8", "Sheet1", "Other", "row", 4, 1)
    assert out == "Sheet1!$A$6:$A$9"


# --- pass-through cases ----------------------------------------------------

def test_non_formula_text_unchanged():
    assert adjust_formula("hello", "Sheet1", "Sheet1", "row", 4, 1) == "hello"
    assert adjust_formula("123", "Sheet1", "Sheet1", "row", 0, -1) == "123"


def test_zero_delta_noop():
    assert adj("=A5", "row", 4, 0) == "=A5"


def test_unparseable_formula_unchanged():
    raw = "=@#$%bad"
    assert adjust_formula(raw, "Sheet1", "Sheet1", "row", 4, 1) == raw
