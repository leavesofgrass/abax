"""Preferences dialog — the Accessibility tab reads/writes the W1 a11y settings.

Covers the three Wave-1 accessibility flags exposed on the new tab:
``high_contrast``, ``speak_on_move``, ``tui_screen_reader``. Loading reflects the
current settings; OK persists changes to ``settings.json``; Cancel discards them.

Driven offscreen (QT_QPA_PLATFORM=offscreen) like the other GUI tests.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication  # noqa: E402
from abax.settings import Settings, load_settings  # noqa: E402


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


@pytest.fixture()
def cfg(abax_user_dirs):
    """The temp dir settings.json persists into (redirected suite-wide by the
    autouse ``abax_user_dirs`` fixture in conftest) — read it back from here."""
    return abax_user_dirs["CONFIG_DIR"]


def _dialog(win):
    from abax.gui.dialogs.preferences_dialog import PreferencesDialog

    return PreferencesDialog(win)


def test_has_accessibility_tab(win):
    from abax.gui._qtcompat import QTabWidget

    dlg = _dialog(win)
    tabs = dlg.findChild(QTabWidget)
    labels = [tabs.tabText(i) for i in range(tabs.count())]
    assert "Accessibility" in labels
    dlg.deleteLater()


def test_loads_accessibility_settings(win):
    win._settings.high_contrast = True
    win._settings.speak_on_move = True
    win._settings.tui_screen_reader = False

    dlg = _dialog(win)
    assert dlg._high_contrast.isChecked() is True
    assert dlg._speak_on_move.isChecked() is True
    assert dlg._tui_screen_reader.isChecked() is False
    dlg.deleteLater()


def test_ok_persists_accessibility_settings(win, cfg):
    win._settings.high_contrast = False
    win._settings.speak_on_move = False
    win._settings.tui_screen_reader = False

    dlg = _dialog(win)
    dlg._high_contrast.setChecked(True)
    dlg._speak_on_move.setChecked(True)
    dlg._tui_screen_reader.setChecked(True)
    dlg._on_ok()

    # In-memory settings updated...
    s = win._settings
    assert s.high_contrast is True
    assert s.speak_on_move is True
    assert s.tui_screen_reader is True

    # ...and written to settings.json in the temp config dir.
    written = load_settings(cfg / "settings.json")
    assert written.high_contrast is True
    assert written.speak_on_move is True
    assert written.tui_screen_reader is True


def test_ok_can_disable_accessibility_settings(win, cfg):
    win._settings.high_contrast = True
    win._settings.speak_on_move = True
    win._settings.tui_screen_reader = True

    dlg = _dialog(win)
    dlg._high_contrast.setChecked(False)
    dlg._speak_on_move.setChecked(False)
    dlg._tui_screen_reader.setChecked(False)
    dlg._on_ok()

    written = load_settings(cfg / "settings.json")
    assert written.high_contrast is False
    assert written.speak_on_move is False
    assert written.tui_screen_reader is False


def test_cancel_discards_accessibility_changes(win, cfg):
    win._settings.high_contrast = False
    win._settings.speak_on_move = False
    win._settings.tui_screen_reader = False

    dlg = _dialog(win)
    dlg._high_contrast.setChecked(True)
    dlg._speak_on_move.setChecked(True)
    dlg._tui_screen_reader.setChecked(True)
    dlg._on_cancel()

    # Nothing changed in memory, and no file was written.
    assert win._settings.high_contrast is False
    assert win._settings.speak_on_move is False
    assert win._settings.tui_screen_reader is False
    assert not (cfg / "settings.json").exists()
