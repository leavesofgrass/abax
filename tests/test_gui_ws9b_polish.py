"""WS9b polish: number-format undo, format painter, in-cell signature tooltip."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    w = MainWindow(Settings())
    yield w
    from abax.gui._qtcompat import QEvent
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


# --- (1) number-format undo ---------------------------------------------


def test_number_format_is_undoable(win):
    sheet = win._doc.workbook.sheet
    sheet.set_cell(0, 0, "1234.5")
    win._table.setCurrentCell(0, 0)

    # Start from a known format so we can assert the prior one is restored.
    win.set_number_format("0.00")
    assert sheet.cell_formats.get((0, 0)) == "0.00"

    win.set_number_format("0%")
    assert sheet.cell_formats.get((0, 0)) == "0%"

    assert win._doc.undo()
    # The active sheet is re-read after load_envelope.
    assert win._doc.workbook.sheet.cell_formats.get((0, 0)) == "0.00"


def test_number_format_general_undoable(win):
    sheet = win._doc.workbook.sheet
    sheet.set_cell(0, 0, "5")
    win._table.setCurrentCell(0, 0)
    win.set_number_format("0.00")
    assert sheet.cell_formats.get((0, 0)) == "0.00"

    win.set_number_format("general")   # clears the format
    assert (0, 0) not in win._doc.workbook.sheet.cell_formats

    assert win._doc.undo()
    assert win._doc.workbook.sheet.cell_formats.get((0, 0)) == "0.00"


# --- (2) format painter --------------------------------------------------


def test_copy_paste_format_copies_style_and_format_one_undo(win):
    from abax.core.format.cellstyle import CellStyle

    sheet = win._doc.workbook.sheet
    # A styled + formatted source cell, and a plain target range.
    sheet.cell_styles[(0, 0)] = CellStyle(bold=True, bg_color="#ff0000")
    sheet.cell_formats[(0, 0)] = "0.00"
    sheet.set_cell(2, 0, "1")
    sheet.set_cell(3, 0, "2")

    win._table.setCurrentCell(0, 0)
    win.copy_format()

    # Select the plain range A3:A4 and paste the picked format.
    from abax.gui._qtcompat import QTableWidgetSelectionRange
    win._table.setCurrentCell(2, 0)
    win._table.clearSelection()
    win._table.setRangeSelected(QTableWidgetSelectionRange(2, 0, 3, 0), True)

    win.paste_format()

    for key in ((2, 0), (3, 0)):
        assert sheet.cell_styles[key] == CellStyle(bold=True, bg_color="#ff0000")
        assert sheet.cell_formats[key] == "0.00"

    # One undo step reverts the whole paste (both cells).
    assert win._doc.undo()
    sheet2 = win._doc.workbook.sheet
    assert (2, 0) not in sheet2.cell_styles
    assert (3, 0) not in sheet2.cell_styles
    assert (2, 0) not in sheet2.cell_formats
    assert (3, 0) not in sheet2.cell_formats


def test_paste_format_without_pick_is_noop(win):
    # A fresh window: nothing picked yet.
    win._picked_format = None
    win._table.setCurrentCell(0, 0)
    can_undo_before = win._doc.can_undo
    win.paste_format()
    assert win._doc.can_undo == can_undo_before  # no checkpoint recorded


def test_paste_format_clears_style_when_source_plain(win):
    from abax.core.format.cellstyle import CellStyle

    sheet = win._doc.workbook.sheet
    # Pick from a plain cell (no style, no format).
    win._table.setCurrentCell(5, 5)
    win.copy_format()
    assert win._picked_format == (None, None)

    # Target already has a style; pasting the plain format should clear it.
    sheet.cell_styles[(6, 6)] = CellStyle(italic=True)
    sheet.cell_formats[(6, 6)] = "0%"
    win._table.setCurrentCell(6, 6)
    win._table.clearSelection()
    from abax.gui._qtcompat import QTableWidgetSelectionRange
    win._table.setRangeSelected(QTableWidgetSelectionRange(6, 6, 6, 6), True)
    win.paste_format()
    assert (6, 6) not in sheet.cell_styles
    assert (6, 6) not in sheet.cell_formats


# --- (3) in-cell signature tooltip --------------------------------------


def test_arg_hint_text_for_partial_sum():
    from abax.gui.grid.grid_view import GridDelegate

    rendered = GridDelegate.arg_hint_text("=SUM(", len("=SUM("))
    assert rendered is not None
    assert "SUM(" in rendered
    # The active (first) parameter is wrapped in the bold marker.
    assert "<b>" in rendered and "</b>" in rendered


def test_arg_hint_text_none_for_non_formula():
    from abax.gui.grid.grid_view import GridDelegate

    assert GridDelegate.arg_hint_text("hello", 5) is None
    assert GridDelegate.arg_hint_text("", 0) is None


def test_arg_hint_text_none_when_call_closed():
    from abax.gui.grid.grid_view import GridDelegate

    # Cursor past the closing paren: no active call.
    assert GridDelegate.arg_hint_text("=SUM(A1)", len("=SUM(A1)")) is None
