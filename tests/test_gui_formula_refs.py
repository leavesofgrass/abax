"""GUI formula-edit reference highlighting — the coloured range boxes.

Offscreen (QT_QPA_PLATFORM=offscreen). The view's ``set_formula_refs`` /
``_formula_ref_rect`` are exercised directly plus through the formula-bar and
editor-close hooks; actual pixels aren't asserted (offscreen), the geometry and
state transitions are.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, QEvent  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    _win = MainWindow(Settings())
    yield _win
    _win.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_set_formula_refs_populates_spans(win):
    view = win._table
    view.set_formula_refs("=A1+B2:C3")
    assert len(view._formula_refs) == 2
    (a1, rng) = view._formula_refs
    assert (a1.r1, a1.c1, a1.r2, a1.c2) == (0, 0, 0, 0) and a1.color == 0
    assert (rng.r1, rng.c1, rng.r2, rng.c2) == (1, 1, 2, 2) and rng.color == 1


def test_non_formula_and_none_clear(win):
    view = win._table
    view.set_formula_refs("=A1")
    assert view._formula_refs
    view.set_formula_refs("plain text")
    assert view._formula_refs == []
    view.set_formula_refs("=B2")
    view.set_formula_refs(None)
    assert view._formula_refs == []


def test_ref_rect_geometry_covers_the_range(win):
    view = win._table
    view.set_formula_refs("=B2:C3")
    (span,) = view._formula_refs
    rect = view._formula_ref_rect(span)
    assert rect.isValid()
    # Two columns / two rows: at least as wide/tall as one column/row each.
    assert rect.width() >= view.columnWidth(1)
    assert rect.height() >= view.rowHeight(1)
    # Anchored at B2's viewport position.
    assert rect.left() == view.columnViewportPosition(1)
    assert rect.top() == view.rowViewportPosition(1)


def test_cross_sheet_refs_skipped_but_colors_stable(win):
    view = win._table
    view.set_formula_refs("=Sheet2!A1 + B2")
    (b2,) = view._formula_refs           # Sheet2!A1 is not on the active sheet
    assert (b2.r1, b2.c1) == (1, 1)
    assert b2.color == 1                  # the cross-sheet ref consumed colour 0


def test_formula_bar_gates_on_focus(win, monkeypatch):
    view = win._table
    # Bar focused: typing a formula highlights.
    monkeypatch.setattr(type(win._formula_bar), "hasFocus", lambda self: True)
    win._formula_bar.setText("=A1:A5")
    assert len(view._formula_refs) == 1
    # Bar not focused (plain cell navigation rewrites its text): no highlight.
    monkeypatch.setattr(type(win._formula_bar), "hasFocus", lambda self: False)
    win._formula_bar.setText("=B1:B5")
    assert view._formula_refs == []


def test_close_editor_clears_refs(win):
    from abax.gui._qtcompat import QAbstractItemDelegate

    view = win._table
    view.set_formula_refs("=A1")
    assert view._formula_refs
    view.closeEditor(win._formula_bar,      # any editor close drops the boxes
                     QAbstractItemDelegate.EndEditHint.NoHint)
    assert view._formula_refs == []


def test_paint_event_with_refs_does_not_crash(win):
    view = win._table
    win.resize(800, 600)
    win.show()
    view.set_formula_refs("=A1+B2:C3+ZZ999")
    view.viewport().repaint()               # exercises _paint_formula_refs
    win.hide()
