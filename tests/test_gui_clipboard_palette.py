"""Searchable clipboard history palette — actions + paste-at-cursor."""

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


def test_empty_history_has_no_actions(win):
    assert win._clipboard_actions() == {}


def test_actions_paste_entry_at_cursor(win):
    win._clipboard.add("hello\tworld")           # one TSV row -> two cells
    win._clipboard.add("solo")
    actions = win._clipboard_actions()
    assert len(actions) == 2
    assert any("hello" in label for label in actions)

    win._table.setCurrentCell(0, 0)
    paste = next(fn for label, fn in actions.items() if "hello" in label)
    paste()
    sheet = win._doc.workbook.sheet
    assert sheet.get("A1") == "hello"
    assert sheet.get("B1") == "world"
