"""Screen-reader accessibility wiring for the model/view grid.

Runs the real ``MainWindow`` offscreen (like ``test_gui_grid``). Skips cleanly
when PyQt6/PySide6 is not installed, so the zero-optional-deps suite stays green.
The model serves ``AccessibleTextRole``/``AccessibleDescriptionRole`` for cells
and headers; the view carries an accessible name/description.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, Qt  # noqa: E402
from abax.settings import Settings  # noqa: E402


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


ACC_TEXT = Qt.ItemDataRole.AccessibleTextRole
ACC_DESC = Qt.ItemDataRole.AccessibleDescriptionRole


def _acc_text(model, r, c):
    return model.data(model.index(r, c), ACC_TEXT)


def _acc_desc(model, r, c):
    return model.data(model.index(r, c), ACC_DESC)


# --- cell accessible text / description -----------------------------------

def test_cell_accessible_text_has_ref_and_value(win):
    win._commit_cell(0, 0, "42")  # A1 = 42
    text = _acc_text(win._model, 0, 0)
    assert "A1" in text
    assert "42" in text


def test_formula_cell_accessible_description_has_formula(win):
    win._commit_cell(0, 0, "42")        # A1 = 42
    win._commit_cell(1, 1, "=A1+1")     # B2 = =A1+1
    desc = _acc_desc(win._model, 1, 1)
    assert desc is not None
    assert "=A1+1" in desc


def test_formula_cell_accessible_text_shows_computed_value(win):
    win._commit_cell(0, 0, "42")
    win._commit_cell(1, 1, "=A1+1")
    text = _acc_text(win._model, 1, 1)
    assert "B2" in text
    assert "43" in text  # the displayed (computed) value, not the formula


def test_empty_cell_accessible_text_is_just_ref(win):
    text = _acc_text(win._model, 4, 2)  # C5, untouched
    assert text == "C5"


def test_literal_cell_has_no_formula_description(win):
    win._commit_cell(0, 0, "42")
    assert _acc_desc(win._model, 0, 0) is None


# --- header accessible text ------------------------------------------------

def test_header_accessible_text_column_and_row(win):
    model = win._model
    col = model.headerData(0, Qt.Orientation.Horizontal, ACC_TEXT)
    row = model.headerData(0, Qt.Orientation.Vertical, ACC_TEXT)
    assert "A" in col          # column A
    assert col != "A"          # spoken form, not the bare display letter
    assert "1" in row          # row 1


def test_header_display_role_unchanged(win):
    # Purely additive: the visible header text is still the bare letter / number.
    model = win._model
    assert model.headerData(0, Qt.Orientation.Horizontal,
                            Qt.ItemDataRole.DisplayRole) == "A"
    assert model.headerData(0, Qt.Orientation.Vertical,
                            Qt.ItemDataRole.DisplayRole) == "1"


# --- view accessibility ----------------------------------------------------

def test_view_has_accessible_name_and_description(win):
    assert win._table.accessibleName()
    assert win._table.accessibleDescription()


def test_current_cell_change_updates_view_description(win):
    win._commit_cell(0, 0, "42")
    win._table.setCurrentCell(0, 0)
    QApplication.processEvents()
    desc = win._table.accessibleDescription()
    assert "A1" in desc
