"""The calculator view (open state + Deg/Rad) persists across sessions."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("qcell.gui._qtcompat")

from qcell.gui._qtcompat import QApplication  # noqa: E402
from qcell.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _win(settings):
    from qcell.gui.main_window import MainWindow

    return MainWindow(settings)


def test_calculator_is_not_auto_opened(app):
    # A fresh window opens to a clean grid — the calculator is on-demand only.
    win = _win(Settings())
    assert getattr(win, "_calc_window", None) is None
    win.show_calculator()                          # opens when asked
    assert win._calc_panel() is not None


def test_calc_degrees_persists(app):
    win = _win(Settings())
    win.show_calculator()
    panel = win._calc_panel()
    panel._kind = "alg"
    panel._rebuild()
    face = panel._widget
    start = face._calc.degrees
    face._do("@deg")
    assert face._calc.degrees != start
    assert win._settings.calc_degrees == face._calc.degrees

    win._settings.calc_degrees = True              # a rebuilt faceplate restores it
    panel._rebuild()
    assert panel._widget._calc.degrees is True
