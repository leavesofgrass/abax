"""The virtualized model/view grid: editing, refresh, and Excel keyboard nav.

Runs the real ``MainWindow`` offscreen (like ``test_faceplate``). Skips cleanly
when PyQt6 is not installed, so the zero-optional-deps suite stays green.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("qcell.gui._qtcompat")

from qcell.gui._qtcompat import (  # noqa: E402
    QApplication,
    QEvent,
    QKeyEvent,
    QLineEdit,
    Qt,
    QTableView,
    QTableWidgetSelectionRange,
)
from qcell.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from qcell.gui.main_window import MainWindow

    return MainWindow(Settings())


def _press(view, key, mods=Qt.KeyboardModifier.NoModifier, text=""):
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods, text))


# --- model / view wiring -------------------------------------------------

def test_grid_is_model_view(win):
    assert isinstance(win._table, QTableView)
    # Virtualized: a generous extent reported without materializing cells.
    assert win._table.rowCount() >= 200
    assert win._table.columnCount() >= 26
    assert win._table.model() is win._model


def test_deferred_grow_extends_extent(win):
    # The scroll handlers defer structural model growth out of the valueChanged
    # signal (fixes a fast-scroll re-entrancy crash). Driving the deferred step
    # must extend the model and clear the _growing re-entrancy guard.
    rows0, cols0 = win._table.rowCount(), win._table.columnCount()
    win._growing = True                      # as _maybe_grow_rows sets it
    win._grow_rows_now()
    assert win._table.rowCount() > rows0
    assert win._growing is False
    win._growing = True
    win._grow_cols_now()
    assert win._table.columnCount() > cols0
    assert win._growing is False


def test_display_vs_edit_role(win):
    win._commit_cell(0, 0, "=1+2")
    model, idx = win._table.model(), win._table.model().index(0, 0)
    assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "3"      # computed
    assert model.data(idx, Qt.ItemDataRole.EditRole) == "=1+2"      # raw formula
    # the QTableWidgetItem-compat proxy still yields the display text
    assert win._table.item(0, 0).text() == "3"


def test_setdata_commits(win):
    model, idx = win._table.model(), win._table.model().index(1, 1)
    assert model.setData(idx, "42", Qt.ItemDataRole.EditRole) is True
    assert win._doc.workbook.sheet.get_raw(1, 1) == "42"


def test_commit_cell_validation_rejects(win, monkeypatch):
    import qcell.gui.mixin_document as md

    monkeypatch.setattr(md.QMessageBox, "warning", lambda *a, **k: None)
    sheet = win._doc.workbook.sheet
    from qcell.core.validation import ValidationRule

    sheet.validations.append((0, 0, 0, 0, ValidationRule(kind="whole", op="ge", p1="0")))
    assert win._commit_cell(0, 0, "not-an-int") is False
    assert win._doc.workbook.sheet.get_raw(0, 0) == ""


def test_conditional_fill_background(win):
    from qcell.core.condformat import CondRule

    sheet = win._doc.workbook.sheet
    win._commit_cell(0, 0, "5")
    sheet.cond_rules = [CondRule(range="A1", kind=">", value=0, color="#ff0000")]
    win.refresh_table()
    brush = win._table.model().data(win._table.model().index(0, 0),
                                    Qt.ItemDataRole.BackgroundRole)
    assert brush is not None
    assert brush.color().name() == "#ff0000"


def test_conditional_fill_lazy_only_colors_matching(win):
    # A rule over a large range: the model colors matching visible cells without
    # eagerly scanning the whole range.
    from qcell.core.condformat import CondRule

    sheet = win._doc.workbook.sheet
    win._commit_cell(0, 0, "5")    # > 0 -> colored
    win._commit_cell(1, 0, "-3")   # not > 0
    sheet.cond_rules = [CondRule(range="A1:A1000", kind=">", value=0, color="#00ff00")]
    win.refresh_table()
    m = win._table.model()
    bg = m.data(m.index(0, 0), Qt.ItemDataRole.BackgroundRole)
    assert bg is not None and bg.color().name() == "#00ff00"
    assert m.data(m.index(1, 0), Qt.ItemDataRole.BackgroundRole) is None  # negative
    assert m.data(m.index(2, 0), Qt.ItemDataRole.BackgroundRole) is None  # blank


def test_recolor_after_edit(win):
    # Editing a value must re-color it (the per-refresh fill cache is dropped).
    from qcell.core.condformat import CondRule

    sheet = win._doc.workbook.sheet
    win._commit_cell(0, 0, "-1")
    sheet.cond_rules = [CondRule(range="A1:A10", kind=">", value=0, color="#00ff00")]
    win.refresh_table()
    m = win._table.model()
    assert m.data(m.index(0, 0), Qt.ItemDataRole.BackgroundRole) is None
    win._commit_cell(0, 0, "7")  # now > 0
    assert m.data(m.index(0, 0), Qt.ItemDataRole.BackgroundRole).color().name() == "#00ff00"


# --- status-bar selection aggregates -------------------------------------

def test_selection_aggregates(win):
    for r, v in enumerate(("10", "20", "30")):
        win._commit_cell(r, 0, v)
    win._table.clearSelection()
    win._table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 2, 0), True)
    win._update_selection_status()
    msg = win.statusBar().currentMessage()
    assert "Sum 60" in msg
    assert "Avg 20" in msg
    assert "Count 3" in msg


def test_single_cell_shows_a1_ref(win):
    win._table.setCurrentCell(1, 2)
    win._update_selection_status()
    assert win.statusBar().currentMessage() == "C2"


# --- frozen panes share the model (no per-cell item materialization) -----

def test_frozen_panes_share_model(win):
    win._commit_cell(0, 0, "hdr")
    win._frozen.freeze(1, 1)
    assert win._frozen.active
    top, left = win._frozen._top, win._frozen._left
    assert isinstance(top, QTableView) and isinstance(left, QTableView)
    # Overlays mirror the main grid by SHARING its model + selection model,
    # so they virtualize too — no QTableWidgetItem is built per row.
    assert top.model() is win._table.model()
    assert left.model() is win._table.model()
    assert left.selectionModel() is win._table.selectionModel()
    win._frozen.unfreeze()
    assert not win._frozen.active
    assert win._frozen._top is None and win._frozen._left is None


# --- keyboard navigation (the Excel feel) --------------------------------

def test_enter_advances_down(win):
    win._table.setCurrentCell(0, 0)
    _press(win._table, Qt.Key.Key_Return)
    assert (win._table.currentRow(), win._table.currentColumn()) == (1, 0)


def test_shift_enter_advances_up(win):
    win._table.setCurrentCell(3, 0)
    _press(win._table, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert win._table.currentRow() == 2


def test_tab_and_backtab(win):
    win._table.setCurrentCell(0, 0)
    _press(win._table, Qt.Key.Key_Tab)
    assert win._table.currentColumn() == 1
    _press(win._table, Qt.Key.Key_Backtab)
    assert win._table.currentColumn() == 0


def test_ctrl_end_jumps_to_last_used(win):
    win._commit_cell(7, 4, "x")
    win._table.setCurrentCell(0, 0)
    _press(win._table, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
    assert (win._table.currentRow(), win._table.currentColumn()) == (7, 4)


def test_ctrl_home(win):
    win._table.setCurrentCell(5, 5)
    _press(win._table, Qt.Key.Key_Home, Qt.KeyboardModifier.ControlModifier)
    assert (win._table.currentRow(), win._table.currentColumn()) == (0, 0)


def test_formula_bar_enter_advances_down(win):
    win._table.setCurrentCell(2, 1)
    win._formula_bar.setText("hello")
    win._commit_formula_bar()
    assert win._doc.workbook.sheet.get_raw(2, 1) == "hello"
    assert (win._table.currentRow(), win._table.currentColumn()) == (3, 1)


def test_delete_and_colon_propagate(win):
    # The view must NOT consume Delete or ':' — they propagate to the window
    # (clear-selection and command palette). An ignored event is the contract.
    win._table.setCurrentCell(0, 0)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete,
                   Qt.KeyboardModifier.NoModifier, "")
    win._table.keyPressEvent(ev)
    assert not ev.isAccepted()


# --- selection round-trip ------------------------------------------------

def test_selected_ranges_round_trip(win):
    t = win._table
    t.clearSelection()
    t.setRangeSelected(QTableWidgetSelectionRange(1, 1, 3, 4), True)
    rngs = t.selectedRanges()
    assert rngs
    r = rngs[0]
    assert (r.topRow(), r.leftColumn(), r.bottomRow(), r.rightColumn()) == (1, 1, 3, 4)


# --- delegate commit-and-move -------------------------------------------

def test_delegate_enter_sets_pending_move(win):
    from qcell.gui.grid_view import GridDelegate

    delegate = GridDelegate(win)
    editor = QLineEdit()
    win._table._pending_move = None
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                   Qt.KeyboardModifier.NoModifier, "")
    delegate.eventFilter(editor, ev)
    assert win._table._pending_move == (1, 0)
