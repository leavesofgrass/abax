"""Calculator <-> cell value bridge (both directions, multi-cell, entry commit)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, QTableWidgetSelectionRange  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    return MainWindow(Settings())


def test_cell_to_calc_loads_value(win):
    win._commit_cell(0, 0, "42")
    win._table.setCurrentCell(0, 0)
    win.cell_to_calc()                       # opens the calculator and loads 42
    panel = win._calc_panel()
    assert panel is not None
    assert panel.current_value() == 42.0


def test_calc_to_cells_fills_selection(win):
    win.show_calculator()
    panel = win._calc_panel()
    panel.load_value(7)
    rpn = getattr(getattr(panel._widget, "keypad", None), "rpn", None)
    if rpn is not None and hasattr(rpn, "base"):
        rpn.base = 10                   # exercise the plain decimal fill path
    win._table.clearSelection()
    win._table.setRangeSelected(QTableWidgetSelectionRange(1, 1, 2, 2), True)
    win.calc_to_cells()
    sheet = win._doc.workbook.sheet
    for r in (1, 2):
        for c in (1, 2):
            assert sheet.get_raw(r, c) == "7"
    assert win._doc.can_undo            # the bulk write is one undo step


def test_send_uses_current_base(win):
    # User-reported: a hex/oct/bin session was sending the *decimal* conversion.
    # "Send to cell" must now write the value in the calculator's current base.
    win.show_calculator()
    panel = win._calc_panel()
    rpn = getattr(getattr(panel._widget, "keypad", None), "rpn", None)
    if rpn is None or not hasattr(rpn, "word_size"):
        pytest.skip("default model is not the HP-16C programmer keypad")
    panel.load_value(255)
    rpn.base = 16
    assert panel.current_text() == "FF"           # bare digits, no 0x prefix
    rpn.base = 8
    assert panel.current_text() == "377"
    rpn.base = 2
    assert panel.current_text() == "11111111"
    rpn.base = 10
    assert panel.current_text() == "255"          # decimal base still sends decimal


def test_uncommitted_entry_is_read(win):
    # The old bug: a number typed but not Enter-committed sat in the entry buffer
    # and "Send to cell" wrote a stale X. current_value() must commit it first.
    win.show_calculator()
    panel = win._calc_panel()
    w = panel._widget
    if not hasattr(w, "keypad"):
        pytest.skip("default model is not the HP keypad")
    w.keypad.entry = "9"            # single digit: same in the 16C's hex mode
    assert panel.current_value() == 9.0
    assert w.keypad.entry == ""     # the entry was committed, not left dangling


def test_algebraic_model_is_wired(win):
    from abax.gui.calc.algebraic_faceplate import AlgebraicFaceplate

    win.show_calculator()
    panel = win._calc_panel()
    panel._kind = "alg"
    panel._rebuild()
    assert isinstance(panel._widget, AlgebraicFaceplate)
    panel.load_value(12.5)              # value bridge works for the algebraic calc
    assert panel.current_value() == 12.5


def test_model_list_order_and_default(win):
    from abax.gui.calc.calculator_panel import _MODELS

    labels = [m[0] for m in _MODELS]
    assert labels[0] == "Algebraic"                              # algebraic first
    assert labels[1:4] == ["HP-12C", "HP-15C", "HP-16C"]         # HP ascending
    assert labels[4:] == ["TI-82", "TI-83 Plus", "TI-84 Plus", "TI-84 Plus CE"]
    # The default selection stays HP-16C even though it's no longer first.
    win.show_calculator()
    panel = win._calc_panel()
    assert panel._model_box.currentText() == "HP-16C"
    assert hasattr(panel._widget, "keypad")


def test_two_consecutive_sends(win):
    # Repro: first send worked, second "did nothing". Send twice to two cells.
    win.show_calculator()
    panel = win._calc_panel()
    rpn = getattr(getattr(panel._widget, "keypad", None), "rpn", None)
    if rpn is not None and hasattr(rpn, "base"):
        rpn.base = 10
    panel.load_value(11)
    win._table.clearSelection()
    win._table.setCurrentCell(0, 0)
    win.calc_to_cells()
    assert win._doc.workbook.sheet.get_raw(0, 0) == "11"

    panel.load_value(22)
    win._table.clearSelection()
    win._table.setCurrentCell(1, 1)
    win.calc_to_cells()
    assert win._doc.workbook.sheet.get_raw(1, 1) == "22", \
        f"second send wrote {win._doc.workbook.sheet.get_raw(1, 1)!r}"


def test_second_send_without_reselect_keeps_target(win):
    # The real-GUI repro: the user stays in the calculator window and does NOT
    # re-click the grid between sends. The current cell must survive refresh so
    # the second send lands on the same target (not silently on A1).
    win.show_calculator()
    panel = win._calc_panel()
    rpn = getattr(getattr(panel._widget, "keypad", None), "rpn", None)
    if rpn is not None and hasattr(rpn, "base"):
        rpn.base = 10
    win._table.clearSelection()
    win._table.setCurrentCell(2, 2)
    panel.load_value(11)
    win.calc_to_cells()
    assert win._doc.workbook.sheet.get_raw(2, 2) == "11"
    panel.load_value(22)
    win.calc_to_cells()                       # no re-selection
    assert win._doc.workbook.sheet.get_raw(2, 2) == "22", (
        f"second send missed target — A1={win._doc.workbook.sheet.get_raw(0, 0)!r} "
        f"C3={win._doc.workbook.sheet.get_raw(2, 2)!r} "
        f"cur=({win._table.currentRow()},{win._table.currentColumn()})")


def test_shortcut_actions_labeled_and_callable(win):
    # The shortcuts dialog reuses the command palette: a {label+key: trigger} map.
    actions = win._shortcut_actions()
    assert actions
    assert all(callable(v) for v in actions.values())
    assert any("Ctrl+F" in k for k in actions)        # Find / Replace is present
    assert any(" > " in k for k in actions)           # entries carry the menu path (ASCII)


def test_calc_model_choice_persists(win):
    # Changing the model writes it to settings; a fresh panel restores it.
    win.show_calculator()
    panel = win._calc_panel()
    ix = next(i for i in range(panel._model_box.count())
              if panel._model_box.itemData(i) == ("hp", "15c"))
    panel._model_box.setCurrentIndex(ix)
    assert win._settings.calc_model == "15c"

    from abax.gui.calc.calculator_panel import CalculatorPanel
    restored = CalculatorPanel(win)
    assert (restored._kind, restored._key) == ("hp", "15c")
    assert restored._model_box.currentText() == "HP-15C"


def test_ui_font_qss_targets_text_widgets_only(win):
    # The dyslexia-font layer must reach cells/console/terminal but leave QLabel
    # (the calculator LCD) and painted faceplates alone.
    win._ui_font_family = ""
    assert win._ui_font_qss() == ""
    win._ui_font_family = "OpenDyslexic"
    qss = win._ui_font_qss()
    assert 'font-family: "OpenDyslexic"' in qss
    assert "QTableView" in qss and "QPlainTextEdit" in qss
    assert "QLabel" not in qss
    win._ui_font_family = ""        # reset so other tests see the default


def test_send_without_calculator_is_safe(win):
    win.calc_to_cells()                      # no calculator open
    assert "Ctrl+K" in win.statusBar().currentMessage()
    assert win._doc.workbook.sheet.get_raw(0, 0) == ""   # nothing written
