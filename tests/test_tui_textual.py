"""Textual TUI front-end — headless (Pilot) and pure-function tests.

The Textual view is a thin shell over :class:`TuiEditor`; these tests drive it
without a real terminal. The pure grid/status/key functions are checked directly,
and the live app is exercised through Textual's ``run_test`` Pilot (run under
``asyncio.run`` so no pytest-asyncio dependency is needed).
"""

from __future__ import annotations

import asyncio
import re

import pytest

pytest.importorskip("textual")

from abax.engine.document import Document  # noqa: E402
from abax.tui import TuiEditor  # noqa: E402
from abax.tui.textual_app import (  # noqa: E402
    AbaxTextualApp,
    grid_hit,
    grid_viewport,
    handle_key,
    render_grid,
    render_overlay,
    status_text,
    theme_surface,
)
from abax.tui.themes import THEMES  # noqa: E402


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


def test_grid_hit_maps_positions_and_rejects_chrome():
    ed = _editor()
    # An 80x22 widget: 21 data rows under the header, 6 columns of 11 cells
    # after the 5-wide row-number gutter (mirrors grid_viewport).
    assert grid_hit(ed, 5, 1, 80, 22) == (0, 0)             # first cell of A1
    assert grid_hit(ed, 5 + 2 * 11 + 3, 4, 80, 22) == (3, 2)  # inside C4
    assert grid_hit(ed, 10, 0, 80, 22) is None              # column-header row
    assert grid_hit(ed, 4, 3, 80, 22) is None               # row-number gutter
    assert grid_hit(ed, 5 + 6 * 11, 1, 80, 22) is None      # past the last column
    ed.scroll_row, ed.scroll_col = 7, 2                     # scroll offsets apply
    assert grid_hit(ed, 5, 1, 80, 22) == (7, 2)


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
    ed.theme_name = "mono"                    # palette-free theme -> color(N) path
    text = render_grid(ed, 80, 24)
    styles = _styles(text)
    assert "reverse" in styles                # the cursor cell
    assert "color(" in styles                 # 256 fallback role colours applied


def test_galaxy_uses_truecolor_purple_surface():
    from abax.tui.textual_app import _cursor_style, _role_style

    g = THEMES["galaxy"]
    assert _role_style(g, "label") == "#a78bfa"        # violet headers (not pale)
    surf = theme_surface(g)
    assert surf["bg"] == "#1e1e2e" and surf["panel"] == "#181825"
    assert "#7c3aed" in _cursor_style(g)               # violet cursor block
    # The palette-free theme keeps the 256-index path and no truecolor surface.
    assert _role_style(THEMES["mono"], "lcd").startswith("color(")
    assert theme_surface(THEMES["mono"]) is None


_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@pytest.mark.parametrize("name", [n for n in THEMES if n != "mono"])
def test_every_palette_theme_has_truecolor_surface_and_renders(name):
    surf = theme_surface(THEMES[name])
    assert isinstance(surf, dict)
    for key in ("bg", "panel", "fg", "accent"):
        assert _HEX_RE.match(surf[key]), f"{name}.{key} = {surf.get(key)!r}"
    ed = _editor()
    ed.theme_name = name
    text = render_grid(ed, 80, 24)
    from rich.text import Text

    assert isinstance(text, Text)
    assert "10" in text.plain                  # cell values still painted
    assert " on #" in _styles(text)            # truecolor cursor block, not reverse


def test_mono_theme_has_no_truecolor_surface():
    assert theme_surface(THEMES["mono"]) is None


def test_render_grid_uses_conditional_format_colors(monkeypatch):
    import abax.core.format.condformat as cf

    # A red rule on C3 (not the A1 cursor cell) -> #ff0000 -> xterm-256 index 196.
    monkeypatch.setattr(cf, "evaluate", lambda sheet, rules: {(2, 2): "#ff0000"})
    ed = _editor()
    ed.sheet.cond_rules = ["<sentinel-rule>"]  # non-empty so _cond_colors evaluates
    text = render_grid(ed, 80, 24)
    assert "color(196)" in _styles(text)


# --- live reference highlighting while typing a formula ----------------------


def test_insert_formula_highlights_referenced_cells():
    ed = _editor()
    ed.row, ed.col = 5, 5                       # cursor away from the refs
    handle_key(ed, "i", "i")
    for ch in "=A1+B3":
        handle_key(ed, ch, ch)
    text = render_grid(ed, 80, 24)
    styles = _styles(text)
    # galaxy is truecolor: the first two ref palette backgrounds appear.
    assert "on #1f3a5f" in styles               # A1 -> colour 0 (blue tint)
    assert "on #1d4a42" in styles               # B3 -> colour 1 (teal tint)


def test_ref_highlight_only_while_editing_a_formula():
    ed = _editor()
    ed.row, ed.col = 5, 5
    text = render_grid(ed, 80, 24)              # normal mode: no ref tints
    assert "on #1f3a5f" not in _styles(text)
    handle_key(ed, "i", "i")
    for ch in "hello":                           # non-formula edit: no tints
        handle_key(ed, ch, ch)
    assert "on #1f3a5f" not in _styles(render_grid(ed, 80, 24))


def test_ref_highlight_range_clips_to_viewport():
    ed = _editor()
    ed.row, ed.col = 5, 5
    handle_key(ed, "i", "i")
    for ch in "=SUM(A1:A99999)":                 # far beyond the window
        handle_key(ed, ch, ch)
    text = render_grid(ed, 80, 24)              # must render fast and tint col A
    assert "on #1f3a5f" in _styles(text)


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


# --- mouse: click / drag-select / wheel (Pilot) ------------------------------
#
# Default Pilot terminal is 80x24; the grid widget gets 80x22 (formula bar and
# status line are docked), i.e. 21 data rows under the header and 6 columns of
# 11 cells after the 5-wide gutter. Offsets below are widget-relative.


def test_mouse_click_moves_cursor_via_pilot():
    ed = _editor()
    app = AbaxTextualApp(ed)

    async def scenario():
        async with app.run_test() as pilot:
            grid = app.query_one("#grid")
            # Line 4, third column: gutter 5 + 2 cols * 11 + 1 -> cell C4.
            await pilot.click(grid, offset=(28, 4))
            assert (ed.row, ed.col) == (3, 2)
            # Header-row and gutter clicks are safe no-ops.
            await pilot.click(grid, offset=(28, 0))
            await pilot.click(grid, offset=(2, 2))
            assert (ed.row, ed.col) == (3, 2)

    _run(scenario())


def test_mouse_drag_selects_range_via_pilot():
    ed = _editor()
    app = AbaxTextualApp(ed)

    async def scenario():
        async with app.run_test() as pilot:
            grid = app.query_one("#grid")
            await pilot.mouse_down(grid, offset=(6, 1))     # press on A1
            await pilot.hover(grid, offset=(17, 3))         # drag to B3
            await pilot.mouse_up(grid, offset=(17, 3))
            assert ed.mode == "visual"                      # still active after up
            assert ed.visual_bounds() == (0, 0, 2, 1)       # A1:B3
            assert (ed.row, ed.col) == (2, 1)               # cursor at drag end
            # 'y' then yanks exactly the dragged range (shared editor pathway).
            await pilot.press("y")
            assert ed.mode == "normal"
            assert ed.clip is not None
            assert (ed.clip.nrows, ed.clip.ncols) == (3, 2)

    _run(scenario())


def test_mouse_wheel_scrolls_without_moving_cursor():
    from textual.events import MouseScrollDown, MouseScrollUp

    ed = _editor()
    app = AbaxTextualApp(ed)

    async def scenario():
        async with app.run_test() as pilot:
            # Park the cursor mid-window so the cursor-visibility clamp lets
            # the viewport actually move (the cursor must stay on screen).
            for _ in range(10):
                await pilot.press("j")
            assert (ed.row, ed.col) == (10, 0) and ed.scroll_row == 0
            grid = app.query_one("#grid")
            grid.post_message(
                MouseScrollDown(grid, 10, 5, 0, 1, 0, False, False, False))
            await pilot.pause()
            assert ed.scroll_row == 3                       # one notch = 3 rows
            assert (ed.row, ed.col) == (10, 0)              # cursor untouched
            grid.post_message(
                MouseScrollUp(grid, 10, 5, 0, -1, 0, False, False, False))
            await pilot.pause()
            assert ed.scroll_row == 0
            assert (ed.row, ed.col) == (10, 0)

    _run(scenario())


def test_mouse_click_ignored_during_insert_edit():
    ed = _editor()
    app = AbaxTextualApp(ed)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.press("j", "j", "j", "i", "4", "2")  # editing A4
            assert ed.mode == "insert" and ed.edit_buf == "42"
            grid = app.query_one("#grid")
            await pilot.click(grid, offset=(28, 4))          # would be cell C4
            assert ed.mode == "insert" and ed.edit_buf == "42"  # buffer intact
            assert (ed.row, ed.col) == (3, 0)                # cursor never moved

    _run(scenario())
