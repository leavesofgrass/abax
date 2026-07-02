"""GUI Descriptive Statistics tool: compute from a range, write summary sheet."""

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
    for r, v in enumerate([2, 4, 4, 4, 5, 5, 7, 9]):
        s.set_cell(r, 0, str(v))
    yield w
    from abax.gui._qtcompat import QEvent
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_describe_dialog_computes_from_range(win):
    from abax.gui.dialogs.describe_dialog import DescribeDialog

    dlg = DescribeDialog(win)
    dlg._in.setText("A1:A8")
    dlg._compute()
    assert dlg._summary is not None
    assert dlg._summary["count"] == 8
    assert dlg._summary["mean"] == pytest.approx(5.0)
    assert dlg._summary["stdev_pop"] == pytest.approx(2.0)


def test_describe_dialog_writes_summary_sheet(win):
    from abax.gui.dialogs.describe_dialog import DescribeDialog

    dlg = DescribeDialog(win)
    dlg._in.setText("A1:A8")
    dlg._compute()

    before = len(win._doc.workbook.sheets)
    dlg._write_sheet()
    assert len(win._doc.workbook.sheets) == before + 1
    out = win._doc.workbook.sheet   # new summary sheet is now active
    assert out.get_value(0, 0) == "Statistic"
    assert out.get_value(0, 1) == "Value"
    # Row 1 is "Count" -> 8 (fields are in descriptive.FIELDS order).
    assert out.get_value(1, 0) == "Count"
    assert str(out.get_value(1, 1)) == "8"


def test_describe_dialog_handles_empty_range(win):
    from abax.gui.dialogs.describe_dialog import DescribeDialog

    dlg = DescribeDialog(win)
    dlg._in.setText("Z1:Z5")   # all blank
    dlg._compute()
    assert dlg._summary["count"] == 0
    assert dlg._to_sheet.isEnabled() is False
