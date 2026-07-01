"""Status-bar state cluster — vim mode · theme · saved/unsaved."""

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


def test_cluster_reflects_vim_and_theme(win):
    win._update_status_cluster()
    assert win._sb_vim.text() == ("VIM" if win._settings.vim_mode else "INS")
    assert win._sb_theme.text() == win._settings.theme
    before = win._sb_vim.text()
    win.toggle_vim_mode()
    assert win._sb_vim.text() != before


def test_cluster_dirty_marker(win):
    assert "saved" in win._sb_dirty.text()        # fresh doc is clean
    win._commit_cell(0, 0, "x")                   # mutate -> dirty
    win.refresh_table()
    assert "unsaved" in win._sb_dirty.text()
