"""Column widths / row heights / freeze survive save + load (envelope v2).

The QTableView owns the rendered geometry; the sheet model owns the persisted
copy (``col_widths`` / ``row_heights`` / ``frozen_rows`` / ``frozen_cols``). These
tests drive a real MainWindow offscreen: set some non-default sizes and a freeze,
save to a temp ``.abax``, reopen in a fresh window, and assert everything comes
back. A manual header resize (``sectionResized``) is also checked to write
straight through to the sheet. Skips cleanly without PyQt6.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, QThread  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _new_window(app):
    from abax.gui.main_window import MainWindow

    return MainWindow(Settings())


def _dispose(app, win) -> None:
    from abax.gui._qtcompat import QEvent

    win.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _wait_io(win, app, timeout_ms: int = 5000) -> None:
    waited = 0
    while getattr(win, "_io_busy", False) and waited < timeout_ms:
        app.processEvents()
        QThread.msleep(10)
        waited += 10
    app.processEvents()
    assert not win._io_busy, "I/O did not finish in time"


def test_widths_heights_freeze_roundtrip(app, tmp_path):
    """Set non-default sizes + a freeze, save, reopen: they all come back."""
    win = _new_window(app)
    try:
        win._commit_cell(0, 0, "seed")  # a populated cell, so it's a real sheet
        # Header defaults are col=100, row=30 — pick clearly different sizes.
        win._table.setColumnWidth(1, 175)
        win._table.setColumnWidth(3, 220)
        win._table.setRowHeight(2, 48)
        win._frozen.freeze(2, 1)   # 2 frozen rows, 1 frozen column

        out = tmp_path / "layout.abax"
        win.save_document(str(out))
        _wait_io(win, app)
        assert out.exists()
    finally:
        _dispose(app, win)

    # Reopen in a *fresh* window — nothing carried over in memory.
    win2 = _new_window(app)
    try:
        win2.open_document(str(out))
        _wait_io(win2, app)

        table = win2._table
        assert table.columnWidth(1) == 175
        assert table.columnWidth(3) == 220
        assert table.rowHeight(2) == 48
        # An untouched column keeps the header default (nothing was persisted).
        assert table.columnWidth(0) == table.horizontalHeader().defaultSectionSize()
        # Freeze re-applied onto the FrozenPanes overlay.
        assert (win2._frozen.rows, win2._frozen.cols) == (2, 1)
        assert win2._frozen.active
    finally:
        _dispose(app, win2)


def test_layout_written_into_envelope(app, tmp_path):
    """Save captures the view geometry into the sheet, so it rides in the file."""
    import json

    win = _new_window(app)
    try:
        win._commit_cell(0, 0, "x")
        win._table.setColumnWidth(2, 140)
        win._table.setRowHeight(1, 55)
        win._frozen.freeze(1, 0)

        out = tmp_path / "env.abax"
        win.save_document(str(out))
        _wait_io(win, app)

        env = json.loads(out.read_text(encoding="utf-8"))
        sheet0 = env["data"]["sheets"][0]
        assert sheet0.get("col_widths") == {"2": 140}
        assert sheet0.get("row_heights") == {"1": 55}
        assert sheet0.get("frozen") == [1, 0]
    finally:
        _dispose(app, win)


def test_no_layout_no_keys(app, tmp_path):
    """An untouched grid persists no width/height/freeze keys (files stay lean)."""
    import json

    win = _new_window(app)
    try:
        win._commit_cell(0, 0, "x")
        out = tmp_path / "bare.abax"
        win.save_document(str(out))
        _wait_io(win, app)

        env = json.loads(out.read_text(encoding="utf-8"))
        sheet0 = env["data"]["sheets"][0]
        assert "col_widths" not in sheet0
        assert "row_heights" not in sheet0
        assert "frozen" not in sheet0
    finally:
        _dispose(app, win)


def test_manual_resize_captured_live(app):
    """A user drag on a header border writes straight through to the sheet."""
    win = _new_window(app)
    try:
        win._ensure_layout_hooks()
        win._doc.dirty = False

        # resizeSection emits sectionResized, exactly as an interactive drag does.
        win._table.horizontalHeader().resizeSection(2, 160)
        assert win._doc.workbook.sheet.col_widths.get(2) == 160
        assert win._doc.dirty  # a fidelity change is a real, savable edit

        win._table.verticalHeader().resizeSection(4, 52)
        assert win._doc.workbook.sheet.row_heights.get(4) == 52

        # Dragging a section back to the default clears its sparse entry.
        default = win._table.horizontalHeader().defaultSectionSize()
        win._table.horizontalHeader().resizeSection(2, default)
        assert 2 not in win._doc.workbook.sheet.col_widths
    finally:
        _dispose(app, win)
