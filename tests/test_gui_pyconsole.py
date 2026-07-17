"""Integration: the GUI Python console runs off-thread, out-of-process, and
applies edits back (async) — and can be interrupted."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, QThread  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui._qtcompat import QEvent
    from abax.gui.main_window import MainWindow

    _win = MainWindow(Settings(code_consent=True))     # past the consent gate
    yield _win
    _win.close()   # stop the console worker/subprocess before disposal
    _win.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


# Generous ceiling: this only bounds a hang — the loop exits the moment the
# worker thread finishes — but the command spawns a fresh Python subprocess
# and imports abax there, so under heavy CPU contention (parallel agent runs,
# concurrent CI jobs) the round-trip has been *measured* at 68 s on a machine
# running several full suites at once. 10 s flaked; give it real headroom.
def _wait(console, app, timeout_ms: int = 120000) -> None:
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


def test_console_tab_completion(win):
    win.show_pyconsole()
    console = win._pyconsole_dock.widget()
    inp = console._in
    inp.setText("compile_e")                   # unique -> inserted whole
    inp.setCursorPosition(9)
    inp._tab_complete()
    assert inp.text() == "compile_expr"
    inp.setText("she")                          # sheet / sheet_to_df -> common prefix
    inp.setCursorPosition(3)
    inp._tab_complete()
    assert inp.text().startswith("sheet")
    console._shutdown()
