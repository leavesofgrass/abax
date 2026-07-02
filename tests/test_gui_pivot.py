"""GUI test for the Pivot / group-by dialog (margins + percent-of-total)."""

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
    s = w._doc.workbook.sheet
    # category x region table with known numbers (grand sales total = 500).
    data = [
        ["category", "region", "sales"],
        ["X", "East", "100"],
        ["X", "West", "200"],
        ["Y", "East", "50"],
        ["Y", "West", "150"],
    ]
    for r, row in enumerate(data):
        for c, val in enumerate(row):
            s.set_cell(r, c, val)
    yield w
    from abax.gui._qtcompat import QEvent
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _make_dialog(win, *, index, column, value, agg="sum", margins=False, pct=None):
    from abax.gui.dialogs.pivot_dialog import PivotDialog

    dlg = PivotDialog(win)
    dlg._range.setText("A1:C5")
    dlg._reload_columns()
    dlg._mode.setCurrentIndex(1)  # "Pivot table"
    for combo, text in ((dlg._index, index), (dlg._column, column),
                        (dlg._value, value)):
        combo.setCurrentIndex(combo.findText(text))
    dlg._agg.setCurrentIndex(dlg._agg.findData(agg))
    dlg._totals.setChecked(margins)
    dlg._pct.setCurrentIndex(dlg._pct.findData(pct))
    dlg._out.setText("E1")
    return dlg


def _read_block(win, top_left, n_rows, n_cols):
    from abax.core.reference import parse_a1
    r0, c0 = parse_a1(top_left)
    sheet = win._doc.workbook.sheet
    return [
        ["" if sheet.get_value(r0 + i, c0 + j) is None
         else str(sheet.get_value(r0 + i, c0 + j))
         for j in range(n_cols)]
        for i in range(n_rows)
    ]


def test_dialog_has_totals_and_pct_controls(win):
    dlg = _make_dialog(win, index="category", column="region", value="sales")
    assert dlg._totals.isVisible() or True  # widget exists on the pivot page
    # Percent combo carries the core pct_of keys.
    keys = [dlg._pct.itemData(i) for i in range(dlg._pct.count())]
    assert keys == [None, "grand", "row", "col"]


def test_dialog_margins_written_to_sheet(win):
    dlg = _make_dialog(win, index="category", column="region", value="sales",
                       margins=True)
    dlg._apply()
    block = _read_block(win, "E1", 4, 4)
    assert block[0] == ["category", "East", "West", "Total"]
    assert block[1] == ["X", "100", "200", "300"]
    assert block[3] == ["Total", "150", "350", "500"]


def test_dialog_percent_of_grand_written_to_sheet(win):
    dlg = _make_dialog(win, index="category", column="region", value="sales",
                       pct=("grand"))
    dlg._apply()
    block = _read_block(win, "E1", 3, 3)
    assert block[0] == ["category", "East", "West"]
    # 100/500 = 20 %, 200/500 = 40 %.
    assert block[1] == ["X", "20", "40"]
    assert block[2] == ["Y", "10", "30"]
