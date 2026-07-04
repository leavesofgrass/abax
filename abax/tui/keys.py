"""Per-mode keystroke handling for the curses front-end."""

from __future__ import annotations

from .editor import TuiEditor

_ARROW_TO_VI: "dict[int, str] | None" = None


def _arrow_vi(ch) -> "str | None":
    """Map a curses arrow key code to the equivalent vi navigation char.

    ``curses``' ``get_wch()`` returns special keys (arrows, page-up, …) as
    *ints*, not strings. Translate the four arrows to ``h``/``j``/``k``/``l`` so
    they drive the same sheet/list navigation as the vi keys. Returns None for
    anything that isn't an arrow (including ordinary string keystrokes)."""
    global _ARROW_TO_VI
    if isinstance(ch, str):
        return None
    if _ARROW_TO_VI is None:
        try:
            import curses

            _ARROW_TO_VI = {curses.KEY_LEFT: "h", curses.KEY_DOWN: "j",
                            curses.KEY_UP: "k", curses.KEY_RIGHT: "l"}
        except Exception:
            _ARROW_TO_VI = {}
    return _ARROW_TO_VI.get(ch)


def _handle_key(editor: TuiEditor, ch) -> None:
    # Normalize curses key to a string where possible.
    if editor.mode == "browser":
        _handle_browser(editor, ch)
    elif editor.mode == "help":
        _handle_help(editor, ch)
    elif editor.mode == "describe":
        _handle_describe(editor, ch)
    elif editor.mode == "plot":
        _handle_plot(editor, ch)
    elif editor.mode == "rpn":
        _handle_rpn(editor, ch)
    elif editor.mode == "normal":
        _handle_normal(editor, ch)
    elif editor.mode in ("visual", "visual-line"):
        _handle_visual(editor, ch)
    elif editor.mode == "insert":
        _handle_insert(editor, ch)
    elif editor.mode == "command":
        _handle_command(editor, ch)


def _handle_normal(editor: TuiEditor, ch) -> None:
    """Normal-mode dispatch, incl. the ``g``-prefixed two-key sheet motions.

    Arrow keys navigate the sheet exactly like the vi keys h/j/k/l. A bare ``g``
    is held pending one keystroke: ``gt``/``gT`` switch sheets; ``gg`` (or any
    other ``g<x>``) falls back to the plain ``g`` jump-to-top, then processes the
    trailing key. Driving :meth:`TuiEditor.dispatch_normal` directly (as the unit
    tests do) keeps the simpler single-key ``g`` = jump-to-top behaviour."""
    key = ch if isinstance(ch, str) else _arrow_vi(ch)
    if key is None:
        return
    if editor.pending_g:  # resolve a previously-pressed 'g'
        editor.pending_g = False
        if key == "t":
            editor.message = ""
            editor.next_sheet(1)
            return
        if key == "T":
            editor.message = ""
            editor.next_sheet(-1)
            return
        # Not a sheet motion: honour the first 'g' (jump to top), then fall
        # through so the trailing key is handled as usual.
        editor.message = ""
        editor.dispatch_normal("g")
        if key == "g":  # 'gg' — already at top; nothing more to do
            return
    if key == "g":
        editor.pending_g = True
        return
    editor.message = ""
    editor.dispatch_normal(key)


def _handle_visual(editor: TuiEditor, ch) -> None:
    # Movement (h/j/k/l AND arrow keys) extends the selection from the anchor;
    # the cursor moves while the anchor stays put. Operations act on the range.
    key = ch if isinstance(ch, str) else _arrow_vi(ch)
    if key in ("h", "j", "k", "l"):
        editor.move(*{"h": (0, -1), "l": (0, 1),
                      "j": (1, 0), "k": (-1, 0)}[key])
        editor.visual_refresh()
    elif key == "\x1b" or key == "v":  # Esc / v cancels
        editor.cancel_visual()
    elif key == "y":  # yank the selection
        editor.visual_yank()
    elif key in ("d", "x"):  # delete/clear the selection (undo checkpoint)
        editor.visual_delete()


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
    ch = _arrow_vi(ch) or ch   # arrows move the list like j/k (h/l are no-ops here)
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


def _handle_help(editor: TuiEditor, ch) -> None:
    ch = _arrow_vi(ch) or ch   # arrows scroll the list like j/k
    if ch == "\x1b" or ch == "q":
        editor.mode = "normal"
    elif ch == "j":
        editor.help_move(1)
    elif ch == "k":
        editor.help_move(-1)
    elif isinstance(ch, str) and ch == "g":
        editor.help_idx = 0
    elif isinstance(ch, str) and ch == "G":
        editor.help_move(1 << 30)  # clamps to the last entry


def _handle_describe(editor: TuiEditor, ch) -> None:
    ch = _arrow_vi(ch) or ch   # arrows scroll the panel like j/k
    if ch == "\x1b" or ch == "q":
        editor.mode = "normal"
    elif ch == "j":
        editor.describe_move(1)
    elif ch == "k":
        editor.describe_move(-1)
    elif isinstance(ch, str) and ch == "g":
        editor.describe_idx = 0
    elif isinstance(ch, str) and ch == "G":
        editor.describe_move(1 << 30)  # clamps to the last row


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
