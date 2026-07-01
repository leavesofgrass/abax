"""Async file open/save via IOWorker: the UI thread never blocks on disk.

Runs MainWindow offscreen and pumps the event loop until the worker delivers its
queued result/finished signals. Skips cleanly without PyQt6.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.core.workbook import Workbook  # noqa: E402
from abax.gui._qtcompat import QApplication, QThread  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    return MainWindow(Settings())


def _wait_io(win, app, timeout_ms: int = 5000) -> None:
    waited = 0
    while getattr(win, "_io_busy", False) and waited < timeout_ms:
        app.processEvents()
        QThread.msleep(10)
        waited += 10
    app.processEvents()
    assert not win._io_busy, "I/O did not finish in time"


def test_async_open_loads_file(win, app, tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    win.open_document(str(p))
    assert win._io_busy            # truly off-thread (not done synchronously)
    assert not win._table.isEnabled()
    _wait_io(win, app)
    assert win._doc.path.name == "data.csv"
    assert win._doc.workbook.sheet.get_raw(1, 0) == "1"
    assert win._table.isEnabled()  # UI restored


def test_async_open_error_restores_ui(win, app, tmp_path, monkeypatch):
    import abax.gui.mixin_document as md

    seen = {}
    monkeypatch.setattr(md.QMessageBox, "critical",
                        lambda *a, **k: seen.__setitem__("shown", True))
    win.open_document(str(tmp_path / "bad.unknownext"))
    _wait_io(win, app)
    assert seen.get("shown")        # error surfaced via dialog
    assert win._table.isEnabled()   # UI restored even on failure


def test_async_save_roundtrips(win, app, tmp_path):
    win._commit_cell(0, 0, "=2*21")
    out = tmp_path / "out.abax"
    win.save_document(str(out))
    _wait_io(win, app)
    assert out.exists()
    assert win._doc.dirty is False
    assert win._doc.path.name == "out.abax"
    assert Workbook.load_json(out).sheet.get_value(0, 0) == 42.0


def test_async_import_csv(win, app, tmp_path, monkeypatch):
    p = tmp_path / "big.csv"
    p.write_text("x,y\n1,2\n3,4\n5,6\n", encoding="utf-8")

    class _FakeFileDialog:
        @staticmethod
        def getOpenFileName(*a, **k):
            return (str(p), "")

    # import_large_csv does `from ._qtcompat import QFileDialog` at call time,
    # so patching the module attribute redirects it. The tiny file stays under
    # the row-cap threshold, so no QInputDialog is shown.
    monkeypatch.setattr("abax.gui._qtcompat.QFileDialog", _FakeFileDialog)
    win.import_large_csv()
    assert win._io_busy
    _wait_io(win, app)
    assert win._doc.path.name == "big.csv"
    assert win._doc.workbook.sheet.get_raw(1, 0) == "1"
    assert win._table.isEnabled()


def test_progress_bar_toggles(win, app, tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("a\n1\n", encoding="utf-8")
    win.open_document(str(p))
    # isHidden() reflects the explicit show/hide state (the window isn't shown
    # in tests, so isVisible() would always be False).
    assert not win._progress.isHidden()   # shown while busy
    _wait_io(win, app)
    assert win._progress.isHidden()        # hidden when done


def test_second_io_is_rejected_while_busy(win, app, tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("x\n1\n", encoding="utf-8")
    win.open_document(str(p))
    assert win._io_busy
    # a second request while busy must be ignored, not started or crash
    win.open_document(str(p))
    _wait_io(win, app)
    assert win._doc.path.name == "a.csv"
