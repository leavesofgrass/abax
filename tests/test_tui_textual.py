"""Textual TUI front-end — headless (Pilot) and pure-function tests.

The Textual view is a thin shell over :class:`TuiEditor`; these tests drive it
without a real terminal. The pure grid/status/key functions are checked directly,
and the live app is exercised through Textual's ``run_test`` Pilot (run under
``asyncio.run`` so no pytest-asyncio dependency is needed).
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from abax.engine.document import Document  # noqa: E402
from abax.tui import TuiEditor  # noqa: E402
from abax.tui.textual_app import (  # noqa: E402
    AbaxTextualApp,
    grid_viewport,
    handle_key,
    render_grid,
    status_text,
)


def _editor():
    doc = Document()
    sh = doc.workbook.sheet
    sh.set_cell(0, 0, "10")
    sh.set_cell(0, 1, "20")
    sh.set_cell(1, 0, "=A1*2")
    return TuiEditor(doc)


# --- pure functions ---------------------------------------------------------


def test_grid_viewport_geometry():
    # 80 wide, 24 tall: 23 data rows (one header), (80-5)//11 = 6 columns.
    assert grid_viewport(80, 24) == (23, 6)
    # Never returns a non-positive dimension for a tiny window.
    assert grid_viewport(1, 1) == (1, 1)


def test_render_grid_shows_values_and_syncs_viewport():
    ed = _editor()
    text = render_grid(ed, 80, 24)
    plain = text.plain
    assert "A" in plain and "B" in plain          # column header
    assert "10" in plain and "20" in plain         # literal values
    assert "20" in plain                            # =A1*2 evaluated
    assert ed.viewport_rows == 23 and ed.viewport_cols == 6


def test_handle_key_normal_navigation():
    ed = _editor()
    handle_key(ed, "l", "l")
    handle_key(ed, "j", "j")
    assert (ed.row, ed.col) == (1, 1)
    handle_key(ed, "h", "h")
    handle_key(ed, "k", "k")
    assert (ed.row, ed.col) == (0, 0)


def test_handle_key_gg_and_G():
    ed = _editor()
    ed.row = 1
    handle_key(ed, "g", "g")       # arm
    handle_key(ed, "g", "g")       # gg -> top
    assert ed.row == 0
    handle_key(ed, "G", "G")       # last used row (row index 1 -> value 2)
    assert ed.row == 1


def test_handle_key_insert_commit_advances():
    ed = _editor()
    ed.row, ed.col = 2, 0
    handle_key(ed, "i", "i")
    assert ed.mode == "insert"
    for c in "=A1+5":
        handle_key(ed, c, c)
    handle_key(ed, "enter", None)
    assert ed.sheet.get_raw(2, 0) == "=A1+5"
    assert ed.mode == "normal"
    assert (ed.row, ed.col) == (3, 0)              # Enter advances down


def test_handle_key_insert_escape_discards():
    ed = _editor()
    ed.row, ed.col = 5, 5
    handle_key(ed, "i", "i")
    for c in "junk":
        handle_key(ed, c, c)
    handle_key(ed, "escape", None)
    assert ed.mode == "normal"
    assert ed.sheet.get_raw(5, 5) == ""


def test_command_backspace_past_colon_cancels():
    ed = _editor()
    handle_key(ed, "colon", ":")
    assert ed.mode == "command" and ed.command_buf == ":"
    handle_key(ed, "backspace", None)
    assert ed.mode == "normal" and ed.command_buf == ""


def test_status_text_reflects_mode():
    ed = _editor()
    assert "NORMAL" in status_text(ed)
    ed.begin_insert()
    assert "INSERT" in status_text(ed)


# --- live app via Pilot -----------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def test_app_navigation_and_edit_via_pilot():
    ed = _editor()
    app = AbaxTextualApp(ed)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("l", "l", "j")       # right, right, down
            assert (ed.row, ed.col) == (1, 2)
            await pilot.press("i", "4", "2", "enter")
            assert ed.sheet.get_raw(1, 2) == "42"

    _run(scenario())


def test_app_quit_command_exits():
    ed = _editor()
    app = AbaxTextualApp(ed)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("colon", "q", "enter")
            # :q on a clean doc sets running False; the app exits the context.

    _run(scenario())
    assert ed.running is False
