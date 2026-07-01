"""Window state (geometry / active sheet / cursor cell) persists across sessions."""

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


def _win(settings):
    from abax.gui.main_window import MainWindow

    return MainWindow(settings)


def test_save_captures_geometry_and_cell(app):
    win = _win(Settings())
    win._table.setCurrentCell(4, 1)               # B5
    win._save_window_state()
    assert win._settings.last_cell == "B5"
    assert set(win._settings.window_geometry) >= {"x", "y", "w", "h"}


def test_restore_moves_cursor(app):
    s = Settings()
    s.last_cell = "C4"
    s.window_geometry = {"x": 20, "y": 20, "w": 720, "h": 480}
    win = _win(s)
    assert (win._table.currentRow(), win._table.currentColumn()) == (3, 2)


def test_restore_tolerates_garbage(app):
    s = Settings()
    s.last_cell = "not-a-ref"
    s.window_geometry = {"oops": 1}
    win = _win(s)                                  # must not raise
    assert win is not None
