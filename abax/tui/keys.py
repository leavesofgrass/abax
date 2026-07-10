"""Per-mode keystroke handling for the curses front-end."""

from __future__ import annotations

from .editor import TuiEditor

_ARROW_TO_VI: "dict[int, str] | None" = None

# Every code a Backspace can arrive as. Over SSH with keypad mode on (curses
# default), the key is translated to curses.KEY_BACKSPACE (263) — NOT the raw
# 0x7f/0x08 — which is why deleting a mistake "did nothing" from a PowerShell →
# Debian SSH session. We accept them all: 0x08 (^H), 0x7f (DEL), and 263.
_BACKSPACE = {"\b", "\x7f", 8, 127, 263}


def _is_enter(ch) -> bool:
    return ch in ("\n", "\r", 10, 13, 343)   # 343 = curses.KEY_ENTER (keypad Enter)


def _is_backspace(ch) -> bool:
    return ch in _BACKSPACE


# Page / Home / End → editor navigation methods. Like backspace, curses (with
# keypad mode) delivers these as KEY_* ints over SSH, not raw ANSI (\x1b[5~ …).
_NAV_METHODS: "dict[int, str] | None" = None


def _nav_method(ch) -> "str | None":
    global _NAV_METHODS
    if isinstance(ch, str):
        return None
    if _NAV_METHODS is None:
        try:
            import curses

            _NAV_METHODS = {
                curses.KEY_NPAGE: "page_down", curses.KEY_PPAGE: "page_up",
                curses.KEY_HOME: "line_home", curses.KEY_END: "line_end",
            }
        except Exception:
            _NAV_METHODS = {}
    return _NAV_METHODS.get(ch)


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


def _user_binding(editor: TuiEditor, mode: str, key) -> bool:
    """Fire a user init.py rebind for (mode, key); True if it handled the key.

    Rebinds win over built-ins; an unbound key returns False so it falls through
    to the default handler. Only string keys are looked up (raw curses ints have
    no user-facing spelling). Errors can't crash the loop — the draw loop
    contains them.
    """
    if not isinstance(key, str):
        return False
    uc = getattr(editor, "user_config", None)
    if uc is None:
        return False
    binding = uc.keybinding(mode, key)
    if binding is None:
        return False
    editor.message = ""
    binding.action(editor)
    return True


def _handle_normal(editor: TuiEditor, ch) -> None:
    """Normal-mode dispatch, incl. the ``g``-prefixed two-key sheet motions.

    Arrow keys navigate the sheet exactly like the vi keys h/j/k/l. A bare ``g``
    is held pending one keystroke: ``gt``/``gT`` switch sheets; ``gg`` (or any
    other ``g<x>``) falls back to the plain ``g`` jump-to-top, then processes the
    trailing key. Driving :meth:`TuiEditor.dispatch_normal` directly (as the unit
    tests do) keeps the simpler single-key ``g`` = jump-to-top behaviour."""
    # Excel-style: Enter starts editing the current cell (in addition to the vim
    # i/a keys), so you never get stranded unable to edit. Escape then cancels,
    # Enter commits and steps down.
    if _is_enter(ch):
        editor.message = ""
        editor.begin_insert()
        return
    nav = _nav_method(ch)          # PageUp/PageDown/Home/End
    if nav is not None:
        editor.message = ""
        getattr(editor, nav)()
        return
    key = ch if isinstance(ch, str) else _arrow_vi(ch)
    if key is None:
        return
    # User rebinds from ~/.config/abax/init.py win over built-ins.
    if _user_binding(editor, "normal", key):
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
    if _user_binding(editor, "visual", key):
        return
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
    if isinstance(ch, str) and _user_binding(editor, "rpn", ch):
        return
    if _is_enter(ch):
        editor.rpn_eval()
    elif ch == "\x1b":
        editor.mode = "normal"
    elif _is_backspace(ch):
        editor.rpn_input = editor.rpn_input[:-1]
    elif isinstance(ch, str) and ch.isprintable():
        editor.rpn_input += ch


def _handle_plot(editor: TuiEditor, ch) -> None:
    if ch == "\x1b" or ch == "q":
        editor.mode = "normal"


def _handle_browser(editor: TuiEditor, ch) -> None:
    ch = _arrow_vi(ch) or ch   # arrows move the list like j/k (h/l are no-ops here)
    if isinstance(ch, str) and _user_binding(editor, "browser", ch):
        return
    if _is_enter(ch):
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
    # A bound chord (e.g. ctrl+w) fires; unbound printables still type normally.
    if isinstance(ch, str) and not ch.isprintable() and _user_binding(editor, "insert", ch):
        return
    if _is_enter(ch):
        # Excel-style: commit the value and drop to the cell below, ready for
        # the next entry. (Esc cancels the edit; Tab autocompletes.)
        editor.commit_insert(advance=True)
        return
    if ch in ("\t", 9):  # Tab — autocomplete the current function token
        editor.complete()
        return
    if ch == "\x1b":  # Escape — cancel the edit (Excel/vim: revert, keep old value)
        editor.cancel_insert()
        return
    if _is_backspace(ch):
        editor.edit_buf = editor.edit_buf[:-1]
    elif isinstance(ch, str) and ch.isprintable():
        editor.edit_buf += ch
    editor.refresh_completions()  # live candidate list while typing a formula


def _handle_command(editor: TuiEditor, ch) -> None:
    if isinstance(ch, str) and not ch.isprintable() and _user_binding(editor, "command", ch):
        return
    if _is_enter(ch):
        editor.run_command()
    elif ch == "\x1b":
        editor.mode = "normal"
        editor.command_buf = ""
    elif _is_backspace(ch):
        editor.command_buf = editor.command_buf[:-1]
        if not editor.command_buf:
            editor.mode = "normal"
    elif isinstance(ch, str) and ch.isprintable():
        editor.command_buf += ch
