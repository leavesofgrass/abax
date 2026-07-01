"""Reference shifting (relative recording / fill foundation)."""

from __future__ import annotations

from abax.core.translate import shift_formula, shift_range, shift_reference


def test_shift_single_reference():
    assert shift_reference("A1", 1, 1) == "B2"
    assert shift_reference("B2", 2, 0) == "B4"
    assert shift_reference("C3", 0, -1) == "B3"


def test_absolute_markers_stay_fixed():
    assert shift_reference("$A$1", 5, 5) == "$A$1"
    assert shift_reference("$A1", 2, 9) == "$A3"  # col fixed, row shifts
    assert shift_reference("A$1", 9, 2) == "C$1"  # row fixed, col shifts


def test_offedge_becomes_ref_error():
    assert shift_reference("A1", -1, 0) == "#REF!"
    assert shift_reference("A1", 0, -1) == "#REF!"


def test_shift_range():
    assert shift_range("A1:B2", 1, 1) == "B2:C3"
    assert shift_range("A1:B2", -5, 0) == "#REF!"


def test_shift_formula_relative_refs():
    assert shift_formula("=A1+B1", 1, 0) == "=A2+B2"
    assert shift_formula("=SUM(A1:A3)", 0, 2) == "=SUM(C1:C3)"


def test_shift_formula_mixes_absolute():
    assert shift_formula("=$A$1+B1", 1, 1) == "=$A$1+C2"


def test_shift_formula_preserves_strings_and_funcs():
    out = shift_formula('=IF(A1>0,"up",B1)', 2, 0)
    assert out == '=IF(A3>0,"up",B3)'


def test_non_formula_and_zero_shift_unchanged():
    assert shift_formula("hello", 3, 3) == "hello"
    assert shift_formula("=A1+1", 0, 0) == "=A1+1"
