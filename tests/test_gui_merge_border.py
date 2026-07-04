"""Grid GUI for the fidelity model: merged cells, borders, and speak-on-move.

Runs the real ``MainWindow`` offscreen (like ``test_gui_grid``). Skips cleanly
when the Qt binding is not installed, so the zero-optional-deps suite stays green.
Covers:
  * merge_selection -> is_merged + interior cleared + view spans + anchor cursor;
  * cursor navigation SKIPS merged interior cells (lands on / exits the anchor);
  * unmerge_selection removes the region;
  * the border dialog spec + _apply_borders writes / clears borders over a range,
    and the delegate paints them without error;
  * the speak-on-move hook is a harmless no-op with no TTS backend installed.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import (  # noqa: E402
    QApplication,
    QTableWidgetSelectionRange,
)
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    _win = MainWindow(Settings())
    yield _win
    from abax.gui._qtcompat import QEvent as _QEvent
    _win.deleteLater()
    app.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    app.processEvents()


def _select(win, r1, c1, r2, c2):
    # Set the current cell first (it collapses the selection to one cell), then
    # lay down the range so ``selectedRanges`` reports the whole rectangle —
    # matching how a real range selection reaches _selected_bounds().
    win._table.setCurrentCell(r1, c1)
    win._table.clearSelection()
    win._table.setRangeSelected(QTableWidgetSelectionRange(r1, c1, r2, c2), True)


# --- merge / unmerge ------------------------------------------------------

def test_merge_selection_clears_interior_and_spans(win):
    sheet = win._doc.workbook.sheet
    win._commit_cell(0, 0, "anchor")
    win._commit_cell(0, 1, "x")
    win._commit_cell(1, 1, "y")
    _select(win, 0, 0, 1, 1)             # A1:B2
    win.merge_selection()
    # Core state: region registered, interior cleared, anchor kept.
    assert sheet.is_merged(0, 1) and sheet.merge_region(1, 1) == (0, 0, 1, 1)
    assert sheet.get_raw(0, 0) == "anchor"
    assert sheet.get_raw(0, 1) == "" and sheet.get_raw(1, 1) == ""
    # The view spans the region as one cell (2 rows x 2 cols at the anchor).
    assert win._table.rowSpan(0, 0) == 2
    assert win._table.columnSpan(0, 0) == 2
    # The cursor lands on the anchor after merging.
    assert (win._table.currentRow(), win._table.currentColumn()) == (0, 0)


def test_merge_single_cell_is_noop(win):
    sheet = win._doc.workbook.sheet
    _select(win, 3, 3, 3, 3)
    win.merge_selection()
    assert sheet.merges == []


def test_unmerge_selection_removes_region(win):
    sheet = win._doc.workbook.sheet
    _select(win, 0, 0, 2, 1)             # A1:B3
    win.merge_selection()
    assert sheet.merge_region(1, 0) == (0, 0, 2, 1)
    # A single cell anywhere inside the merge unmerges the whole region.
    _select(win, 1, 0, 1, 0)
    win.unmerge_selection()
    assert sheet.merges == []
    assert win._table.rowSpan(0, 0) == 1 and win._table.columnSpan(0, 0) == 1


def test_unmerge_with_no_merge_is_noop(win):
    sheet = win._doc.workbook.sheet
    _select(win, 5, 5, 5, 5)
    win.unmerge_selection()
    assert sheet.merges == []


# --- navigation skips merged interiors -----------------------------------

def test_click_into_merge_lands_on_anchor(win):
    _select(win, 1, 1, 2, 2)             # B2:C3
    win.merge_selection()
    # Point the cursor at an interior cell -> snaps to the anchor (B2).
    win._table.setCurrentCell(2, 2)
    assert (win._table.currentRow(), win._table.currentColumn()) == (1, 1)


def test_move_down_exits_below_merge(win):
    _select(win, 1, 1, 2, 2)             # B2:C3 (2 rows tall)
    win.merge_selection()
    win._table.setCurrentCell(1, 1)      # on the anchor
    win._table.move_cursor_by(1, 0)      # one step down
    # Must skip the merged interior (row 2) and land just below the region.
    assert (win._table.currentRow(), win._table.currentColumn()) == (3, 1)


def test_move_right_exits_past_merge(win):
    _select(win, 1, 1, 2, 2)             # B2:C3 (2 cols wide)
    win.merge_selection()
    win._table.setCurrentCell(1, 1)
    win._table.move_cursor_by(0, 1)      # one step right
    assert (win._table.currentRow(), win._table.currentColumn()) == (1, 3)


def test_move_up_into_tall_merge_lands_on_anchor(win):
    _select(win, 1, 0, 3, 0)             # A2:A4 (rows 1-3, 3 rows tall)
    win.merge_selection()
    win._table.setCurrentCell(4, 0)      # just below the merge (A5)
    win._table.move_cursor_by(-1, 0)     # up into row 3 (a merged interior)
    # Entering the merge lands on the anchor A2, not a hidden interior row.
    assert (win._table.currentRow(), win._table.currentColumn()) == (1, 0)


def test_move_up_exits_above_merge(win):
    _select(win, 2, 0, 4, 0)             # A3:A5 (rows 2-4)
    win.merge_selection()
    win._table.setCurrentCell(2, 0)      # on the anchor (A3)
    win._table.move_cursor_by(-1, 0)     # up out of the merge
    # Exiting steps to the cell just above the region (A2 = row 1).
    assert (win._table.currentRow(), win._table.currentColumn()) == (1, 0)


def test_move_down_into_merge_lands_on_anchor(win):
    _select(win, 3, 0, 3, 2)             # A4:C4 (one row, cols 0-2)
    win.merge_selection()
    win._table.setCurrentCell(2, 0)      # above the merge (A3)
    win._table.move_cursor_by(1, 0)      # down into the merged row
    # A one-row merge: entering lands on the anchor A4.
    assert (win._table.currentRow(), win._table.currentColumn()) == (3, 0)


# --- borders --------------------------------------------------------------

def test_border_dialog_spec_all_and_none(win):
    from abax.gui.dialogs.border_dialog import BorderDialog

    dlg = BorderDialog(win)
    dlg._style.setCurrentText("medium")
    dlg._select_all()
    edges, clear = dlg.border_spec()
    assert edges == {"top": "medium", "bottom": "medium",
                     "left": "medium", "right": "medium"}
    assert clear is False
    dlg._select_none()
    edges, clear = dlg.border_spec()
    assert edges == {} and clear is True
    dlg.deleteLater()


def test_apply_borders_over_selection(win):
    sheet = win._doc.workbook.sheet
    _select(win, 0, 0, 1, 1)
    win._apply_borders({"top": "thin", "left": "thick"}, clear=False)
    for r in range(2):
        for c in range(2):
            assert sheet.cell_border(r, c) == {"top": "thin", "left": "thick"}


def test_apply_borders_merges_with_existing(win):
    sheet = win._doc.workbook.sheet
    _select(win, 0, 0, 0, 0)
    win._apply_borders({"top": "thin"}, clear=False)
    win._apply_borders({"bottom": "thick"}, clear=False)
    # A second edge is added, not replaced.
    assert sheet.cell_border(0, 0) == {"top": "thin", "bottom": "thick"}


def test_clear_borders(win):
    sheet = win._doc.workbook.sheet
    _select(win, 0, 0, 1, 0)
    win._apply_borders({"top": "thin"}, clear=False)
    assert sheet.cell_border(0, 0) == {"top": "thin"}
    win._apply_borders({}, clear=True)
    assert sheet.cell_border(0, 0) == {} and sheet.cell_border(1, 0) == {}


def test_empty_spec_no_clear_is_noop(win):
    sheet = win._doc.workbook.sheet
    _select(win, 0, 0, 0, 0)
    win._apply_borders({"top": "medium"}, clear=False)
    win._apply_borders({}, clear=False)   # nothing chosen: must not wipe
    assert sheet.cell_border(0, 0) == {"top": "medium"}


def test_delegate_paints_borders_without_error(win):
    from abax.gui._qtcompat import QImage, QPainter, QRect

    try:
        from PySide6.QtWidgets import QStyleOptionViewItem
    except ImportError:  # pragma: no cover - depends on the installed binding
        from PyQt6.QtWidgets import QStyleOptionViewItem

    sheet = win._doc.workbook.sheet
    sheet.set_cell_border(0, 0, {"top": "thin", "bottom": "medium",
                                 "left": "thick", "right": "thin"})
    win.refresh_table()
    delegate = win._table.itemDelegate()
    img = QImage(60, 24, QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 60, 24)
    delegate.paint(painter, opt, win._table.model().index(0, 0))
    painter.end()  # no exception == borders rendered


# --- speak-on-move hook ---------------------------------------------------

def test_speak_hook_noops_without_backend(win):
    # No abax.engine.tts backend is installed in the thin CI env, so the guarded
    # import fails and speak_current must simply return without raising — even
    # with the setting explicitly turned on.
    win._settings.speak_on_move = True
    win._table.speak_current(0, 0)        # must not raise
    # The mixin delegate hook the integrator wires is likewise safe.
    win.speak_active_cell(0, 0, -1, -1)


def test_speak_hook_disabled_by_default(win):
    # Off by default: the hook returns before even attempting the optional import.
    assert win._settings.speak_on_move is False
    win._table.speak_current(0, 0)        # no-op, no raise


def test_speak_hook_uses_merge_anchor(win, monkeypatch):
    # With a stub backend and the setting on, moving onto a merged interior
    # speaks the anchor's ref + value, not the empty interior cell.
    import sys
    import types

    spoken = []
    mod = types.ModuleType("abax.engine.tts")
    mod.speak = lambda text: spoken.append(text)
    monkeypatch.setitem(sys.modules, "abax.engine.tts", mod)

    win._commit_cell(0, 0, "top-left")
    _select(win, 0, 0, 1, 1)
    win.merge_selection()
    win._settings.speak_on_move = True
    win._table.speak_current(1, 1)        # interior of the merge
    assert spoken == ["A1 top-left"]      # anchor ref + value, not "B2"
