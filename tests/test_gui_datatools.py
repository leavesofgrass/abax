"""GUI data-science tools: SQL query dialog, column profiler, chart export."""

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
    for c, h in enumerate(["name", "age"]):
        s.set_cell(0, c, h)
    for r, (n, a) in enumerate([("al", "30"), ("bo", "40"), ("cy", "20")], start=1):
        s.set_cell(r, 0, n)
        s.set_cell(r, 1, a)
    return w


def test_sql_dialog_runs_and_writes_sheet(win):
    from abax.gui.dialogs.sql_dialog import SqlDialog

    dlg = SqlDialog(win)
    dlg._sql.setPlainText("SELECT name FROM Sheet1 WHERE age > 25 ORDER BY age")
    dlg.run_query()
    assert dlg._columns == ["name"]
    assert [row[0] for row in dlg._rows] == ["al", "bo"]
    assert dlg._table.rowCount() == 2

    before = len(win._doc.workbook.sheets)
    dlg._results_to_sheet()
    assert len(win._doc.workbook.sheets) == before + 1
    assert win._doc.workbook.sheet.get_value(1, 0) == "al"   # result sheet active


def test_sql_dialog_reports_bad_sql(win, monkeypatch):
    from abax.gui.dialogs import sql_dialog

    warned = []
    monkeypatch.setattr(sql_dialog.QMessageBox, "warning",
                        lambda *a, **k: warned.append(a))
    dlg = sql_dialog.SqlDialog(win)
    dlg._sql.setPlainText("SELECT * FROM NoSuchTable")
    dlg.run_query()
    assert warned                                            # SqlError surfaced


def test_profile_columns_writes_report(win):
    before = len(win._doc.workbook.sheets)
    win.profile_columns()
    assert len(win._doc.workbook.sheets) == before + 1
    rep = win._doc.workbook.sheet
    assert rep.get_value(0, 0) == "column"
    # the 'age' column should profile as an int with mean 30
    ages = next(r for r in range(1, 4) if rep.get_value(r, 0) == "age")
    assert rep.get_value(ages, 1) == "int"


def test_export_chart_gathers_numeric(win, tmp_path, monkeypatch):
    from abax.gui import mixin_tools

    saved = tmp_path / "chart.svg"
    monkeypatch.setattr(mixin_tools, "QFileDialog", None, raising=False)
    from abax.gui._qtcompat import QFileDialog
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(saved), "")))
    # select the age column (col 1, rows 1..3)
    win._table.setCurrentCell(1, 1)
    win._table.setRangeSelected(
        __import__("abax.gui._qtcompat", fromlist=["QTableWidgetSelectionRange"])
        .QTableWidgetSelectionRange(1, 1, 3, 1), True)
    win.export_chart_svg()
    assert saved.exists() and saved.read_text().startswith("<svg")


def test_wired_into_palette(win):
    actions = win._palette_actions()
    assert "SQL query..." in actions
    assert "Profile columns" in actions
    assert "Export chart as SVG..." in actions
