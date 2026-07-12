"""The conditional-format dialog: it reshapes per kind and builds the right rule."""

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
    from abax.gui._qtcompat import QEvent as _QEvent
    _win.deleteLater()
    app.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    app.processEvents()


def _dialog(win):
    from abax.gui.dialogs.condformat_dialog import CondFormatDialog

    return CondFormatDialog(win)


def test_every_kind_reshapes_without_error(win):
    """Selecting each kind must reconfigure the form cleanly (no exceptions)."""
    dlg = _dialog(win)
    for i in range(dlg._kind.count()):
        dlg._kind.setCurrentIndex(i)  # fires _on_kind
    # After a scale kind, the max-colour row is visible; after a solid kind it isn't.
    dlg._kind.setCurrentIndex(dlg._kind.findData("colorscale"))
    assert dlg._color2_btn.isVisibleTo(dlg)
    dlg._kind.setCurrentIndex(dlg._kind.findData(">"))
    assert not dlg._color2_btn.isVisibleTo(dlg)


def test_accept_appends_top_n_rule(win):
    sheet = win._doc.workbook.sheet
    sheet.cond_rules.clear()
    dlg = _dialog(win)
    dlg._range.setText("A1:A9")
    dlg._kind.setCurrentIndex(dlg._kind.findData("top_n"))
    dlg._value.setText("3")
    dlg._accept()

    assert len(sheet.cond_rules) == 1
    rule = sheet.cond_rules[0]
    assert rule.kind == "top_n"
    assert rule.range == "A1:A9"
    assert rule.value == "3"


def test_accept_three_color_scale_uses_three_colors(win):
    sheet = win._doc.workbook.sheet
    sheet.cond_rules.clear()
    dlg = _dialog(win)
    dlg._color, dlg._color2, dlg._color3 = "#111111", "#222222", "#333333"
    dlg._kind.setCurrentIndex(dlg._kind.findData("colorscale3"))
    dlg._accept()

    rule = sheet.cond_rules[0]
    assert rule.kind == "colorscale3"
    assert rule.value == "#111111"    # min colour
    assert rule.value2 == "#222222"   # max colour
    assert rule.color == "#333333"    # midpoint colour
