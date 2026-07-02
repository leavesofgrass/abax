"""GUI smoke test: the Radio-menu 'Smith chart -> SVG' export writes a real SVG.

Runs MainWindow offscreen, monkeypatches the input/file dialogs, and confirms the
exported file starts with <svg and contains a plotted point. Skips without PyQt6.
"""

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

    _win = MainWindow(Settings())
    yield _win
    from abax.gui._qtcompat import QEvent as _QEvent
    _win.deleteLater()
    app.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    app.processEvents()


def test_export_smith_svg_writes_file(win, tmp_path, monkeypatch):
    from abax.gui import _qtcompat

    out = tmp_path / "smith.svg"
    monkeypatch.setattr(
        _qtcompat.QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("75+25j", True) if "Load" in a[2]
                     else ("50", True)))
    monkeypatch.setattr(
        _qtcompat.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(out), "SVG image (*.svg)")))

    win.export_smith_svg()

    assert out.exists()
    svg = out.read_text(encoding="utf-8")
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "<circle" in svg


def test_export_smith_svg_cancel_writes_nothing(win, tmp_path, monkeypatch):
    from abax.gui import _qtcompat

    monkeypatch.setattr(_qtcompat.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("", False)))
    saved = {"called": False}

    def _no_save(*a, **k):
        saved["called"] = True
        return ("", "")

    monkeypatch.setattr(_qtcompat.QFileDialog, "getSaveFileName",
                        staticmethod(_no_save))
    win.export_smith_svg()
    assert saved["called"] is False
