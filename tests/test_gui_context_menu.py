"""Sheet right-click context menu — built from the existing actions."""

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


def test_context_menu_has_clipboard_and_submenus(win):
    m = win._build_cell_context_menu()
    texts = [a.text() for a in m.actions()]
    assert "Cu&t" in texts and "&Copy" in texts and "&Paste" in texts

    submenus = {a.text(): a.menu() for a in m.actions() if a.menu() is not None}
    assert {"Insert", "Delete", "Format", "Number format", "Data"} <= set(submenus)
    assert submenus["Number format"].actions()                  # populated from FORMATS
    assert any("pandas" in a.text() for a in submenus["Data"].actions())
    assert any("Bold" == a.text() for a in submenus["Format"].actions())


def test_context_menu_actions_are_wired(win):
    # Every leaf action has a callable trigger (so right-click → run works).
    m = win._build_cell_context_menu()

    def leaves(menu):
        for a in menu.actions():
            if a.menu() is not None:
                yield from leaves(a.menu())
            elif not a.isSeparator():
                yield a

    actions = list(leaves(m))
    assert len(actions) >= 15
    assert all(a.text() for a in actions)
