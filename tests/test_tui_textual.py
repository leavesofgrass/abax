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
    render_overlay,
    status_text,
)


def _cmd(ed, line):
    ed.command_buf = line
    ed.run_command()


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


def test_numpad_enter_as_ctrl_j_commits():
    # Terminals that send numpad Enter as LF surface it as ctrl+j; it must still
    # commit an edit like the main Enter key.
    ed = _editor()
    ed.row, ed.col = 4, 4
    handle_key(ed, "i", "i")
    for c in "=1+2":
        handle_key(ed, c, c)
    handle_key(ed, "ctrl+j", None)             # numpad Enter (LF)
    assert ed.sheet.get_raw(4, 4) == "=1+2"
    assert ed.mode == "normal"


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
    assert status_text(ed).startswith("=>")   # insert shows the live edit line


# --- visual mode + yank/paste (delegated to the shared editor dispatch) ------


def test_visual_yank_then_paste():
    doc = Document()
    sh = doc.workbook.sheet
    sh.set_cell(0, 0, "10")
    sh.set_cell(0, 1, "20")
    ed = TuiEditor(doc)
    handle_key(ed, "v", "v")                 # enter visual at A1
    assert ed.mode == "visual"
    handle_key(ed, "l", "l")                 # extend to B1
    handle_key(ed, "y", "y")                 # yank A1:B1 (cursor now at B1)
    assert ed.mode == "normal" and ed.clip is not None
    handle_key(ed, "0", "0")                 # back to column A
    handle_key(ed, "j", "j")                 # move to A2
    handle_key(ed, "p", "p")                 # paste
    assert ed.sheet.get_raw(1, 0) == "10"
    assert ed.sheet.get_raw(1, 1) == "20"


def test_visual_escape_cancels():
    ed = _editor()
    handle_key(ed, "v", "v")
    assert ed.mode == "visual"
    handle_key(ed, "escape", None)
    assert ed.mode == "normal"


def test_visual_delete_clears_selection():
    doc = Document()
    sh = doc.workbook.sheet
    sh.set_cell(0, 0, "10")
    sh.set_cell(0, 1, "20")
    ed = TuiEditor(doc)
    handle_key(ed, "v", "v")
    handle_key(ed, "l", "l")
    handle_key(ed, "d", "d")                 # delete A1:B1
    assert ed.mode == "normal"
    assert ed.sheet.get_raw(0, 0) == "" and ed.sheet.get_raw(0, 1) == ""


# --- theming + conditional-format colours -----------------------------------


def _styles(text):
    return " ".join(str(sp.style) for sp in text.spans)


def test_render_grid_applies_theme_and_cursor_style():
    ed = _editor()
    ed.theme_name = "hacker"                  # green theme -> color(46) for lcd
    text = render_grid(ed, 80, 24)
    styles = _styles(text)
    assert "reverse" in styles                # the cursor cell
    assert "color(" in styles                 # theme role colours applied


def test_galaxy_uses_truecolor_purple_surface():
    from abax.tui.textual_app import _cursor_style, _role_style, theme_surface
    from abax.tui.themes import THEMES

    g = THEMES["galaxy"]
    assert _role_style(g, "label") == "#a78bfa"        # violet headers (not pale)
    surf = theme_surface(g)
    assert surf["bg"] == "#1e1e2e" and surf["panel"] == "#181825"
    assert "#7c3aed" in _cursor_style(g)               # violet cursor block
    # A 256-only theme keeps the palette-index path and no truecolor surface.
    assert _role_style(THEMES["hacker"], "lcd").startswith("color(")
    assert theme_surface(THEMES["hacker"]) is None


def test_render_grid_uses_conditional_format_colors(monkeypatch):
    import abax.core.format.condformat as cf

    # A red rule on C3 (not the A1 cursor cell) -> #ff0000 -> xterm-256 index 196.
    monkeypatch.setattr(cf, "evaluate", lambda sheet, rules: {(2, 2): "#ff0000"})
    ed = _editor()
    ed.sheet.cond_rules = ["<sentinel-rule>"]  # non-empty so _cond_colors evaluates
    text = render_grid(ed, 80, 24)
    assert "color(196)" in _styles(text)


# --- overlay modes (help / browser / rpn / describe) + completions ----------


def test_help_overlay_opens_scrolls_and_closes():
    ed = _editor()
    handle_key(ed, "?", "?")                  # ? opens help
    assert ed.mode == "help"
    assert "Help" in render_overlay(ed, 80, 24).plain
    before = ed.help_idx
    handle_key(ed, "j", "j")
    assert ed.help_idx >= before
    handle_key(ed, "escape", None)
    assert ed.mode == "normal"


def test_function_browser_opens_and_navigates():
    ed = _editor()
    _cmd(ed, ":func")
    assert ed.mode == "browser"
    assert "Function browser" in render_overlay(ed, 80, 24).plain
    idx = ed.browser_idx
    handle_key(ed, "j", "j")
    assert ed.browser_idx == idx + 1
    handle_key(ed, "q", "q")                  # q closes
    assert ed.mode == "normal"


def test_rpn_overlay_evaluates_and_renders():
    ed = _editor()
    _cmd(ed, ":rpn")
    assert ed.mode == "rpn"
    for ch in "2 3 +":
        handle_key(ed, ch, ch)
    handle_key(ed, "enter", None)
    assert ed._ensure_rpn().stack[0] == 5      # X register
    assert "X:" in render_overlay(ed, 80, 24).plain
    handle_key(ed, "escape", None)
    assert ed.mode == "normal"


def test_describe_overlay_renders_lines():
    ed = _editor()
    ed.mode = "describe"
    ed.describe_range = "A1:A3"
    ed.describe_title = ""
    ed.describe_lines = [("count", "3"), ("mean", "20")]
    ed.describe_idx = 0
    plain = render_overlay(ed, 80, 24).plain
    assert "Describe" in plain and "mean" in plain
    handle_key(ed, "j", "j")
    assert ed.describe_idx == 1


def test_insert_completion_hint_in_status():
    ed = _editor()
    ed.row, ed.col = 4, 4                        # an empty cell (begin_insert loads "")
    handle_key(ed, "i", "i")
    for ch in "=SU":
        handle_key(ed, ch, ch)
    assert ed.completions                       # SUM, SUMIF, ...
    assert "SU" in status_text(ed)


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
