"""Ensure the project root is importable when running tests uninstalled, and
dispose any leaked Qt windows between tests so the GUI suite stays safe in a
long-lived process."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _dispose_leaked_qt_windows():
    """Delete any top-level Qt widget still alive at the end of a test.

    The GUI tests build a ``MainWindow`` per test; the fixtures now dispose their
    own window, but a few tests create one via a plain helper (a local variable,
    dropped when the test returns) and would otherwise pile up. Left alone, dozens
    of live windows make a later test that restyles the whole widget tree (the
    zoom test's repeated global ``setStyleSheet``) crawl or crash Qt.

    Being autouse, this tears down *after* the per-test fixtures, so a fixture has
    already deleted its own window before we look — we only ever collect the
    genuine strays, never a window another fixture still owns.

    Disposal is two passes, real windows first. ``topLevelWidgets()`` also lists
    popup *windows* that belong to objects inside a real window: every QMenu,
    and — the dangerous one — the formula bar's QCompleter popup, a parentless
    QListView the completer owns through a raw pointer and deletes in its own
    destructor. Posting a DeferredDelete for that popup too is a double free
    whenever it is dispatched before the window's (the list's order is
    arbitrary): the popup is freed, then the dying window's ~QCompleter deletes
    it again — heap corruption that aborts the whole pytest process (observed
    on Windows + PySide6 6.11 as ``Fatal Python error: Aborted``, exit
    0xC0000409). So pass 1 deletes only genuine windows/dialogs — their popups
    die with their owners — and pass 2 sweeps whatever parentless stray is
    still alive afterwards (e.g. the shared tooltip label). Windows are *not*
    ``close()``d first: closeEvent persists settings via ``rt.CONFIG_DIR``, and
    this fixture tears down after the tests/conftest dir-redirect is undone.

    A cheap no-op for the ~700 non-GUI tests: it acts only when the Qt binding has
    actually been imported in this worker (a plain ``sys.modules`` lookup — no Qt
    import is forced)."""
    yield
    qt = sys.modules.get("abax.gui._qtcompat")
    if qt is None:
        return
    app = qt.QApplication.instance()
    if app is None:
        return
    real_windows = (qt.Qt.WindowType.Window, qt.Qt.WindowType.Dialog)
    for widget in list(app.topLevelWidgets()):
        if widget.windowType() in real_windows:
            widget.deleteLater()
    app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
    app.processEvents()
    for widget in list(app.topLevelWidgets()):
        widget.deleteLater()
    app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
    app.processEvents()
