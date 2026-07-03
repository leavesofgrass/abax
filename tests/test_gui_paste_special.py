"""Paste Special — values-only, transpose, and skip-blanks.

Covers the pure core helpers (``copy_region_values`` / ``transpose_clip`` /
``paste_clip(skip_blanks=...)``) and the GUI ``paste_special`` handler, driving
the modal dialog by patching ``PasteSpecialDialog.get_options``.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from abax.core.reference import parse_a1  # noqa: E402

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, QTableWidgetSelectionRange  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# -- core helpers (pure, no Qt) ---------------------------------------------


def test_transpose_clip_swaps_axes():
    from abax.core.fill import Clip, transpose_clip

    clip = Clip((0, 0), [["a", "b", "c"], ["d", "e", "f"]])  # 2x3
    t = transpose_clip(clip)
    assert t.grid == [["a", "d"], ["b", "e"], ["c", "f"]]  # 3x2
    assert transpose_clip(Clip((0, 0), [])).grid == []


def test_paste_clip_skip_blanks_leaves_destination():
    from abax.core.fill import Clip, paste_clip
    from abax.core.sheet import Sheet

    sheet = Sheet()
    sheet.set_cell(0, 1, "KEEP")  # B1 destination pre-filled
    clip = Clip((0, 0), [["x", ""]])  # second cell blank
    paste_clip(sheet, clip, (0, 0), mode="absolute", skip_blanks=True)
    assert sheet.display(0, 0) == "x"
    assert sheet.display(0, 1) == "KEEP"  # blank source didn't overwrite


# -- GUI integration --------------------------------------------------------


def _win():
    from abax.gui.main_window import MainWindow

    return MainWindow(Settings())


def _patch_options(monkeypatch, **opts):
    import abax.gui.dialogs.paste_special_dialog as psd

    full = {"values": opts.get("values", False) or opts.get("transpose", False),
            "transpose": opts.get("transpose", False),
            "skip_blanks": opts.get("skip_blanks", False)}
    monkeypatch.setattr(
        psd.PasteSpecialDialog, "get_options",
        classmethod(lambda cls, window, *, formulas_available=True: full))


def _select(win, r1, c1, r2, c2):
    win._table.clearSelection()
    win._table.setRangeSelected(QTableWidgetSelectionRange(r1, c1, r2, c2), True)


def _disp(win, a1):
    r, c = parse_a1(a1)
    return win._doc.workbook.sheet.display(r, c)


def _raw(win, a1):
    r, c = parse_a1(a1)
    return win._doc.workbook.sheet.get_raw(r, c)


def test_paste_special_values_only_drops_formula(app, monkeypatch):
    win = _win()
    s = win._doc.workbook.sheet
    s.set_cell(0, 0, "10")
    s.set_cell(1, 0, "=A1+5")  # -> 15
    _select(win, 0, 0, 1, 0)
    win.copy_selection()
    win._table.setCurrentCell(0, 2)  # C1
    _patch_options(monkeypatch, values=True)
    win.paste_special()
    assert _raw(win, "C2") == "15"  # literal value, not the formula
    assert _disp(win, "C2") == "15"


def test_paste_special_formulas_shift_relative(app, monkeypatch):
    win = _win()
    s = win._doc.workbook.sheet
    s.set_cell(0, 0, "10")
    s.set_cell(1, 0, "=A1+5")
    _select(win, 0, 0, 1, 0)
    win.copy_selection()
    win._table.setCurrentCell(0, 2)
    _patch_options(monkeypatch, values=False)
    win.paste_special()
    assert _raw(win, "C2") == "=C1+5"  # reference shifted with the paste


def test_paste_special_transpose(app, monkeypatch):
    win = _win()
    s = win._doc.workbook.sheet
    s.set_cell(0, 0, "10")
    s.set_cell(1, 0, "20")  # a 2x1 column
    _select(win, 0, 0, 1, 0)
    win.copy_selection()
    win._table.setCurrentCell(0, 2)  # C1
    _patch_options(monkeypatch, transpose=True)
    win.paste_special()
    assert _disp(win, "C1") == "10"
    assert _disp(win, "D1") == "20"  # became a 1x2 row
    assert _raw(win, "C2") == ""


def test_paste_special_skip_blanks(app, monkeypatch):
    win = _win()
    s = win._doc.workbook.sheet
    s.set_cell(0, 0, "10")
    s.set_cell(2, 0, "20")  # A2 left blank
    s.set_cell(1, 2, "KEEP")  # C2 pre-existing
    _select(win, 0, 0, 2, 0)
    win.copy_selection()
    win._table.setCurrentCell(0, 2)  # C1
    _patch_options(monkeypatch, values=True, skip_blanks=True)
    win.paste_special()
    assert _disp(win, "C1") == "10"
    assert _disp(win, "C2") == "KEEP"  # blank source skipped
    assert _disp(win, "C3") == "20"


def test_paste_special_is_one_undo_step(app, monkeypatch):
    win = _win()
    win._doc.workbook.sheet.set_cell(0, 0, "7")
    _select(win, 0, 0, 0, 0)
    win.copy_selection()
    win._table.setCurrentCell(0, 2)
    _patch_options(monkeypatch, values=True)
    win.paste_special()
    assert _disp(win, "C1") == "7"
    win.undo_edit()
    assert _disp(win, "C1") == ""  # a single checkpoint restored
