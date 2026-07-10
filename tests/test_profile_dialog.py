"""GUI wiring for the formula profiler dialog (:mod:`abax.gui.dialogs.profile_dialog`).

The measurement + SVG live in :mod:`abax.core.profile` (tested headlessly in
``test_profile.py``); here we only prove the dialog runs a profile into its
report pane and renders a dependency graph without raising.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PySide6")
    from abax.gui._qtcompat import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui._qtcompat import QEvent
    from abax.gui.main_window import MainWindow
    from abax.settings import Settings

    _win = MainWindow(Settings())
    sh = _win._doc.workbook.sheet
    sh.set_cell(0, 0, "1")
    sh.set_cell(1, 0, "=A1+1")
    sh.set_cell(2, 0, "=A2*3")
    yield _win
    _win.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_profiler_runs_and_reports_slowest(win) -> None:
    from abax.gui.dialogs.profile_dialog import ProfileDialog

    dlg = ProfileDialog(win)
    dlg._run()
    text = dlg._report.toPlainText()
    # Header + both formula cells appear; the input constant A1 is not a formula.
    assert "Time (ms)" in text
    assert "A2" in text and "A3" in text


def test_profiler_draws_dependency_graph(win) -> None:
    from abax.gui.dialogs.profile_dialog import ProfileDialog

    dlg = ProfileDialog(win)
    win._table.setCurrentCell(2, 0)  # A3 = A2*3
    dlg._draw_graph()  # must not raise; loads SVG into the widget when present
    # Switch direction and redraw to exercise the other branch too.
    dlg._direction.setCurrentIndex(1)
    dlg._draw_graph()


def test_menu_handlers_exist(win) -> None:
    # The Analyze menu wires these; assert the callables the actions bind to.
    assert callable(win.show_formula_profiler)
    assert callable(win.show_what_if)
