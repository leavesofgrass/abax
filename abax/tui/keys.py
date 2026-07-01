"""Per-mode keystroke handling for the curses front-end."""

from __future__ import annotations

from .editor import TuiEditor


def _handle_key(editor: TuiEditor, ch) -> None:
    # Normalize curses key to a string where possible.
    if editor.mode == "browser":
        _handle_browser(editor, ch)
    elif editor.mode == "plot":
        _handle_plot(editor, ch)
    elif editor.mode == "rpn":
        _handle_rpn(editor, ch)
    elif editor.mode == "normal":
        if isinstance(ch, str):
            editor.message = ""
            editor.dispatch_normal(ch)
    elif editor.mode == "insert":
        _handle_insert(editor, ch)
    elif editor.mode == "command":
        _handle_command(editor, ch)


def _handle_rpn(editor: TuiEditor, ch) -> None:
    if ch in ("\n", "\r", 10, 13):
        editor.rpn_eval()
    elif ch == "\x1b":
        editor.mode = "normal"
    elif ch in ("\b", "\x7f", 8, 127):
        editor.rpn_input = editor.rpn_input[:-1]
    elif isinstance(ch, str) and ch.isprintable():
        editor.rpn_input += ch


def _handle_plot(editor: TuiEditor, ch) -> None:
    if ch == "\x1b" or ch == "q":
        editor.mode = "normal"


def _handle_browser(editor: TuiEditor, ch) -> None:
    if ch in ("\n", "\r", 10, 13):
        editor.browser_insert()
    elif ch == "\x1b" or ch == "q":
        editor.mode = "normal"
    elif ch == "j":
        editor.browser_move(1)
    elif ch == "k":
        editor.browser_move(-1)
    elif isinstance(ch, str) and ch in ("g",):
        editor.browser_idx = 0
    elif isinstance(ch, str) and ch in ("G",):
        editor.browser_idx = len(editor.browser) - 1


def _handle_insert(editor: TuiEditor, ch) -> None:
    if ch in ("\n", "\r", 10, 13):
        editor.commit_insert()
        return
    if ch in ("\t", 9):  # Tab — autocomplete the current function token
        editor.complete()
        return
    if ch == "\x1b":  # Escape
        editor.mode = "normal"
        editor.completions = []
        return
    if ch in ("\b", "\x7f", 8, 127):
        editor.edit_buf = editor.edit_buf[:-1]
    elif isinstance(ch, str) and ch.isprintable():
        editor.edit_buf += ch
    editor.refresh_completions()  # live candidate list while typing a formula


def _handle_command(editor: TuiEditor, ch) -> None:
    if ch in ("\n", "\r", 10, 13):
        editor.run_command()
    elif ch == "\x1b":
        editor.mode = "normal"
        editor.command_buf = ""
    elif ch in ("\b", "\x7f", 8, 127):
        editor.command_buf = editor.command_buf[:-1]
        if not editor.command_buf:
            editor.mode = "normal"
    elif isinstance(ch, str) and ch.isprintable():
        editor.command_buf += ch
