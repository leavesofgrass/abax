"""Completion polish — TUI Tab-cycling, ':' command completion, GUI Tab-accept."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from abax.engine.document import Document  # noqa: E402
from abax.tui import TuiEditor  # noqa: E402


def _editor() -> TuiEditor:
    return TuiEditor(Document())


# --- TUI: successive Tabs cycle the candidates -------------------------------


def test_tab_extends_prefix_then_cycles():
    ed = _editor()
    ed.begin_insert()
    ed.edit_buf = "=SUMI"
    ed.refresh_completions()
    ed.complete()                       # SUMIF/SUMIFS share prefix SUMIF
    assert ed.edit_buf == "=SUMIF"
    ed.complete()                       # prefix exhausted -> first candidate
    assert ed.edit_buf == "=SUMIF("
    ed.complete()                       # next candidate
    assert ed.edit_buf == "=SUMIFS("
    ed.complete()                       # wraps around
    assert ed.edit_buf == "=SUMIF("


def test_typing_resets_the_cycle():
    ed = _editor()
    ed.begin_insert()
    ed.edit_buf = "=SUMIF"
    ed.refresh_completions()
    ed.complete()                       # begins cycling
    assert ed._tab_cycle is not None
    ed.edit_buf += "1"                  # user types — handlers refresh
    ed.refresh_completions()
    assert ed._tab_cycle is None


def test_single_candidate_inserts_directly():
    ed = _editor()
    ed.begin_insert()
    ed.edit_buf = "=XLOOKU"
    ed.complete()
    assert ed.edit_buf == "=XLOOKUP("
    assert ed._tab_cycle is None


# --- TUI: ':' command completion ---------------------------------------------


def test_command_single_match_completes_with_space():
    ed = _editor()
    ed.command_buf = ":cr"
    ed.complete_command()
    assert ed.command_buf == ":critpath "


def test_command_multiple_matches_lists_candidates():
    ed = _editor()
    ed.command_buf = ":q"
    ed.complete_command()
    assert ed.command_buf == ":q"       # no longer prefix to extend
    assert "quit" in ed.message and "q!" in ed.message


def test_command_prefix_extension():
    ed = _editor()
    ed.command_buf = ":des"
    ed.complete_command()
    assert ed.command_buf == ":desc"    # desc/describe common prefix
    assert "describe" in ed.message


def test_theme_argument_completion():
    ed = _editor()
    ed.command_buf = ":theme g"
    ed.complete_command()
    assert ed.command_buf == ":theme galaxy"


# --- GUI: Tab accepts the highlighted completion ------------------------------


@pytest.fixture(scope="module")
def app():
    pytest.importorskip("abax.gui._qtcompat")
    from abax.gui._qtcompat import QApplication

    return QApplication.instance() or QApplication([])


def test_gui_tab_accepts_popup_candidate(app):
    from abax.gui._qtcompat import QLineEdit
    from abax.gui.completion import FormulaCompleter

    try:
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
    except ImportError:
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent

    le = QLineEdit()
    fc = FormulaCompleter(le)
    le.show()
    le.setText("=SUMI")
    le.setCursorPosition(5)
    fc._on_edited("=SUMI")              # opens the popup with SUMIF/SUMIFS
    assert fc._completer.popup().isVisible()
    tab = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    handled = fc.eventFilter(le, tab)
    assert handled                       # consumed — focus does not move
    assert le.text() == "=SUMIF("       # highlighted candidate inserted
    assert not fc._completer.popup().isVisible()
    le.deleteLater()
