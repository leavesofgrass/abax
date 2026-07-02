"""used_bounds() extent tracking — incremental maxes with a lazy rescan.

The extent of the populated cells is tracked as cells are set (adds bump the
maxes in O(1)); a delete of a boundary cell, a bulk load, or a row/col
restructure marks it dirty so the next call rescans. These tests pin that the
optimization returns the same answer a full scan would.
"""

from __future__ import annotations

from abax.core.sheet import Sheet
from abax.core.workbook import Workbook


def _scan_bounds(sheet):
    """A brute-force oracle: the real extent from a full scan (+ spills)."""
    keys = list(sheet._cells)
    mr = max((r for r, _ in keys), default=-1)
    mc = max((c for _, c in keys), default=-1)
    for (ar, ac), grid in sheet._spill_grid.items():
        mr = max(mr, ar + len(grid) - 1)
        mc = max(mc, ac + (len(grid[0]) if grid else 1) - 1)
    return (0, 0) if mr < 0 and not sheet._cells else (mr + 1, mc + 1)


def test_grows_on_add():
    s = Sheet("S")
    assert s.used_bounds() == (0, 0)
    s.set("A1", "1")
    assert s.used_bounds() == (1, 1)
    s.set("C5", "9")
    assert s.used_bounds() == (5, 3) == _scan_bounds(s)


def test_boundary_delete_shrinks():
    s = Sheet("S")
    s.set("A1", "1")
    s.set("C5", "9")  # extent (5, 3)
    assert s.used_bounds() == (5, 3)
    s.set("C5", "")   # delete the boundary cell — extent must shrink
    assert s.used_bounds() == (1, 1) == _scan_bounds(s)


def test_nonboundary_delete_keeps_extent():
    s = Sheet("S")
    s.set("A1", "1")
    s.set("C5", "9")
    s.set("B2", "5")
    assert s.used_bounds() == (5, 3)
    s.set("B2", "")   # interior delete — extent unchanged
    assert s.used_bounds() == (5, 3) == _scan_bounds(s)


def test_delete_one_of_two_boundary_cells():
    # Two cells sharing the max row; deleting one must not shrink that dimension.
    s = Sheet("S")
    s.set("A5", "1")
    s.set("C5", "2")
    assert s.used_bounds() == (5, 3)
    s.set("C5", "")   # max_col drops to 0 (col A), max_row stays 4
    assert s.used_bounds() == (5, 1) == _scan_bounds(s)


def test_bulk_load_extent():
    s = Sheet("S")
    s.set_cells_bulk([(0, 0, "1"), (9, 4, "2"), (3, 3, "3")])
    assert s.used_bounds() == (10, 5) == _scan_bounds(s)


def test_restructure_updates_extent():
    wb = Workbook()
    s = wb.sheets[0]
    s.set("A1", "1")
    s.set("C3", "9")
    assert s.used_bounds() == (3, 3)
    s.insert_rows(0, 2)  # everything shifts down two rows
    assert s.used_bounds() == (5, 3) == _scan_bounds(s)
    s.delete_cols(2, 1)  # drop column C
    assert s.used_bounds() == _scan_bounds(s)


def test_spill_counts_toward_extent():
    wb = Workbook()
    s = wb.sheets[0]
    s.set("A1", "=SEQUENCE(4)")  # spills into A1:A4
    assert s.used_bounds() == (4, 1) == _scan_bounds(s)
