"""Wave-3 GUI wiring: Import from URL and Solve NEC deck (PyNEC)."""

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


def test_import_from_url_loads(win, tmp_path, monkeypatch):
    # A tiny CSV that urlfetch would have downloaded.
    src = tmp_path / "remote.csv"
    src.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

    from abax.core.io import urlfetch
    from abax.gui import _qtcompat

    monkeypatch.setattr(urlfetch, "fetch_url", lambda url, **kw: src)
    monkeypatch.setattr(_qtcompat.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("http://example/remote.csv", True)))
    # Run the worker's callable synchronously so the test stays deterministic.
    monkeypatch.setattr(win, "_run_io",
                        lambda worker, on_success, busy_msg: on_success(worker._fn()))

    win.import_from_url(None)
    sheet = win._doc.workbook.sheet
    assert sheet.get_value(1, 0) == 1.0      # row 2, col A
    assert sheet.get_value(2, 1) == 4.0      # row 3, col B


def test_import_from_url_cancel(win, monkeypatch):
    from abax.gui import _qtcompat

    monkeypatch.setattr(_qtcompat.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("", False)))
    called = []
    monkeypatch.setattr(win, "_run_io",
                        lambda *a, **k: called.append(1))
    win.import_from_url(None)
    assert not called          # cancelled dialog -> no fetch


def test_solve_nec_pynec_absent(win, monkeypatch):
    from abax.engine import necpy
    from abax.gui import _qtcompat

    monkeypatch.setattr(necpy, "available", lambda: False)
    shown = []
    monkeypatch.setattr(_qtcompat.QMessageBox, "information",
                        staticmethod(lambda *a, **k: shown.append(a)))
    # If a file dialog were reached it would block; assert it is not.
    monkeypatch.setattr(_qtcompat.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: pytest.fail("should not prompt")))
    win.solve_nec_pynec()
    assert shown and "PyNEC" in shown[0][1]


def test_url_and_nec_palette_wiring(win):
    actions = win._palette_actions()
    assert "Import from URL..." in actions
    assert "Solve NEC deck (PyNEC)..." in actions


def test_console_ns_has_urlfetch():
    from abax.core.console_ns import build_namespace
    from abax.core.workbook import Workbook

    ns = build_namespace(Workbook())
    assert "urlfetch" in ns
    assert hasattr(ns["urlfetch"], "fetch_url")
