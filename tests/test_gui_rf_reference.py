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


def test_palette_wiring(win):
    assert "RF reference (bands / CTCSS)..." in win._palette_actions()
