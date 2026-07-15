"""Textual front-end — a richer TUI over the same :class:`TuiEditor` brain.

The curses front-end (:mod:`~abax.tui.render` / :mod:`~abax.tui.app`) and this
Textual one are two *views* over one state machine: :class:`~abax.tui.editor.TuiEditor`
owns every bit of logic (modes, cursor, the ``:`` command set, undo/redo,
completions, ``:tasks``/``:critpath``, accessibility). This module only paints the
editor's state and routes Textual key events into the editor's methods — the
same contract ``render.py`` + ``keys.py`` implement for curses.

Textual needs a capable terminal (real TTY, not the 8-colour/mono SSH degrade the
curses view targets), so the CLI prefers this when the terminal supports it and
falls back to curses otherwise (or with ``--curses``). See :func:`run_textual_tui`.

The grid painter, status line, and key dispatch are module-level pure functions so
they can be unit-tested against an editor without spinning up a live terminal; the
:class:`AbaxTextualApp` is a thin shell that wires them to Textual's event loop.
"""

from __future__ import annotations

# Grid geometry — one header row inside the grid widget; the formula bar and
# status line are separate docked widgets (unlike curses, which counts them here).
_COL_W = 10
_GUTTER = 5


def grid_viewport(width: int, height: int) -> "tuple[int, int]":
    """Data (rows, cols) that fit a grid widget ``width`` x ``height`` cells.

    One row is the column header; each data column is ``_COL_W`` + 1 separator,
    after a ``_GUTTER``-wide row-number gutter. Mirrors the curses
    ``visible_rows``/``visible_cols`` so the two views scroll identically.
    """
    rows = max(1, height - 1)
    cols = max(1, (width - _GUTTER) // (_COL_W + 1))
    return rows, cols


def _role_style(theme, role: str) -> str:
    """A Rich style for a theme role — the theme's xterm-256 index as ``color(N)``
    (Rich understands the 256-palette form directly, so the TUI themes map over
    with no new colour tables)."""
    return f"color({theme.color(role, '256')})"


def _cond_colors(sheet) -> dict:
    """``{(row, col): '#rrggbb'}`` from the sheet's conditional-format rules, or
    ``{}`` — evaluation is guarded exactly like the curses draw loop so a bad rule
    can never break the paint."""
    if not getattr(sheet, "cond_rules", None):
        return {}
    try:
        from ..core.format.condformat import evaluate
        return evaluate(sheet, sheet.cond_rules)
    except Exception:
        return {}


def render_grid(editor, width: int, height: int):
    """Build the grid body (header + data rows) as a Rich ``Text`` for a widget
    ``width`` x ``height`` cells, syncing the editor's viewport + scroll first so
    the cursor stays visible (the same reclamp the curses draw loop does). Cells
    are tinted with the active TUI theme's role colours and per-cell
    conditional-format colours — cursor and selection win over both."""
    from rich.text import Text

    from ..core.reference import index_to_col
    from .themes import THEMES, _hex_to_256

    theme = THEMES.get(getattr(editor, "theme_name", "obsidian"), THEMES["obsidian"])
    s_label = _role_style(theme, "label")
    s_dim = _role_style(theme, "dim")
    s_lcd = _role_style(theme, "lcd")
    s_accent = _role_style(theme, "accent")
    s_cursor = _role_style(theme, "cursor") + " reverse"

    rows, cols = grid_viewport(width, height)
    editor.viewport_rows = rows
    editor.viewport_cols = cols
    editor._reclamp()

    sheet = editor.sheet
    top, left = editor.scroll_row, editor.scroll_col
    vsel = editor.visual_bounds() if editor.mode in ("visual", "visual-line") else None
    cond = _cond_colors(sheet)

    out = Text()
    # Column header.
    out.append(" " * _GUTTER, style=s_label + " bold")
    for c in range(left, left + cols):
        out.append(index_to_col(c).ljust(_COL_W + 1)[: _COL_W + 1], style=s_label + " bold")
    out.append("\n")
    # Data rows.
    for r in range(top, top + rows):
        out.append(str(r + 1).rjust(_GUTTER - 1) + " ", style=s_dim)
        for c in range(left, left + cols):
            text = sheet.display(r, c)[:_COL_W].ljust(_COL_W) + " "
            if r == editor.row and c == editor.col:
                style = s_cursor
            elif vsel is not None and vsel[0] <= r <= vsel[2] and vsel[1] <= c <= vsel[3]:
                style = s_accent + " reverse"
            elif cond.get((r, c)):
                style = f"color({_hex_to_256(cond[(r, c)])})"
            elif sheet.in_spill(r, c):
                style = s_accent
            else:
                style = s_lcd
            out.append(text, style=style)
        if r != top + rows - 1:
            out.append("\n")
    return out


def formula_text(editor) -> str:
    """The formula-bar line: the live edit buffer while inserting, else the
    read-only ``A1  <raw>`` readout (or the reader line in screen-reader mode)."""
    if editor.mode == "insert":
        return f"{editor.cursor_a1()}  {editor.edit_buf}"
    if getattr(editor, "screen_reader", False):
        return "» " + editor.reader_line()
    return editor.formula_bar_text()


def status_text(editor) -> str:
    """The bottom line: the ``:`` command being typed, or ``mode  A1  message``."""
    if editor.mode == "command":
        return editor.command_buf or ":"
    label = {"normal": "NORMAL", "insert": "-- INSERT --",
             "visual": "-- VISUAL --", "visual-line": "-- VISUAL LINE --"}.get(
                 editor.mode, editor.mode.upper())
    parts = [label, editor.cursor_a1()]
    if editor.message:
        parts.append(editor.message)
    return "   ".join(parts)


# Textual's arrow/navigation key names -> the editor's motion methods / vi chars.
_NAV_METHOD = {"pageup": "page_up", "pagedown": "page_down",
               "home": "line_home", "end": "line_end"}
_ARROW_VI = {"up": "k", "down": "j", "left": "h", "right": "l"}
_VISUAL_MOVE = {"h": (0, -1), "l": (0, 1), "j": (1, 0), "k": (-1, 0)}


def handle_key(editor, key: str, char: "str | None") -> None:
    """Route one key (Textual ``event.key`` name + ``event.character``) into the
    editor, dispatched by the current mode. Mirrors ``keys.py`` for curses down to
    the delegation into :meth:`TuiEditor.dispatch_normal` — so every normal-mode
    command (visual, yank/paste, search, append, …) and user ``init.py`` rebind
    works identically across both front-ends."""
    if editor.mode == "command":
        _command_key(editor, key, char)
    elif editor.mode == "insert":
        _insert_key(editor, key, char)
    elif editor.mode in ("visual", "visual-line"):
        _visual_key(editor, key, char)
    else:
        _normal_key(editor, key, char)


def _normal_key(editor, key: str, char: "str | None") -> None:
    from .keys import _user_binding

    if key == "enter":                       # Excel-style: Enter starts editing
        editor.message = ""
        editor.begin_insert()
        return
    if key == "ctrl+r":                       # redo (curses gets this as \x12)
        editor.message = ""
        editor.do_redo()
        return
    nav = _NAV_METHOD.get(key)
    if nav is not None:
        editor.message = ""
        getattr(editor, nav)()
        return
    k = _ARROW_VI.get(key) or char            # arrows behave as h/j/k/l
    if k is None:
        return
    if _user_binding(editor, "normal", k):    # ~/.config/abax/init.py rebinds win
        return
    if editor.pending_g:                       # resolve a pending 'g' (gt/gT/gg)
        editor.pending_g = False
        if k == "t":
            editor.message = ""
            editor.next_sheet(1)
            return
        if k == "T":
            editor.message = ""
            editor.next_sheet(-1)
            return
        editor.message = ""
        editor.dispatch_normal("g")           # honour the first 'g' (jump to top)
        if k == "g":
            return
    if k == "g":
        editor.pending_g = True
        return
    editor.message = ""
    editor.dispatch_normal(k)                  # the shared single-key command set


def _visual_key(editor, key: str, char: "str | None") -> None:
    from .keys import _user_binding

    k = _ARROW_VI.get(key) or char
    if k is not None and _user_binding(editor, "visual", k):
        return
    if k in _VISUAL_MOVE:                       # movement extends the selection
        editor.move(*_VISUAL_MOVE[k])
        editor.visual_refresh()
    elif key == "escape" or k == "v":          # Esc / v cancels
        editor.cancel_visual()
    elif k == "y":                             # yank the selection
        editor.visual_yank()
    elif k in ("d", "x"):                      # delete/clear the selection
        editor.visual_delete()


def _insert_key(editor, key: str, char: "str | None") -> None:
    if key == "escape":
        editor.cancel_insert()
    elif key == "enter":
        editor.commit_insert(advance=True)
    elif key == "tab":                          # autocomplete the current token
        editor.complete()
    elif key == "backspace":
        editor.edit_buf = editor.edit_buf[:-1]
        editor.refresh_completions()
    elif char is not None and char.isprintable():
        editor.edit_buf += char
        editor.refresh_completions()


def _command_key(editor, key: str, char: "str | None") -> None:
    if key == "escape":
        editor.mode = "normal"
        editor.command_buf = ""
    elif key == "enter":
        editor.run_command()
    elif key == "backspace":
        # Backspacing past the leading ':' cancels the command line.
        if len(editor.command_buf) <= 1:
            editor.mode = "normal"
            editor.command_buf = ""
        else:
            editor.command_buf = editor.command_buf[:-1]
    elif char is not None and char.isprintable():
        editor.command_buf += char


# --- the Textual App (thin shell around the pure functions above) -----------

try:
    from textual.app import App
    from textual.widget import Widget
    from textual.widgets import Static

    class _GridView(Widget):
        """Full-height grid body; re-renders from editor state on every refresh."""

        can_focus = True

        def render(self):
            size = self.size
            return render_grid(self.app.editor, max(1, size.width), max(1, size.height))

    class AbaxTextualApp(App):
        """Textual view over a :class:`TuiEditor`. All logic lives in the editor;
        this only paints it and forwards keys."""

        CSS = """
        Screen { layers: base; }
        #formula { dock: top; height: 1; background: $panel; color: $text; }
        #grid { height: 1fr; }
        #status { dock: bottom; height: 1; background: $panel; color: $text; }
        """

        def __init__(self, editor) -> None:
            super().__init__()
            self.editor = editor

        def compose(self):
            yield Static(id="formula")
            yield _GridView(id="grid")
            yield Static(id="status")

        def on_mount(self) -> None:
            self.query_one("#grid", _GridView).focus()
            self._sync()

        def _sync(self) -> None:
            if not self.editor.running:
                self.exit()
                return
            self.query_one("#formula", Static).update(formula_text(self.editor))
            self.query_one("#status", Static).update(status_text(self.editor))
            self.query_one("#grid", _GridView).refresh()

        def on_key(self, event) -> None:
            try:
                handle_key(self.editor, event.key, event.character)
            except Exception as exc:  # noqa: BLE001 — a bad key must not crash the app
                self.editor.message = f"error: {type(exc).__name__}: {exc}"[:120]
            event.stop()
            event.prevent_default()
            self._sync()

except ImportError:  # pragma: no cover — textual not installed
    AbaxTextualApp = None  # type: ignore[assignment]


def textual_available() -> bool:
    """Whether the Textual App class imported (i.e. the ``textual`` dep is present)."""
    return AbaxTextualApp is not None


def run_textual_tui(file: str | None = None, registry=None) -> int:
    """Entry point: build the shared session and run the Textual app.

    Returns a process exit code. Falls back to the curses front-end when Textual
    isn't installed, so ``abax tui`` always works.
    """
    if not textual_available():
        from .app import run_tui
        return run_tui(file, registry)

    from .session import build_session

    editor = build_session(file, registry)
    AbaxTextualApp(editor).run()
    return 0
