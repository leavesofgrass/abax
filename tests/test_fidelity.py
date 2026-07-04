"""Layout & fidelity model (envelope v2): merges, borders, widths/heights, freeze.

Core storage + query + structural shift + envelope round-trip. The GUI wiring
lives elsewhere; this pins the model.
"""

from __future__ import annotations

from abax.core.workbook import Workbook


def _wb():
    wb = Workbook()
    return wb, wb.sheet


def test_merge_clears_interior_keeps_anchor():
    wb, s = _wb()
    s.set("A1", "anchor")
    s.set("B1", "x")
    s.set("B2", "y")
    s.set("A3", "keep")
    s.merge_cells(0, 0, 1, 1)  # A1:B2
    assert s.merge_region(1, 1) == (0, 0, 1, 1)
    assert s.merge_anchor(1, 1) == (0, 0)
    assert s.is_merged(0, 1) and not s.is_merged(2, 0)
    assert s.get_raw(0, 0) == "anchor"          # anchor kept
    assert s.get_raw(0, 1) == "" and s.get_raw(1, 1) == ""  # interior cleared
    assert s.get_raw(2, 0) == "keep"            # outside untouched


def test_merge_normalises_and_drops_overlap():
    wb, s = _wb()
    s.merge_cells(1, 1, 0, 0)                    # given out of order -> A1:B2
    assert s.merges == [(0, 0, 1, 1)]
    s.merge_cells(0, 0, 2, 2)                    # overlaps -> replaces the prior
    assert s.merges == [(0, 0, 2, 2)]
    assert s.unmerge_cells(1, 1) is True
    assert s.merges == [] and s.unmerge_cells(0, 0) is False


def test_borders_and_layout_setters():
    wb, s = _wb()
    s.set_cell_border(0, 0, {"top": "thin", "bottom": "thick"})
    assert s.cell_border(0, 0) == {"top": "thin", "bottom": "thick"}
    s.set_cell_border(0, 0, None)
    assert s.cell_border(0, 0) == {}
    s.set_col_width(2, 140)
    s.set_row_height(3, 30)
    s.set_frozen(1, 2)
    assert s.col_widths == {2: 140} and s.row_heights == {3: 30}
    assert (s.frozen_rows, s.frozen_cols) == (1, 2)


def test_envelope_round_trip():
    wb, s = _wb()
    s.set("A1", "v")
    s.merge_cells(0, 0, 1, 1)
    s.set_cell_border(0, 0, {"left": "thin"})
    s.set_col_width(0, 120)
    s.set_row_height(1, 40)
    s.set_frozen(2, 1)
    s2 = Workbook.from_envelope(wb.to_envelope()).sheet
    assert s2.merges == [(0, 0, 1, 1)]
    assert s2.cell_border(0, 0) == {"left": "thin"}
    assert s2.col_widths == {0: 120} and s2.row_heights == {1: 40}
    assert (s2.frozen_rows, s2.frozen_cols) == (2, 1)


def test_empty_fidelity_keys_are_omitted():
    wb, s = _wb()
    s.set("A1", "1")
    env = wb.to_envelope()
    sheet0 = env["data"]["sheets"][0]
    for key in ("col_widths", "row_heights", "frozen", "borders", "merges"):
        assert key not in sheet0  # lean file when unused


def test_v1_file_loads_with_empty_fidelity():
    old = {"schema_version": 1,
           "data": {"active": 0, "names": {},
                    "sheets": [{"name": "S", "cells": {"A1": "1"}}]}}
    s = Workbook.from_envelope(old).sheet
    assert s.merges == [] and s.col_widths == {} and s.cell_borders == {}
    assert (s.frozen_rows, s.frozen_cols) == (0, 0)


def test_structural_shift_moves_fidelity():
    wb, s = _wb()
    s.merge_cells(0, 0, 1, 1)
    s.set_cell_border(0, 0, {"top": "thin"})
    s.set_row_height(2, 30)
    s.set_col_width(0, 100)
    s.insert_rows(0, 1)                          # rows shift +1
    assert s.merge_region(1, 0) == (1, 0, 2, 1)
    assert s.cell_border(1, 0) == {"top": "thin"}
    assert s.row_heights == {3: 30}
    s.delete_cols(0, 1)                          # col 0 removed
    assert s.col_widths == {}                    # the col-0 width is gone
    assert s.merge_region(1, 0) == (1, 0, 2, 0)  # cols shift -1


def test_merge_fully_deleted_is_dropped():
    wb, s = _wb()
    s.merge_cells(5, 5, 6, 6)
    s.delete_rows(5, 3)
    assert s.merge_region(5, 5) is None and s.merges == []
