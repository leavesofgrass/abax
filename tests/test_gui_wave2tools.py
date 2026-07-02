"""Wave-2 GUI tools: Goal Seek, workbook compare, HTML export, I/Q export."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.core.sheet import Sheet  # noqa: E402
from abax.core.workbook import Workbook  # noqa: E402
from abax.engine.document import Document  # noqa: E402
from abax.gui._qtcompat import QApplication, QFileDialog  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    _win = MainWindow(Settings())
    yield _win
    # Dispose the window so it doesn't accumulate across a long test process
    # (many live MainWindows segfault Qt when a later test restyles them).
    from abax.gui._qtcompat import QEvent as _QEvent
    _win.deleteLater()
    app.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    app.processEvents()


def _wb(sheet):
    return Workbook.from_sheets([sheet]) if hasattr(Workbook, "from_sheets") else Workbook()


def test_goal_seek_solves(win):
    from abax.gui.dialogs.goalseek_dialog import GoalSeekDialog

    s = win._doc.workbook.sheet
    s.set_cell(0, 1, "2")            # B1
    s.set_cell(0, 0, "=B1*3")        # A1
    dlg = GoalSeekDialog(win)
    dlg._target.setText("A1")
    dlg._value.setText("30")
    dlg._changing.setText("B1")
    dlg.solve()
    assert abs(float(s.get_value(0, 1)) - 10) < 1e-4      # B1 -> 10
    assert abs(float(s.get_value(0, 0)) - 30) < 1e-4      # A1 -> 30


def test_compare_workbook(win, tmp_path, monkeypatch):
    win._doc.workbook.sheet.set_cell(0, 0, "hello")
    other = tmp_path / "other.abax"
    s2 = Sheet("Sheet1")
    s2.set_cell(0, 0, "world")
    Document(_wb(s2), other).save()
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(other), "")))
    before = len(win._doc.workbook.sheets)
    win.compare_workbook()
    assert len(win._doc.workbook.sheets) == before + 1    # a Diff sheet appears
    assert "changed" in win._doc.workbook.sheet.get_value(0, 0)


def test_html_export(win, tmp_path, monkeypatch):
    out = tmp_path / "report.html"
    win._doc.workbook.sheet.set_cell(0, 0, "hi")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    win.export_html_report()
    assert out.read_text(encoding="utf-8").lstrip().startswith("<!DOCTYPE")


def test_iq_export(win, tmp_path, monkeypatch):
    from abax.gui._qtcompat import QTableWidgetSelectionRange

    s = win._doc.workbook.sheet
    for r, (i, q) in enumerate([(1, 0), (0, 1), (-1, 0), (0, -1)]):
        s.set_cell(r, 0, str(i))
        s.set_cell(r, 1, str(q))
    out = tmp_path / "c.svg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    win._table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 3, 1), True)
    win.export_iq_svg()
    assert out.read_text(encoding="utf-8").startswith("<svg")


def test_wave2_palette_wiring(win):
    actions = win._palette_actions()
    for label in ("Goal seek...", "Compare workbook...",
                  "Export as HTML report...", "I/Q constellation -> SVG"):
        assert label in actions


def test_curve_fit_linear_writes_fitted_column(win):
    from abax.gui.dialogs.curvefit_dialog import CurveFitDialog

    s = win._doc.workbook.sheet
    # y = 2x + 1 in columns A (x) and B (y).
    for r, x in enumerate([0, 1, 2, 3]):
        s.set_cell(r, 0, str(x))
        s.set_cell(r, 1, str(2 * x + 1))
    dlg = CurveFitDialog(win)
    dlg._x.setText("A1:A4")
    dlg._y.setText("B1:B4")
    dlg._model.setCurrentIndex(0)          # Linear
    dlg._write.setChecked(True)
    dlg._out.setText("C1")
    dlg._apply()
    # R² reported as a perfect fit.
    assert "R" in dlg._readout.text()
    # Fitted column reproduces y = 2x + 1.
    for r, x in enumerate([0, 1, 2, 3]):
        assert abs(float(s.get_value(r, 2)) - (2 * x + 1)) < 1e-6


def test_curve_fit_palette_wiring(win):
    assert "Curve fit..." in win._palette_actions()
