"""External closed-workbook references (=[Book.abax]Sheet1!A1).

The hub is exercised with an injected fake loader (no file I/O in most tests);
one temp-file path check covers real resolution. The end-to-end test drives a
live Workbook formula through the tokenizer, parser, and resolver.
"""

from __future__ import annotations

import time

import pytest

from abax.core.errors import CellError, is_error
from abax.core.externref import (
    OFF_MARKER,
    ExternalRefHub,
    parse_external,
)
from abax.core.workbook import Workbook


def _wait_for(pred, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


class _FakeSheet:
    def __init__(self, grid):
        self._grid = grid

    def get_value(self, row, col):
        try:
            return self._grid[row][col]
        except (IndexError, KeyError):
            return None


class _FakeWorkbook:
    """Minimal stand-in exposing get_sheet/.sheet like a real Workbook."""

    def __init__(self, sheets):
        self._sheets = sheets

    def get_sheet(self, name):
        return self._sheets.get(name)

    @property
    def sheet(self):
        return next(iter(self._sheets.values()))


def _fake_loader(grid, sheet_name="Sheet1"):
    def _load(path):
        return _FakeWorkbook({sheet_name: _FakeSheet(grid)})
    return _load


# -- parse_external --------------------------------------------------------

def test_parse_external_forms():
    assert parse_external("[Book.abax]Sheet1") == ("Book.abax", "Sheet1")
    assert parse_external("[a/b.abax]") == ("a/b.abax", "")   # first sheet
    assert parse_external("Sheet1") is None                   # not external
    assert parse_external("") is None


# -- hub behaviour ---------------------------------------------------------

def test_hub_disabled_returns_off_and_loads_nothing():
    hub = ExternalRefHub()
    hub.loader = _fake_loader([[42]])
    assert hub.lookup("Book.abax", "Sheet1", 0, 0) == OFF_MARKER
    assert hub.book_count() == 0


def test_hub_loads_in_background_then_serves_value(tmp_path):
    (tmp_path / "Book.abax").write_text("{}")  # path must exist (is_file)
    hub = ExternalRefHub()
    hub.loader = _fake_loader([[10, 20], [30, 40]])
    hub.set_base_dir(tmp_path)
    hub.set_enabled(True)
    try:
        g0 = hub.generation()
        first = hub.lookup("Book.abax", "Sheet1", 1, 1)
        # First lookup is either the #N/A loading placeholder or — if the
        # background load already finished (fast runner) — the value. Both are
        # valid; the eventual value below is the real contract.
        assert (is_error(first) and first.code == CellError.NA) or first == 40
        assert _wait_for(lambda: not is_error(hub.lookup("Book.abax", "Sheet1", 1, 1)))
        assert hub.lookup("Book.abax", "Sheet1", 1, 1) == 40
        assert hub.generation() > g0
        assert hub.book_count() == 1
    finally:
        hub.set_enabled(False)


def test_hub_disallows_bad_suffix_and_missing_base():
    hub = ExternalRefHub()
    hub.loader = _fake_loader([[1]])
    hub.set_enabled(True)
    try:
        # relative path but no base dir -> #REF
        assert is_error(hub.lookup("Book.abax", "Sheet1", 0, 0))
        hub.set_base_dir("/tmp")
        # disallowed extension -> #REF, never loaded
        out = hub.lookup("Book.exe", "Sheet1", 0, 0)
        assert is_error(out) and out.code == CellError.REF
    finally:
        hub.set_enabled(False)


def test_hub_missing_file_reports_ref(tmp_path):
    hub = ExternalRefHub()
    hub.loader = _fake_loader([[1]])
    hub.set_base_dir(tmp_path)
    hub.set_enabled(True)
    try:
        hub.lookup("Nope.abax", "Sheet1", 0, 0)  # kicks off load of a missing file
        assert _wait_for(lambda: hub.lookup("Nope.abax", "Sheet1", 0, 0).code == CellError.REF
                         if is_error(hub.lookup("Nope.abax", "Sheet1", 0, 0)) else False)
    finally:
        hub.set_enabled(False)


def test_hub_disable_clears_cache(tmp_path):
    (tmp_path / "Book.abax").write_text("{}")
    hub = ExternalRefHub()
    hub.loader = _fake_loader([[1]])
    hub.set_base_dir(tmp_path)
    hub.set_enabled(True)
    hub.lookup("Book.abax", "Sheet1", 0, 0)
    assert _wait_for(lambda: hub.book_count() == 1)
    hub.set_enabled(False)
    assert hub.book_count() == 0


# -- end-to-end through a live formula -------------------------------------

def test_formula_resolves_external_ref(tmp_path):
    from abax.core import externref

    (tmp_path / "ext.abax").write_text("{}")
    hub = externref.HUB
    saved_loader = hub.loader
    hub.loader = _fake_loader([[0, 0, 0], [0, 0, 0], [0, 0, 7]], "Data")
    hub.set_base_dir(tmp_path)
    hub.set_enabled(True)
    try:
        wb = Workbook()
        wb.sheet.set_cell(0, 0, "=[ext.abax]Data!C3 + 1")
        wb.recalculate()
        # First read is either the loading placeholder (#N/A, background load
        # still pending) or — on a fast machine where the load already finished —
        # the resolved value. Both are valid; don't race on the transient state.
        first = wb.sheet.get_value(0, 0)
        assert is_error(first) or first == 8
        assert _wait_for(lambda: hub.lookup("ext.abax", "Data", 2, 2) == 7)
        wb.recalculate()                   # external sheet is always-dirty
        assert wb.sheet.get_value(0, 0) == 8
    finally:
        hub.set_enabled(False)
        hub.loader = saved_loader


# -- GUI consent wiring ----------------------------------------------------

def test_gui_external_toggle_and_poll():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from abax.core import externref
    from abax.gui._qtcompat import QApplication
    from abax.gui.main_window import MainWindow
    from abax.settings import Settings

    _ = QApplication.instance() or QApplication([])
    win = MainWindow(Settings())
    try:
        assert hasattr(win, "_external_refs_action")
        assert externref.HUB.enabled is False       # off by default
        win._settings.external_refs_enabled = True
        externref.HUB.set_enabled(True)
        g0 = win._extern_generation
        externref.HUB._bump()
        win._poll_live_data()                        # picks up the ext generation
        assert win._extern_generation != g0
    finally:
        externref.HUB.set_enabled(False)
