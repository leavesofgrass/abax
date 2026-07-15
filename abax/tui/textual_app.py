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


def render_grid(editor, width: int, height: int):
    """Build the grid body (header + data rows) as a Rich ``Text`` for a widget
    ``width`` x ``height`` cells, syncing the editor's viewport + scroll first so
    the cursor stays visible (the same reclamp the curses draw loop does)."""
    from rich.text import Text

    from ..core.reference import index_to_col

    rows, cols = grid_viewport(width, height)
    editor.viewport_rows = rows
    editor.viewport_cols = cols
    editor._reclamp()

    sheet = editor.sheet
    top, left = editor.scroll_row, editor.scroll_col
    vsel = editor.visual_bounds() if editor.mode in ("visual", "visual-line") else None

    out = Text()
    # Column header.
    out.append(" " * _GUTTER, style="bold")
    for c in range(left, left + cols):
        out.append(index_to_col(c).ljust(_COL_W + 1)[: _COL_W + 1], style="bold")
    out.append("\n")
    # Data rows.
    for r in range(top, top + rows):
        out.append(str(r + 1).rjust(_GUTTER - 1) + " ", style="dim")
        for c in range(left, left + cols):
            text = sheet.display(r, c)[:_COL_W].ljust(_COL_W) + " "
            if r == editor.row and c == editor.col:
                style = "reverse"
            elif vsel is not None and vsel[0] <= r <= vsel[2] and vsel[1] <= c <= vsel[3]:
                style = "reverse dim"
            elif sheet.in_spill(r, c):
                style = "cyan"
            else:
                style = ""
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


def handle_key(editor, key: str, char: "str | None") -> None:
    """Route one key (Textual ``event.key`` name + ``event.character``) into the
    editor, dispatched by the current mode. Mirrors ``keys.py`` for curses; the
    editor methods it calls are identical."""
    if editor.mode == "command":
        _command_key(editor, key, char)
    elif editor.mode == "insert":
        _insert_key(editor, key, char)
    else:
        _normal_key(editor, key, char)


def _normal_key(editor, key: str, char: "str | None") -> None:
    # A bare 'g' arms 'gg'; any other key disarms it (handled at the end).
    was_pending_g = editor.pending_g
    editor.pending_g = False
    if key in ("left", "h"):
        editor.move(0, -1)
    elif key in ("right", "l"):
        editor.move(0, 1)
    elif key in ("up", "k"):
        editor.move(-1, 0)
    elif key in ("down", "j"):
        editor.move(1, 0)
    elif key == "pageup":
        editor.page_up()
    elif key == "pagedown":
        editor.page_down()
    elif key == "home" or char == "0":
        editor.line_home()
    elif key == "end" or char == "$":
        editor.line_end()
    elif key == "g":
        if was_pending_g:
            editor.row = 0
            editor._reclamp()
            editor.announce()
        else:
            editor.pending_g = True
    elif char == "G":
        n_rows, _ = editor.sheet.used_bounds()
        editor.row = max(0, n_rows - 1)
        editor._reclamp()
        editor.announce()
    elif key in ("i", "enter") or char == "i":
        editor.begin_insert()
    elif char == ":" or key == "colon":
        editor.begin_command()
    elif char == "u":
        editor.do_undo()
    elif key == "ctrl+r":
        editor.do_redo()


def _insert_key(editor, key: str, char: "str | None") -> None:
    if key == "escape":
        editor.cancel_insert()
    elif key == "enter":
        editor.commit_insert(advance=True)
    elif key == "backspace":
        editor.edit_buf = editor.edit_buf[:-1]
    elif char is not None and char.isprintable():
        editor.edit_buf += char


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
