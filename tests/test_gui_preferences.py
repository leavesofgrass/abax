"""Preferences dialog: loads current settings, Apply/OK persist, Cancel discards.

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


def test_loads_current_settings(win):
    # Seed some non-default values, then confirm the widgets reflect them.
    win._settings.theme = "nord"
    win._settings.zoom = 1.3
    win._settings.autosave_enabled = False
    win._settings.autosave_interval = 45
    win._settings.code_isolation = "strict"
    win._settings.dyslexic_font = False

    dlg = _dialog(win)
    assert dlg._theme.currentData() == "nord"
    assert abs(dlg._zoom.value() - 1.3) < 1e-9
    assert dlg._autosave_on.isChecked() is False
    assert dlg._autosave_interval.value() == 45
    # Interval greyed out while autosave is off.
    assert dlg._autosave_interval.isEnabled() is False
    assert dlg._isolation.currentData() == "strict"
    assert dlg._dyslexic.isChecked() is False
    dlg.deleteLater()


def test_ok_persists_changes(win, cfg):
    win._settings.theme = "galaxy"
    win._settings.code_isolation = "isolated"
    win._settings.autosave_interval = 30

    dlg = _dialog(win)
    # Change several values.
    dlg._select(dlg._theme, "solarized")
    dlg._select(dlg._isolation, "off")
    dlg._autosave_on.setChecked(True)
    dlg._autosave_interval.setValue(120)
    dlg._zoom.setValue(1.5)
    dlg._on_ok()  # Apply + accept

    # In-memory settings updated...
    s = win._settings
    assert s.theme == "solarized"
    assert s.code_isolation == "off"
    assert s.autosave_interval == 120
    assert abs(s.zoom - 1.5) < 1e-9
    # ...and the isolation change flowed through set_code_isolation (menu synced).
    assert win._isolation_actions["off"].isChecked()

    # ...and written to settings.json in the temp config dir.
    written = load_settings(cfg / "settings.json")
    assert written.theme == "solarized"
    assert written.code_isolation == "off"
    assert written.autosave_interval == 120
    assert abs(written.zoom - 1.5) < 1e-9


def test_cancel_discards_changes(win, cfg):
    win._settings.theme = "nord"
    win._settings.code_isolation = "isolated"
    win.apply_current_theme()

    dlg = _dialog(win)
    dlg._select(dlg._theme, "light")
    dlg._select(dlg._isolation, "strict")
    dlg._autosave_interval.setValue(99)
    dlg._on_cancel()  # revert + reject

    # Nothing changed in memory.
    assert win._settings.theme == "nord"
    assert win._settings.code_isolation == "isolated"
    assert win._settings.autosave_interval != 99
    # No settings.json was written by Cancel.
    assert not (cfg / "settings.json").exists()


def test_menu_has_preferences(win):
    # The Preferences item lives under Edit and opens the dialog method.
    for a in win.menuBar().actions():
        if a.text().replace("&", "") == "Edit":
            labels = [x.text().replace("&", "") for x in a.menu().actions() if x.text()]
            assert "Preferences..." in labels
            break
    else:
        pytest.fail("Edit menu not found")
    # Reachable from the command palette too.
    assert "Preferences..." in win._palette_actions()
