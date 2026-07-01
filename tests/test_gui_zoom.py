"""UI zoom — View-menu actions scale the base font via a QSS layer."""

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


def test_zoom_in_out_reset(win):
    assert win._zoom_qss() == ""                       # 1.0 -> no override
    win.zoom_in()
    assert win._settings.zoom == 1.1
    assert "font-size" in win._zoom_qss()
    win.zoom_out()
    win.zoom_out()
    assert round(win._settings.zoom, 1) == 0.9
    win.reset_zoom()
    assert win._settings.zoom == 1.0 and win._zoom_qss() == ""


def test_zoom_clamps(win):
    for _ in range(40):
        win.zoom_in()
    assert win._settings.zoom == 3.0
    for _ in range(60):
        win.zoom_out()
    assert win._settings.zoom == 0.5
