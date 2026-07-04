"""TUI pure logic: terminal detection, command parse, theme alloc, vim dispatch.

No real terminal is created (spec §12).
"""

from __future__ import annotations

from abax.engine.document import Document
from abax.tui import (
    THEMES,
    TuiEditor,
    can_use_powerline,
    detect_terminal,
    parse_command,
)


def test_detect_terminal_levels(monkeypatch):
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert detect_terminal(True, 256) == "256"
    monkeypatch.setenv("COLORTERM", "")
    monkeypatch.setenv("TERM", "xterm")
    assert detect_terminal(True, 8) == "8"
    assert detect_terminal(False, 0) == "mono"


def test_powerline_needs_256_and_not_ssh(monkeypatch):
    monkeypatch.delenv("SSH_CLIENT", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)
    assert can_use_powerline("256") is True
    monkeypatch.setenv("SSH_TTY", "/dev/pts/1")
    assert can_use_powerline("256") is False
    assert can_use_powerline("8") is False


def test_parse_command():
    assert parse_command(":w foo.csv") == ("w", ["foo.csv"])
    assert parse_command("q") == ("q", [])
    assert parse_command(":") == ("", [])


def test_theme_color_falls_back_to_8():
    theme = THEMES["obsidian"]
    # 256-color index vs 8-color fallback differ.
    assert theme.color("accent", "256") == 99
    assert theme.color("accent", "8") == 5


def test_vim_dispatch_navigation():
    ed = TuiEditor(Document())
    ed.dispatch_normal("j")
    ed.dispatch_normal("j")
    ed.dispatch_normal("l")
    assert ed.row == 2
    assert ed.col == 1
    ed.dispatch_normal("g")
    assert ed.row == 0


def test_arrow_keys_navigate_the_sheet():
    """Arrow keys (curses int key codes) move the cursor like h/j/k/l."""
    import curses

    from abax.tui.keys import _handle_key

    ed = TuiEditor(Document())
    ed.mode = "normal"
    _handle_key(ed, curses.KEY_DOWN)
    _handle_key(ed, curses.KEY_DOWN)
    _handle_key(ed, curses.KEY_RIGHT)
    assert (ed.row, ed.col) == (2, 1)
    _handle_key(ed, curses.KEY_UP)
    _handle_key(ed, curses.KEY_LEFT)
    assert (ed.row, ed.col) == (1, 0)
    # Ordinary vi keys still work alongside the arrows.
    ed.dispatch_normal("j")
    assert ed.row == 2


def test_vim_insert_commits_value():
    ed = TuiEditor(Document())
    ed.begin_insert()
    ed.edit_buf = "=1+2"
    ed.commit_insert()
    assert ed.mode == "normal"
    assert ed.sheet.get("A1") == 3


def test_command_quit_stops_loop():
    ed = TuiEditor(Document())
    ed.command_buf = ":q"
    ed.run_command()
    assert ed.running is False


def test_editor_records_edits_when_recording():
    ed = TuiEditor(Document())
    ed.recorder.start("t")
    ed.begin_insert()
    ed.edit_buf = "=1+2"
    ed.commit_insert()  # at A1
    ed.move(1, 0)
    ed.dispatch_normal("x")  # clear A2
    assert ed.recorder.count == 2
    assert ed.recorder.actions[0].ref == "A1"
    assert ed.recorder.actions[0].raw == "=1+2"
    assert ed.recorder.actions[1].kind == "clear"


def test_record_command_toggle_and_replay():
    ed = TuiEditor(Document())
    ed.command_buf = ":rec"  # start
    ed.run_command()
    assert ed.recorder.recording is True
    ed.begin_insert()
    ed.edit_buf = "99"
    ed.commit_insert()
    ed.command_buf = ":rec"  # stop
    ed.run_command()
    assert ed.recorder.recording is False
    assert ed.recorder.count == 1


def test_record_save_command(tmp_path):
    ed = TuiEditor(Document())
    ed.recorder.start("saved")
    ed.recorder.record_set("A1", "1")
    out = tmp_path / "rec.py"
    ed.command_buf = f":rec save {out}"
    ed.run_command()
    assert out.exists()
    assert "@macro" in out.read_text()


def test_tab_completion_single_match():
    ed = TuiEditor(Document())
    ed.begin_insert()
    ed.edit_buf = "=VLOOK"
    ed.complete()
    assert ed.edit_buf == "=VLOOKUP("


def test_tab_completion_common_prefix():
    ed = TuiEditor(Document())
    ed.begin_insert()
    ed.edit_buf = "=AVERAGEI"
    ed.complete()
    # AVERAGEIF, AVERAGEIFS -> common prefix AVERAGEIF
    assert ed.edit_buf == "=AVERAGEIF"
    assert len(ed.completions) > 1


def test_live_completions_refresh():
    ed = TuiEditor(Document())
    ed.begin_insert()
    ed.edit_buf = "=AV"
    ed.refresh_completions()
    assert "AVERAGE" in ed.completions


def test_arg_hint_tracks_parameter():
    ed = TuiEditor(Document())
    ed.begin_insert()
    ed.edit_buf = "=VLOOKUP(A1, B1:C9, "
    ed.refresh_completions()
    assert ed.completions == []  # not typing a name -> no completion list
    assert "»col_index«" in ed.arg_hint


def test_find_and_navigate():
    ed = TuiEditor(Document())
    for ref, v in [("A1", "apple"), ("A2", "apricot"), ("A3", "banana")]:
        ed.sheet.set(ref, v)
    ed.command_buf = ":find ap"
    ed.run_command()
    assert len(ed.matches) == 2
    assert (ed.row, ed.col) == (0, 0)  # jumped to first
    ed.dispatch_normal("n")
    assert (ed.row, ed.col) == (1, 0)  # apricot
    ed.dispatch_normal("N")
    assert (ed.row, ed.col) == (0, 0)


def test_substitute_command():
    ed = TuiEditor(Document())
    ed.sheet.set("A1", "color colour")
    ed.command_buf = ":s/colou?r/COLOR/"
    ed.run_command()
    assert ed.sheet.get("A1") == "COLOR COLOR"


def test_replace_command_with_regex_backref():
    ed = TuiEditor(Document())
    ed.sheet.set("A1", "a=b")
    ed.command_buf = r":replace (\w+)=(\w+) \2=\1"
    ed.run_command()
    assert ed.sheet.get("A1") == "b=a"


def test_theme_command():
    ed = TuiEditor(Document())
    ed.command_buf = ":theme nord"
    ed.run_command()
    assert ed.theme_name == "nord"
    ed.command_buf = ":theme nonsense"
    ed.run_command()
    assert ed.theme_name == "nord"  # unchanged; message lists options


def test_rpn_repl_mode_and_eval():
    ed = TuiEditor(Document())
    ed.command_buf = ":rpn"
    ed.run_command()
    assert ed.mode == "rpn"
    ed.rpn_input = "3 4 + 5 *"
    ed.rpn_eval()
    assert ed.rpn.x == 35.0


def test_rpn_cell_interop():
    ed = TuiEditor(Document())
    ed.sheet.set("A1", "42")
    ed.row, ed.col = 0, 0
    ed.command_buf = ":rpn"
    ed.run_command()
    ed.rpn_input = "<"  # pull cell value
    ed.rpn_eval()
    assert ed.rpn.x == 42.0
    ed.rpn_input = "sqrt"
    ed.rpn_eval()
    ed.row, ed.col = 0, 1
    ed.rpn_input = ">"  # store X to B1
    ed.rpn_eval()
    assert abs(ed.sheet.get("B1") - 42 ** 0.5) < 1e-6


def test_rpn_oneshot_command():
    ed = TuiEditor(Document())
    ed.command_buf = ":rpn 2 3 +"
    ed.run_command()
    assert ed.mode == "normal"  # one-shot, not REPL
    assert ed.rpn.x == 5.0


def test_shell_passthrough_command():
    import sys

    ed = TuiEditor(Document())
    ed.command_buf = f':!{sys.executable} -c "print(6*7)"'
    ed.run_command()
    assert "42" in ed.message
    assert ed.mode == "normal"


def test_convert_command():
    ed = TuiEditor(Document())
    ed.command_buf = ":convert 100 C F"
    ed.run_command()
    assert "212" in ed.message
    ed.command_buf = ":convert 1 m kg"  # cross-category
    ed.run_command()
    assert "convert:" in ed.message


def test_fmt_command():
    ed = TuiEditor(Document())
    ed.sheet.set("A1", "0.25")
    ed.command_buf = ":fmt percent A1"
    ed.run_command()
    assert ed.sheet.cell_formats[(0, 0)] == "percent"
    assert ed.sheet.display(0, 0) == "25%"


def test_plot_command_enters_plot_mode():
    ed = TuiEditor(Document())
    ed.command_buf = ":plot sin(x) -3 3"
    ed.run_command()
    assert ed.mode == "plot"
    assert ed.plot_expr == "sin(x)"
    assert len(ed.plot_pts) > 0


def test_eq_command_unicode():
    ed = TuiEditor(Document())
    ed.command_buf = ":eq x^2"
    ed.run_command()
    assert "x²" in ed.message


def test_py_command_scripts_the_sheet():
    ed = TuiEditor(Document())
    ed.command_buf = ":py put('A1', sum(range(11)))"
    ed.run_command()
    assert ed.sheet.get("A1") == 55
    ed.command_buf = ":py cell('A1') * 2"
    ed.run_command()
    assert "110" in ed.message


def test_clipboard_history_commands():
    ed = TuiEditor(Document())
    ed.sheet.set("A1", "hello")
    ed.row, ed.col = 0, 0
    ed.dispatch_normal("y")  # yank -> adds to history
    assert len(ed.clips.entries()) == 1
    ed.row, ed.col = 2, 0
    ed.command_buf = ":clip 0"  # paste history entry 0 at A3
    ed.run_command()
    assert ed.sheet.get("A3") == "hello"


def test_hex_to_ansi_helpers():
    from abax.tui import _hex_to_8, _hex_to_256

    assert _hex_to_256("#000000") == 16
    assert _hex_to_256("#ffffff") == 231
    assert 16 <= _hex_to_256("#ff0000") <= 231
    assert _hex_to_8("#ff0000") == 1   # red
    assert _hex_to_8("#00ff00") == 2   # green
    assert _hex_to_8("#ffff00") == 3   # yellow
    assert _hex_to_8("#000000") == 0


def test_new_themes_present():
    from abax.tui import THEMES

    for name in ("solarized", "nord", "dark_one", "crt_green", "crt_amber"):
        assert name in THEMES


def test_function_browser_mode():
    ed = TuiEditor(Document())
    ed.command_buf = ":func VLOOK"
    ed.run_command()
    assert ed.mode == "browser"
    assert ed.browser == ["VLOOKUP"]
    ed.browser_insert()
    assert ed.mode == "insert"
    assert ed.edit_buf == "=VLOOKUP("


def test_undo_restores_cleared_cell():
    ed = TuiEditor(Document())
    ed.sheet.set("A1", "hello")
    ed.row, ed.col = 0, 0
    ed.dispatch_normal("x")  # clear A1 (checkpoints first)
    assert ed.sheet.get("A1") in (None, "")
    ed.dispatch_normal("u")  # undo
    assert ed.sheet.get("A1") == "hello"
    assert ed.message == "undone"


def test_redo_reapplies_change():
    ed = TuiEditor(Document())
    ed.sheet.set("A1", "hello")
    ed.dispatch_normal("x")   # clear
    ed.dispatch_normal("u")   # undo -> restored
    assert ed.sheet.get("A1") == "hello"
    ed.dispatch_normal("\x12")  # Ctrl-R redo -> cleared again
    assert ed.sheet.get("A1") in (None, "")
    assert ed.message == "redone"


def test_undo_command_and_nothing_to_undo():
    ed = TuiEditor(Document())
    ed.command_buf = ":undo"
    ed.run_command()
    assert ed.message == "nothing to undo"
    ed.begin_insert()
    ed.edit_buf = "=1+1"
    ed.commit_insert()  # A1 = 2, checkpointed
    ed.command_buf = ":undo"
    ed.run_command()
    assert ed.sheet.get("A1") in (None, "")
    ed.command_buf = ":redo"
    ed.run_command()
    assert ed.sheet.get("A1") == 2


def test_help_command_enters_help_mode():
    ed = TuiEditor(Document())
    ed.command_buf = ":help"
    ed.run_command()
    assert ed.mode == "help"


def test_help_key_enters_and_lists_commands():
    from abax.tui.editor import HELP_ENTRIES

    ed = TuiEditor(Document())
    ed.dispatch_normal("?")
    assert ed.mode == "help"
    # every normal-mode key + ':' command is represented
    keys = " ".join(k for k, _ in HELP_ENTRIES)
    assert ":help" in keys
    assert ":plot" in keys
    assert "u" in keys
    assert "?" in keys


def test_help_mode_scroll_and_exit():
    from abax.tui.keys import _handle_key

    ed = TuiEditor(Document())
    ed.dispatch_normal("?")
    _handle_key(ed, "j")
    assert ed.help_idx == 1
    _handle_key(ed, "G")  # jump to bottom (clamped)
    from abax.tui.editor import HELP_ENTRIES

    assert ed.help_idx == len(HELP_ENTRIES) - 1
    _handle_key(ed, "q")  # exit
    assert ed.mode == "normal"


def test_plot_range_single_column():
    ed = TuiEditor(Document())
    for i, v in enumerate([1, 4, 9], start=1):
        ed.sheet.set(f"A{i}", str(v))
    ed.command_buf = ":plot A1:A3"
    ed.run_command()
    assert ed.mode == "plot"
    assert ed.plot_bounds is not None
    # bounds y-range covers the data
    _, _, ymin, ymax = ed.plot_bounds
    assert ymin == 1.0 and ymax == 9.0
    from abax.core.graphing import braille_plot

    out = braille_plot(ed.plot_pts, width=20, height=6,
                       xmin=ed.plot_bounds[0], xmax=ed.plot_bounds[1],
                       ymin=ymin, ymax=ymax)
    assert isinstance(out, str) and out


def test_plot_range_xy_pairs():
    ed = TuiEditor(Document())
    for i, (x, y) in enumerate([(0, 0), (1, 2), (2, 4)], start=1):
        ed.sheet.set(f"A{i}", str(x))
        ed.sheet.set(f"B{i}", str(y))
    ed.command_buf = ":plot A1:A3 B1:B3"
    ed.run_command()
    assert ed.mode == "plot"
    assert ed.plot_pts == [(0.0, 0.0), (1.0, 2.0), (2.0, 4.0)]


def test_plot_expression_still_works():
    ed = TuiEditor(Document())
    ed.command_buf = ":plot sin(x) -3 3"
    ed.run_command()
    assert ed.mode == "plot"
    assert ed.plot_expr == "sin(x)"
    assert ed.plot_bounds is None  # expression form uses auto-ranging


def test_visual_mode_enter_and_extend():
    """`v` enters visual mode; h/j/k/l extend the selection from the anchor."""
    ed = TuiEditor(Document())
    ed.row, ed.col = 1, 1  # start at B2
    ed.dispatch_normal("v")
    assert ed.mode == "visual"
    assert (ed.anchor_row, ed.anchor_col) == (1, 1)
    ed.dispatch_normal("j")  # cursor -> B3 (below)
    ed.dispatch_normal("l")  # cursor -> C3
    assert ed.visual_bounds() == (1, 1, 2, 2)  # B2:C3, normalized


def test_visual_mode_extends_upward_and_left():
    """Selecting toward the origin still yields a normalized (r1<=r2) range."""
    ed = TuiEditor(Document())
    ed.row, ed.col = 2, 2  # C3
    ed.dispatch_normal("v")
    ed.dispatch_normal("k")  # C2
    ed.dispatch_normal("h")  # B2
    assert ed.visual_bounds() == (1, 1, 2, 2)  # anchor C3, cursor B2 -> B2:C3


def test_visual_line_mode_spans_full_width():
    """`V` selects whole rows across the used column width."""
    ed = TuiEditor(Document())
    ed.sheet.set("A1", "1")
    ed.sheet.set("C1", "3")  # widen used bounds to column C (index 2)
    ed.row, ed.col = 0, 0
    ed.dispatch_normal("V")
    assert ed.mode == "visual-line"
    ed.dispatch_normal("j")  # extend to row 2
    r1, c1, r2, c2 = ed.visual_bounds()
    assert (r1, r2) == (0, 1)
    assert (c1, c2) == (0, 2)  # whole width A..C


def test_visual_aggregate_in_status_line():
    """Sum / count / average of the numeric cells appear while in visual mode."""
    from abax.tui.keys import _handle_key

    ed = TuiEditor(Document())
    for ref, v in [("A1", "10"), ("A2", "20"), ("A3", "hello")]:
        ed.sheet.set(ref, v)
    ed.row, ed.col = 0, 0
    ed.dispatch_normal("v")
    _handle_key(ed, "j")
    _handle_key(ed, "j")  # A1:A3 — status line refreshes as the selection grows
    total, count, avg = ed.visual_aggregate()
    assert total == 30.0
    assert count == 2  # the text cell is not counted
    assert avg == 15.0
    assert "sum=30" in ed.message
    assert "count=2" in ed.message
    assert "avg=15" in ed.message


def test_visual_yank_copies_range_and_exits():
    """`y` copies the selected range to the clipboard/registers and leaves visual."""
    from abax.tui.keys import _handle_key

    ed = TuiEditor(Document())
    for ref, v in [("A1", "1"), ("B1", "2"), ("A2", "3"), ("B2", "4")]:
        ed.sheet.set(ref, v)
    ed.row, ed.col = 0, 0
    ed.dispatch_normal("v")
    ed.dispatch_normal("l")
    ed.dispatch_normal("j")  # A1:B2
    _handle_key(ed, "y")
    assert ed.mode == "normal"
    assert ed.clip is not None
    assert ed.clip.nrows == 2 and ed.clip.ncols == 2
    assert len(ed.clips.entries()) == 1
    # The yanked clip pastes back verbatim elsewhere.
    from abax.core.fill import paste_clip

    paste_clip(ed.sheet, ed.clip, "D1", mode="absolute")
    assert ed.sheet.get("D1") == 1
    assert ed.sheet.get("E2") == 4


def test_visual_delete_clears_with_undo():
    """`d` clears the selection under an undo checkpoint; undo restores it."""
    from abax.tui.keys import _handle_key

    ed = TuiEditor(Document())
    for ref, v in [("A1", "1"), ("B1", "2"), ("A2", "3"), ("B2", "4")]:
        ed.sheet.set(ref, v)
    ed.row, ed.col = 0, 0
    ed.dispatch_normal("v")
    ed.dispatch_normal("l")
    ed.dispatch_normal("j")  # A1:B2
    _handle_key(ed, "d")
    assert ed.mode == "normal"
    assert ed.sheet.get_raw(0, 0) == ""
    assert ed.sheet.get_raw(1, 1) == ""
    assert ed.doc.can_undo
    ed.doc.undo()
    assert ed.sheet.get("A1") == 1
    assert ed.sheet.get("B2") == 4


def test_visual_delete_via_x_records_clears():
    """`x` in visual mode also clears the range and records the clears."""
    from abax.tui.keys import _handle_key

    ed = TuiEditor(Document())
    ed.sheet.set("A1", "1")
    ed.sheet.set("A2", "2")
    ed.recorder.start("t")
    ed.row, ed.col = 0, 0
    ed.dispatch_normal("v")
    ed.dispatch_normal("j")  # A1:A2
    _handle_key(ed, "x")
    assert ed.sheet.get_raw(0, 0) == ""
    assert ed.sheet.get_raw(1, 0) == ""
    assert ed.recorder.count == 2  # one clear per non-empty cell
    assert all(a.kind == "clear" for a in ed.recorder.actions)


def test_visual_escape_cancels_selection():
    """Esc leaves visual mode without mutating the sheet."""
    from abax.tui.keys import _handle_key

    ed = TuiEditor(Document())
    ed.sheet.set("A1", "keep")
    ed.row, ed.col = 0, 0
    ed.dispatch_normal("v")
    ed.dispatch_normal("j")
    _handle_key(ed, "\x1b")
    assert ed.mode == "normal"
    assert ed.sheet.get("A1") == "keep"
    assert ed.message == ""


def test_visual_movement_via_arrow_keys():
    """Arrow keys extend the visual selection exactly like h/j/k/l."""
    import curses

    from abax.tui.keys import _handle_key

    ed = TuiEditor(Document())
    ed.row, ed.col = 0, 0
    ed.dispatch_normal("v")
    _handle_key(ed, curses.KEY_DOWN)
    _handle_key(ed, curses.KEY_RIGHT)
    assert ed.visual_bounds() == (0, 0, 1, 1)  # A1:B2


def test_relative_record_and_replay_at_cursor():
    ed = TuiEditor(Document())
    # start relative recording at B2
    ed.row, ed.col = 1, 1
    ed.command_buf = ":rec rel"
    ed.run_command()
    assert ed.recorder.relative is True
    ed.begin_insert()
    ed.edit_buf = "=A1*2"  # at B2, ref A1 is up-left
    ed.commit_insert()
    ed.command_buf = ":rec stop"
    ed.run_command()

    # move cursor to D4 and replay
    ed.row, ed.col = 3, 3
    ed.command_buf = ":rec replay"
    ed.run_command()
    # B2 "=A1*2" -> D4 "=C3*2"
    assert ed.sheet.get_raw(3, 3) == "=C3*2"


# --- (1) stable viewport with scroll offset ------------------------------

def test_viewport_geometry_helpers():
    """Renderer/reclamp share one grid-size formula (header+bar+status+hint chrome)."""
    from abax.tui.render import visible_cols, visible_rows

    assert visible_rows(24) == 20   # 24 - 4 lines of chrome
    assert visible_rows(4) == 1     # never below one row
    assert visible_rows(1) == 1
    # col gutter is 5 wide; each column is col_w + 1.
    assert visible_cols(60, col_w=10) == 5   # (60 - 5) // 11
    assert visible_cols(6, col_w=10) == 1     # clamps to at least one column


def test_reclamp_noop_without_viewport():
    """With no reported viewport (headless, pre-first-frame) the scroll stays put."""
    ed = TuiEditor(Document())
    ed.move(50, 30)
    assert (ed.row, ed.col) == (50, 30)
    assert (ed.scroll_row, ed.scroll_col) == (0, 0)  # unknown viewport => no scroll


def test_reclamp_scrolls_to_follow_cursor_down_and_right():
    ed = TuiEditor(Document())
    ed.viewport_rows, ed.viewport_cols = 10, 4
    ed.move(9, 3)  # last visible cell — still no scroll needed
    assert (ed.scroll_row, ed.scroll_col) == (0, 0)
    ed.move(1, 1)  # steps just past the bottom-right corner
    assert ed.row == 10 and ed.col == 4
    assert ed.scroll_row == 1   # window shifts down by exactly one
    assert ed.scroll_col == 1   # and right by one
    # A big jump keeps the cursor on the last visible line.
    ed.row = 100
    ed._reclamp()
    assert ed.scroll_row == 100 - 10 + 1


def test_reclamp_scrolls_back_up_when_cursor_leaves_top():
    ed = TuiEditor(Document())
    ed.viewport_rows, ed.viewport_cols = 5, 3
    ed.row, ed.col = 20, 10
    ed._reclamp()
    assert ed.scroll_row == 16 and ed.scroll_col == 8
    # Move above the window: it scrolls up so the cursor sits on the top line.
    ed.row = 4
    ed._reclamp()
    assert ed.scroll_row == 4
    ed.col = 0
    ed._reclamp()
    assert ed.scroll_col == 0


def test_reclamp_on_goto_top_and_bottom():
    ed = TuiEditor(Document())
    ed.viewport_rows, ed.viewport_cols = 5, 5
    ed.sheet.set("A200", "x")  # extend used bounds far down
    ed.dispatch_normal("G")    # jump to the last used row
    assert ed.row == 199
    assert ed.scroll_row == 199 - 5 + 1  # window followed the cursor down
    ed.dispatch_normal("g")    # back to the top
    assert ed.row == 0
    assert ed.scroll_row == 0


def test_reclamp_on_find_navigation():
    ed = TuiEditor(Document())
    ed.viewport_rows, ed.viewport_cols = 5, 5
    ed.sheet.set("A50", "needle")
    ed.command_buf = ":find needle"
    ed.run_command()
    assert (ed.row, ed.col) == (49, 0)
    assert ed.scroll_row == 49 - 5 + 1  # jumped-to match is visible


def test_render_draws_scrolled_window(monkeypatch):
    """The draw loop reports the viewport and paints the scrolled cell range."""
    from abax.tui import render as render_mod

    ed = TuiEditor(Document())
    ed.sheet.set("A1", "top")
    ed.sheet.set("A40", "far")
    ed.row, ed.col = 39, 0  # cursor well below the first screen

    painted: dict[tuple[int, int], str] = {}

    class FakeScr:
        def getmaxyx(self):
            return 24, 80

        def addstr(self, y, x, text, attr_val):
            painted[(y, x)] = text

    fake = FakeScr()

    class FakeCurses:
        A_REVERSE = 0
        A_BOLD = 0
        A_NORMAL = 0

        def color_pair(self, n):
            return 0

    # The draw loop reports the viewport + reclamps before each paint; do the
    # same here so the render reflects the scrolled window.
    ed.viewport_rows = render_mod.visible_rows(24)
    ed.viewport_cols = render_mod.visible_cols(80)
    ed._reclamp()
    assert ed.scroll_row == 39 - ed.viewport_rows + 1
    render_mod._render(fake, FakeCurses(), ed, lambda role: 0, "mono", {},
                       lambda hexc: None)
    # Formula bar (row 0) shows the active cell's ref + raw content.
    assert painted[(0, 0)].strip().startswith("A40")
    assert "far" in painted[(0, 0)]
    # Row label 2 (screen row 2, the first data line) shows the scrolled top row,
    # not row 1 — proving the window is offset.
    top_label = painted[(2, 0)].strip()
    assert top_label == str(ed.scroll_row + 1)


# --- (2) persistent formula bar ------------------------------------------

def test_formula_bar_shows_ref_and_raw():
    ed = TuiEditor(Document())
    ed.sheet.set("B2", "=1+2")
    ed.row, ed.col = 1, 1
    assert ed.formula_bar_text() == "B2  =1+2"
    ed.row, ed.col = 0, 0  # empty cell -> ref then nothing
    assert ed.formula_bar_text() == "A1  "


# --- (3) sheet switching --------------------------------------------------

def _wb_with_sheets(ed, *names):
    for n in names:
        ed.doc.workbook.add_sheet(n)


def test_switch_sheet_changes_active_and_reclamps():
    ed = TuiEditor(Document())
    _wb_with_sheets(ed, "Data")
    ed.viewport_rows, ed.viewport_cols = 5, 5
    ed.row = 40  # far down on Sheet1
    ed._reclamp()
    assert ed.scroll_row > 0
    ok = ed.switch_sheet(1)  # -> "Data" (used bounds empty)
    assert ok is True
    assert ed.doc.workbook.active == 1
    assert ed.sheet.name == "Data"
    # cursor kept, but reclamp ran (scroll re-derived from the new viewport)
    assert ed.scroll_row == 40 - 5 + 1


def test_switch_sheet_out_of_range_is_rejected():
    ed = TuiEditor(Document())
    assert ed.switch_sheet(3) is False
    assert ed.doc.workbook.active == 0
    assert "no sheet" in ed.message


def test_next_prev_sheet_wraps():
    ed = TuiEditor(Document())
    _wb_with_sheets(ed, "Two", "Three")
    assert ed.doc.workbook.active == 0
    ed.next_sheet(1)
    assert ed.doc.workbook.active == 1
    ed.next_sheet(1)
    assert ed.doc.workbook.active == 2
    ed.next_sheet(1)          # wraps back to the first
    assert ed.doc.workbook.active == 0
    ed.next_sheet(-1)         # wraps to the last
    assert ed.doc.workbook.active == 2


def test_gt_gT_switch_sheets_via_keys():
    from abax.tui.keys import _handle_key

    ed = TuiEditor(Document())
    _wb_with_sheets(ed, "B", "C")
    _handle_key(ed, "g")
    assert ed.pending_g is True   # first 'g' held pending
    _handle_key(ed, "t")          # 'gt' -> next sheet
    assert ed.pending_g is False
    assert ed.doc.workbook.active == 1
    _handle_key(ed, "g")
    _handle_key(ed, "T")          # 'gT' -> previous sheet
    assert ed.doc.workbook.active == 0


def test_bare_g_still_jumps_to_top_via_keys():
    """A 'g' not followed by t/T behaves as the plain jump-to-top motion."""
    from abax.tui.keys import _handle_key

    ed = TuiEditor(Document())
    ed.row = 12
    _handle_key(ed, "g")   # pending
    _handle_key(ed, "j")   # 'gj' -> g (top) then j (down one)
    assert ed.pending_g is False
    assert ed.row == 1     # jumped to 0, then j moved down to 1


def test_gg_jumps_to_top_via_keys():
    from abax.tui.keys import _handle_key

    ed = TuiEditor(Document())
    ed.row = 30
    _handle_key(ed, "g")
    _handle_key(ed, "g")   # 'gg'
    assert ed.row == 0
    assert ed.pending_g is False


def test_sheet_command_by_index_and_name():
    ed = TuiEditor(Document())
    _wb_with_sheets(ed, "Data", "Notes")
    ed.command_buf = ":sheet 2"   # 1-based index -> "Data"
    ed.run_command()
    assert ed.sheet.name == "Data"
    ed.command_buf = ":sheet Notes"
    ed.run_command()
    assert ed.sheet.name == "Notes"
    ed.command_buf = ":sheet Missing"
    ed.run_command()
    assert ed.sheet.name == "Notes"  # unchanged
    assert "no sheet named" in ed.message


def test_sheets_command_lists_and_marks_active():
    ed = TuiEditor(Document())
    _wb_with_sheets(ed, "Data")
    ed.doc.workbook.active = 1
    ed.command_buf = ":sheets"
    ed.run_command()
    assert "*2:Data" in ed.message
    assert "1:Sheet1" in ed.message


def test_sheet_switch_pushes_no_undo_checkpoint():
    ed = TuiEditor(Document())
    _wb_with_sheets(ed, "Data")
    # make one real edit so there IS undo history to compare against
    ed.begin_insert()
    ed.edit_buf = "=1"
    ed.commit_insert()
    undo_before, _ = ed.doc.undo_history()
    ed.switch_sheet(1)
    ed.switch_sheet(0)
    ed.next_sheet(1)
    undo_after, _ = ed.doc.undo_history()
    assert undo_after == undo_before  # navigation added no checkpoints


def test_switch_sheet_shows_the_other_sheets_cells():
    """Regression: multi-tab workbooks were invisible; switching reveals them."""
    ed = TuiEditor(Document())
    ed.sheet.set("A1", "on-first")
    data = ed.doc.workbook.add_sheet("Data")
    data.set("A1", "on-second")
    assert ed.formula_bar_text() == "A1  on-first"
    ed.goto_sheet("Data")
    assert ed.sheet.display(0, 0) == "on-second"
    assert ed.formula_bar_text() == "A1  on-second"
