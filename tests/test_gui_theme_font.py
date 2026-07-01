"""Default UI font family: the chrome gets a known-good sans-serif stack when the
dyslexia font is off, so menus/lists don't fall back to a poorly-hinted font; the
layer steps aside (and the monospace console is untouched) when OpenDyslexic is on.
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

    return MainWindow(Settings())


def test_chrome_font_family_applied_when_dyslexic_off(win, app):
    qss = app.styleSheet()
    assert "QMenu" in qss and "sans-serif" in qss
    # the monospace console/terminal must NOT be forced to the sans stack
    assert "QPlainTextEdit { font-family" not in qss


def test_base_font_dropped_when_dyslexic_on(win, app):
    win._ui_font_family = "OpenDyslexic"
    win.apply_current_theme()
    qss = app.styleSheet()
    assert "Segoe UI" not in qss              # base sans layer suppressed
    assert "OpenDyslexic" in qss              # dyslexia font drives the text widgets
    # restore so the shared app stylesheet doesn't leak into other tests
    win._ui_font_family = ""
    win.apply_current_theme()
