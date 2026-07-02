"""Array-aware IFERROR / IFNA: a spilled array with per-cell errors is caught
element-wise, exactly like the dynamic-array IF. Scalars keep their old
behaviour."""

from __future__ import annotations

from abax.core.errors import CellError
from abax.core.sheet import Sheet


def _col(s, refs):
    return [s.get(r) for r in refs]


# --- scalar behaviour is unchanged -----------------------------------------


def test_iferror_scalar_catches():
    s = Sheet()
    s.set("A1", "=IFERROR(1/0, 42)")
    assert s.get("A1") == 42


def test_iferror_scalar_passes_through():
    s = Sheet()
    s.set("A1", "=IFERROR(10, 42)")
    assert s.get("A1") == 10


def test_ifna_scalar_only_catches_na():
    s = Sheet()
    s.set("A1", "=IFNA(NA(), 7)")
    assert s.get("A1") == 7
    s.set("A2", "=IFNA(1/0, 7)")  # #DIV/0! is not #N/A -> survives
    val = s.get("A2")
    assert isinstance(val, CellError) and val.code == CellError.DIV0


# --- array-aware IFERROR ---------------------------------------------------


def test_iferror_catches_per_cell_error_scalar_fallback():
    s = Sheet()
    for r, v in enumerate([2, 0, 4]):
        s.set_cell(r, 0, str(v))          # A1:A3 = 2,0,4
    s.set("C1", "=IFERROR(10/A1:A3, -1)")  # 10/0 -> #DIV/0! in the middle cell
    assert _col(s, ["C1", "C2", "C3"]) == [5.0, -1.0, 2.5]


def test_iferror_array_with_no_errors_is_unchanged():
    s = Sheet()
    for r, v in enumerate([1, 2, 4]):
        s.set_cell(r, 0, str(v))
    s.set("C1", "=IFERROR(10/A1:A3, -1)")
    assert _col(s, ["C1", "C2", "C3"]) == [10.0, 5.0, 2.5]


def test_iferror_elementwise_array_fallback():
    s = Sheet()
    for r, v in enumerate([2, 0, 4]):
        s.set_cell(r, 0, str(v))          # A1:A3
    for r, v in enumerate([100, 200, 300]):
        s.set_cell(r, 1, str(v))          # B1:B3 = the fallback array
    s.set("D1", "=IFERROR(10/A1:A3, B1:B3)")
    # Only the errored cell is replaced, and it takes the *matching* fallback (200).
    assert _col(s, ["D1", "D2", "D3"]) == [5.0, 200, 2.5]


# --- array-aware IFNA ------------------------------------------------------


def test_ifna_catches_only_na_per_cell():
    s = Sheet()
    for r, v in enumerate([2, 0, 4]):
        s.set_cell(r, 0, str(v))
    # A #N/A in the last row (4>2) is caught; the rest pass through untouched.
    s.set("F1", "=IFNA(IF(A1:A3>2, NA(), A1:A3), -9)")
    assert _col(s, ["F1", "F2", "F3"]) == [2, 0, -9.0]


def test_ifna_leaves_non_na_errors_uncaught():
    s = Sheet()
    for r, v in enumerate([2, 0, 4]):
        s.set_cell(r, 0, str(v))
    s.set("G1", "=IFNA(10/A1:A3, -1)")  # #DIV/0! is not #N/A -> stays an error
    got = _col(s, ["G1", "G2", "G3"])
    assert got[0] == 5.0 and got[2] == 2.5
    assert isinstance(got[1], CellError) and got[1].code == CellError.DIV0


def test_iferror_catches_mixed_error_kinds_element_wise():
    s = Sheet()
    for r, v in enumerate([2, 0, 4]):
        s.set_cell(r, 0, str(v))
    # Row 2 is #DIV/0!; row 3 (4>2) is a forced #N/A — IFERROR catches both.
    s.set("H1", "=IFERROR(IF(A1:A3>2, NA(), 10/A1:A3), -1)")
    assert _col(s, ["H1", "H2", "H3"]) == [5.0, -1.0, -1.0]
