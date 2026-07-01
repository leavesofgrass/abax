"""Array functions registered into the engine and usable in real formulas."""

from __future__ import annotations

from abax.core.functions import FUNCTIONS
from abax.core.sheet import Sheet


def _sheet():
    s = Sheet()
    for r, (k, v) in enumerate([("a", 1), ("b", 2), ("c", 3), ("b", 2)]):
        s.set_cell(r, 0, k)
        s.set_cell(r, 1, str(v))
    return s


def test_all_registered():
    for name in ("XLOOKUP", "UNIQUE", "SORT", "FILTER", "SEQUENCE"):
        assert name in FUNCTIONS


def test_xlookup_in_formula():
    s = _sheet()
    s.set_cell(0, 3, '=XLOOKUP("c", A1:A4, B1:B4)')
    assert s.get_value(0, 3) == 3


def test_sum_unique_composes():
    s = _sheet()
    s.set_cell(0, 3, "=SUM(UNIQUE(B1:B4))")     # unique(1,2,3,2)=1,2,3 -> 6
    assert s.get_value(0, 3) == 6


def test_count_filter_composes():
    s = _sheet()
    # FILTER(B, B) keeps truthy values; all 4 are non-zero -> COUNT 4
    s.set_cell(0, 3, "=COUNT(FILTER(B1:B4, B1:B4))")
    assert s.get_value(0, 3) == 4


def test_sum_sequence():
    s = Sheet()
    s.set_cell(0, 0, "=SUM(SEQUENCE(5))")       # 1+2+3+4+5
    assert s.get_value(0, 0) == 15
