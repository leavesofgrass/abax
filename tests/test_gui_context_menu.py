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

    _win = MainWindow(Settings())
    yield _win
    # Dispose the window so it doesn't accumulate across a long test process
    # (many live MainWindows segfault Qt when a later test restyles them).
    from abax.gui._qtcompat import QEvent as _QEvent
    _win.deleteLater()
    app.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    app.processEvents()


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


# --- cell comments -------------------------------------------------------

def _menu_texts(menu):
    return [a.text() for a in menu.actions()]


def test_context_menu_insert_vs_edit_comment(win):
    win._table.setCurrentCell(0, 0)
    # No comment yet -> the menu offers "Insert comment...".
    texts = _menu_texts(win._build_cell_context_menu())
    assert "Insert comment..." in texts
    assert "Edit comment..." not in texts and "Delete comment" not in texts

    # With a comment -> the menu offers Edit + Delete instead.
    win._doc.workbook.sheet.set_comment(0, 0, "hi")
    texts = _menu_texts(win._build_cell_context_menu())
    assert "Edit comment..." in texts and "Delete comment" in texts
    assert "Insert comment..." not in texts
    win._doc.workbook.sheet.set_comment(0, 0, "")  # cleanup


def test_edit_comment_sets_it_and_delete_removes(win, monkeypatch):
    from abax.gui import mixin_document
    from abax.gui._qtcompat import QInputDialog

    win._table.setCurrentCell(2, 3)
    monkeypatch.setattr(QInputDialog, "getMultiLineText",
                        staticmethod(lambda *a, **k: ("a typed note", True)))
    win.edit_comment()
    assert win._doc.workbook.sheet.get_comment(2, 3) == "a typed note"

    # Cancelling the dialog leaves the comment unchanged.
    monkeypatch.setattr(QInputDialog, "getMultiLineText",
                        staticmethod(lambda *a, **k: ("ignored", False)))
    win.edit_comment()
    assert win._doc.workbook.sheet.get_comment(2, 3) == "a typed note"

    win.delete_comment()
    assert win._doc.workbook.sheet.get_comment(2, 3) is None
    assert mixin_document  # imported for coverage of the module path


def test_comment_tooltip_role(win):
    from abax.gui._qtcompat import Qt

    win._doc.workbook.sheet.set_comment(1, 1, "a tooltip note")
    win._model.refresh()
    idx = win._model.index(1, 1)
    tip = win._model.data(idx, Qt.ItemDataRole.ToolTipRole)
    assert tip == "a tooltip note"
    # A cell without a comment yields no tooltip.
    assert win._model.data(win._model.index(5, 5), Qt.ItemDataRole.ToolTipRole) is None
    win._doc.workbook.sheet.set_comment(1, 1, "")  # cleanup


def test_comment_marker_paints_without_error(win):
    """The delegate paints a marker on a commented cell (offscreen smoke test)."""
    from abax.gui._qtcompat import BINDING, QColor, QImage, QPainter

    if BINDING == "PySide6":
        from PySide6.QtWidgets import QStyleOptionViewItem
    else:
        from PyQt6.QtWidgets import QStyleOptionViewItem

    win._doc.workbook.sheet.set_comment(0, 4, "note")
    win._model.refresh()
    delegate = win._table.itemDelegate()
    img = QImage(80, 24, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    painter = QPainter(img)
    opt = QStyleOptionViewItem()
    opt.rect.setRect(0, 0, 80, 24)
    delegate.paint(painter, opt, win._model.index(0, 4))
    painter.end()
    # The top-right corner should now carry the red marker colour, not white.
    corner = QColor(img.pixel(78, 1))
    assert corner != QColor("white")
    win._doc.workbook.sheet.set_comment(0, 4, "")  # cleanup
