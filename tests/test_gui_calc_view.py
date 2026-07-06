"""The calculator view (open state + Deg/Rad) persists across sessions."""

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


def test_image_fallback_never_duplicates_faceplate(app, monkeypatch):
    # Frozen/assetless machines: style "image" with no faceplate art falls back
    # to vector. The fallback used to fire currentIndexChanged -> _on_style ->
    # _rebuild RE-ENTRANTLY mid-_make_widget, stacking a second (orphaned)
    # vector faceplate in the layout — two calculators on screen.
    from abax.gui.calc import image_faceplate
    from abax.gui.calc.calculator_panel import CalculatorPanel
    from abax.settings import Settings

    monkeypatch.setattr(image_faceplate, "find_assets_dir", lambda *_a: None)

    class _Host:  # minimal window stand-in (interop buttons need these slots)
        _settings = Settings()

        def cell_to_calc(self):
            pass

        def calc_to_cells(self):
            pass

    _Host._settings.calc_style = "image"
    panel = CalculatorPanel(_Host())

    def faceplates():
        n = 0
        for i in range(panel._body.count()):
            w = panel._body.itemAt(i).widget()
            if w is not None and w is not panel._prog_panel:
                n += 1
        return n

    assert faceplates() == 1
    # Switch models a few times with the fallback active — still exactly one.
    for ix in range(panel._model_box.count()):
        panel._model_box.setCurrentIndex(ix)
        assert faceplates() == 1, f"duplicate faceplate after switching to index {ix}"
    panel.deleteLater()


def test_style_toggle_to_image_without_assets_stays_single(app, monkeypatch):
    # The user's exact gesture on an assetless machine: style Vector -> Image.
    # The image fallback must snap the choice back to Vector with exactly ONE
    # faceplate rendered (no re-entrant duplicate) and report why via the
    # window's status line.
    from abax.gui.calc import image_faceplate
    from abax.gui.calc.calculator_panel import CalculatorPanel
    from abax.settings import Settings

    monkeypatch.setattr(image_faceplate, "find_assets_dir", lambda *_a: None)
    status = {}

    class _Host:
        _settings = Settings()

        def cell_to_calc(self):
            pass

        def calc_to_cells(self):
            pass

        def _set_status(self, msg):
            status["msg"] = msg

    _Host._settings.calc_style = "vector"
    panel = CalculatorPanel(_Host())

    def faceplates():
        return sum(1 for i in range(panel._body.count())
                   if panel._body.itemAt(i).widget() is not None
                   and panel._body.itemAt(i).widget() is not panel._prog_panel)

    assert faceplates() == 1
    panel._style_box.setCurrentIndex(0)          # Vector -> Image (no assets)
    assert faceplates() == 1                      # never a duplicate
    assert panel._style == "vector"               # choice snapped back
    assert panel._style_box.currentData() == "vector"   # UI agrees
    assert "faceplate" in status.get("msg", "")   # and the user was told why
    panel.deleteLater()
