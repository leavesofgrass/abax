"""RF reference panel: data rows, filtering, and 'bands -> sheet'."""

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

    return MainWindow(Settings())


def test_dialog_populates(win):
    from abax.core.science import rf_bands
    from abax.gui.dialogs.rf_reference_dialog import RfReferenceDialog

    dlg = RfReferenceDialog(win)
    assert dlg._band_table.rowCount() == len(rf_bands.US_AMATEUR_BANDS)
    assert dlg._tone_table.rowCount() == len(rf_bands.CTCSS_TONES)
    # 20 m band low edge is 14 MHz.
    labels = [dlg._band_table.item(r, 0).text() for r in range(dlg._band_table.rowCount())]
    assert "20m" in labels


def test_filter_hides_nonmatching(win):
    from abax.gui.dialogs.rf_reference_dialog import RfReferenceDialog

    dlg = RfReferenceDialog(win)
    dlg._filter.setText("20m")
    dlg._apply_filter("20m")
    visible = [r for r in range(dlg._band_table.rowCount())
               if not dlg._band_table.isRowHidden(r)]
    assert len(visible) == 1
    assert dlg._band_table.item(visible[0], 0).text() == "20m"


def test_bands_to_sheet(win):
    from abax.gui.dialogs.rf_reference_dialog import RfReferenceDialog

    dlg = RfReferenceDialog(win)
    before = len(win._doc.workbook.sheets)
    dlg._bands_to_sheet()
    assert len(win._doc.workbook.sheets) == before + 1
    sheet = win._doc.workbook.sheet
    assert sheet.get_value(0, 0) == "Band"
    assert sheet.get_value(1, 0) is not None


def test_double_click_sends_value_to_current_cell(win):
    from abax.gui.dialogs.rf_reference_dialog import RfReferenceDialog

    dlg = RfReferenceDialog(win)
    win._table.setCurrentCell(2, 3)                  # aim the grid at D3
    # 20 m row, "Low (MHz)" column (index 1) == "14".
    row = next(r for r in range(dlg._band_table.rowCount())
               if dlg._band_table.item(r, 0).text() == "20m")
    dlg._send_cell(dlg._band_table, row, 1)
    assert win._doc.workbook.sheet.get_value(2, 3) == 14.0


def test_send_selected_uses_active_table(win):
    from abax.gui.dialogs.rf_reference_dialog import RfReferenceDialog

    dlg = RfReferenceDialog(win)
    win._table.setCurrentCell(0, 0)
    # Select CTCSS tone #13 (100.0 Hz) in the tones table and send it.
    dlg._active_table = dlg._tone_table
    dlg._tone_table.setCurrentCell(12, 1)            # row 13 (0-based 12), Tone col
    dlg._send_selected()
    assert win._doc.workbook.sheet.get_value(0, 0) == 100.0


def test_send_fills_multi_cell_selection(win):
    from abax.gui._qtcompat import QTableWidgetSelectionRange
    from abax.gui.dialogs.rf_reference_dialog import RfReferenceDialog

    dlg = RfReferenceDialog(win)
    win._table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 0), True)
    dlg._send_value("146.52")
    sheet = win._doc.workbook.sheet
    assert sheet.get_value(0, 0) == 146.52
    assert sheet.get_value(1, 0) == 146.52


def test_dialog_is_non_modal(win):
    from abax.gui.dialogs.rf_reference_dialog import RfReferenceDialog

    assert RfReferenceDialog(win).isModal() is False


def test_palette_wiring(win):
    assert "RF reference (bands / CTCSS)..." in win._palette_actions()
