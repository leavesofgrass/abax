"""A1 <-> R1C1 conversion (used by the XML Spreadsheet format)."""

from __future__ import annotations

from abax.core.r1c1 import (
    formula_a1_to_r1c1,
    formula_r1c1_to_a1,
    ref_a1_to_r1c1,
    ref_r1c1_to_a1,
)


def test_relative_ref_a1_to_r1c1():
    # formula in B2 (row 1, col 1)
    assert ref_a1_to_r1c1("A1", 1, 1) == "R[-1]C[-1]"
    assert ref_a1_to_r1c1("B2", 1, 1) == "RC"
    assert ref_a1_to_r1c1("C2", 1, 1) == "RC[1]"
    assert ref_a1_to_r1c1("B5", 1, 1) == "R[3]C"


def test_absolute_ref_a1_to_r1c1():
    assert ref_a1_to_r1c1("$A$1", 5, 5) == "R1C1"
    assert ref_a1_to_r1c1("$A1", 1, 1) == "R[-1]C1"  # col abs, row rel


def test_ref_r1c1_to_a1_roundtrip():
    for a1, br, bc in [("A1", 1, 1), ("C2", 1, 1), ("$A$1", 3, 4), ("B$5", 0, 0)]:
        r1c1 = ref_a1_to_r1c1(a1, br, bc)
        assert ref_r1c1_to_a1(r1c1, br, bc) == a1


def test_formula_a1_to_r1c1():
    # =A1*2 in cell B1 (row 0, col 1)
    assert formula_a1_to_r1c1("=A1*2", 0, 1) == "=RC[-1]*2"
    assert formula_a1_to_r1c1("=SUM(A1:A3)", 3, 0) == "=SUM(R[-3]C:R[-1]C)"


def test_formula_r1c1_to_a1():
    assert formula_r1c1_to_a1("=RC[-1]*2", 0, 1) == "=A1*2"
    assert formula_r1c1_to_a1("=SUM(R[-3]C:R[-1]C)", 3, 0) == "=SUM(A1:A3)"
    assert formula_r1c1_to_a1("=R1C1+RC[-1]", 0, 1) == "=$A$1+A1"


def test_formula_roundtrip_preserves_strings():
    raw = '=IF(RC[-1]>0,"R1C1",RC[-2])'
    a1 = formula_r1c1_to_a1(raw, 0, 2)
    assert a1 == '=IF(B1>0,"R1C1",A1)'  # the string "R1C1" is untouched
