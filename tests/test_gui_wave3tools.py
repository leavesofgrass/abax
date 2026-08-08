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

    _win = MainWindow(Settings())
    yield _win
    # Dispose the window so it doesn't accumulate across a long test process
    # (many live MainWindows segfault Qt when a later test restyles them).
    from abax.gui._qtcompat import QEvent as _QEvent
    _win.deleteLater()
    app.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    app.processEvents()


def test_import_from_url_loads(win, tmp_path, monkeypatch):
    # A tiny CSV that urlfetch would have downloaded. Handed back as a throwaway
    # copy, not as `src` itself: the code under test wraps the fetch in
    # ``urlfetch.fetched``, which deletes the path it is given, and a stub that
    # returns a fixture the test still owns would have it removed underneath.
    src = tmp_path / "remote.csv"
    src.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

    from abax.core.io import urlfetch
    from abax.gui import _qtcompat

    def _fake_fetch(url, **kw):
        copy = tmp_path / "downloaded.csv"
        copy.write_bytes(src.read_bytes())
        return copy

    monkeypatch.setattr(urlfetch, "fetch_url", _fake_fetch)
    monkeypatch.setattr(_qtcompat.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("http://example/remote.csv", True)))
    # Run the worker's callable synchronously so the test stays deterministic.
    monkeypatch.setattr(win, "_run_io",
                        lambda worker, on_success, busy_msg: on_success(worker._fn()))

    win.import_from_url(None)
    sheet = win._doc.workbook.sheet
    assert sheet.get_value(1, 0) == 1.0      # row 2, col A
    assert sheet.get_value(2, 1) == 4.0      # row 3, col B


def test_import_from_url_leaves_no_downloaded_file(win, tmp_path, monkeypatch):
    """The GUI import must not leave the remote data sitting in temp (issue #2).

    Driven through the REAL ``fetch_url`` with only ``urlopen`` faked, so this
    exercises the same download-then-clean path a user gets. Stubbing
    ``fetch_url`` instead would pin nothing: the leak lived in the caller, and a
    stub that hands back a file the test made is deleted just as happily by a
    correct implementation as by a broken one.

    Without this, reverting ``import_from_url`` to the leaking
    ``fetch_url``/``Document.open`` pair passes the whole suite — verified by
    mutation, which is what put this test here.
    """
    import io as _io

    from abax.core.io import urlfetch
    from abax.gui import _qtcompat

    class _Resp:                       # what urlopen returns, minus the network
        headers = {"Content-Type": "text/csv"}

        def __init__(self):
            self._buf = _io.BytesIO(b"a,b\n1,2\n3,4\n")

        def read(self, n=-1):
            return self._buf.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(urlfetch.urllib.request, "urlopen",
                        lambda request, timeout=None: _Resp())
    # fetch_url takes no dest_dir from the GUI, so redirect bare tempfile —
    # this is the "system temp directory" the leak accumulated in.
    monkeypatch.setattr(urlfetch.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(_qtcompat.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("http://example.test/remote.csv", True)))
    monkeypatch.setattr(win, "_run_io",
                        lambda worker, on_success, busy_msg: on_success(worker._fn()))

    win.import_from_url(None)

    # The workbook is usable...
    assert win._doc.workbook.sheet.get_value(1, 0) == 1.0
    # ...and nothing of the download survives.
    assert list(tmp_path.iterdir()) == [], (
        f"the URL import left files behind: {[p.name for p in tmp_path.iterdir()]}")


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
