"""Integration: the GUI Python console runs off-thread, out-of-process, and
applies edits back (async) — and can be interrupted."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("qcell.gui._qtcompat")

from qcell.gui._qtcompat import QApplication, QThread  # noqa: E402
from qcell.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from qcell.gui.main_window import MainWindow

    return MainWindow(Settings(code_consent=True))     # past the consent gate


def _wait(console, app, timeout_ms: int = 10000) -> None:
    waited = 0
    while console._thread is not None and waited < timeout_ms:
        app.processEvents()
        QThread.msleep(10)
        waited += 10
    app.processEvents()
    assert console._thread is None, "console command did not finish in time"


def test_console_runs_async_and_applies(win, app):
    win.show_pyconsole()
    console = win._pyconsole_dock.widget()
    console._in.setText("put('A1', '5')")
    console._run()
    assert console._thread is not None        # truly off the UI thread
    assert not console._in.isEnabled()         # input disabled while running
    _wait(console, app)
    assert win._doc.workbook.sheet.get("A1") == 5
    assert console._in.isEnabled()             # UI restored after completion
    console._shutdown()
