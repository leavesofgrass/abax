"""Copy/cut/paste driven through the grid view's keyPressEvent.

The view owns Ctrl+C/X/V directly (the menu WindowShortcut can be swallowed by a
focused editor or an ambiguous shortcut), so these keys must work via the view.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, QEvent, Qt, QTableWidgetSelectionRange  # noqa: E402
from abax.settings import Settings  # noqa: E402

try:
    from PySide6.QtGui import QKeyEvent
except ImportError:  # pragma: no cover - alternate binding
    from PyQt6.QtGui import QKeyEvent


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    return MainWindow(Settings())


def _press(widget, key, *, ctrl=False, shift=False):
    mods = Qt.KeyboardModifier.NoModifier
    if ctrl:
        mods |= Qt.KeyboardModifier.ControlModifier
    if shift:
        mods |= Qt.KeyboardModifier.ShiftModifier
    widget.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods))


def test_ctrl_c_then_ctrl_v_via_keypress(win):
    sh = win._doc.workbook.sheet
    sh.set("A1", "x")
    sh.set("B1", "y")
    win.refresh_table()

    win._table.setCurrentCell(0, 0)
    win._table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 0, 1), True)
    _press(win._table, Qt.Key.Key_C, ctrl=True)
    assert win._clip is not None and win._clip.ncols == 2

    win._table.setCurrentCell(2, 0)
    _press(win._table, Qt.Key.Key_V, ctrl=True)
    assert sh.get_raw(2, 0) == "x"
    assert sh.get_raw(2, 1) == "y"


def test_ctrl_x_cuts_via_keypress(win):
    sh = win._doc.workbook.sheet
    sh.set("A1", "gone")
    win.refresh_table()
    win._table.setCurrentCell(0, 0)
    win._table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 0, 0), True)
    _press(win._table, Qt.Key.Key_X, ctrl=True)
    assert sh.get_raw(0, 0) == ""              # source cleared
    assert win._clip is not None               # captured for paste


def test_ctrl_shift_c_is_not_treated_as_copy(win):
    # Ctrl+Shift+C must NOT trigger copy (reserved / different binding).
    win._table.setCurrentCell(0, 0)
    win._clip = None
    _press(win._table, Qt.Key.Key_C, ctrl=True, shift=True)
    assert win._clip is None
