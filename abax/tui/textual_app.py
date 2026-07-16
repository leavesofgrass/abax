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

from .commands import _fmt_num

# Grid geometry — one header row inside the grid widget; the formula bar and
# status line are separate docked widgets (unlike curses, which counts them here).
_COL_W = 10
_GUTTER = 5

# Editor modes that replace the grid with a full-panel overlay (rendered by
# render_overlay, keys routed by _overlay_key) — the same set the curses view
# paints specially.
OVERLAY_MODES = ("browser", "help", "describe", "rpn", "plot")


def grid_viewport(width: int, height: int) -> "tuple[int, int]":
    """Data (rows, cols) that fit a grid widget ``width`` x ``height`` cells.

    One row is the column header; each data column is ``_COL_W`` + 1 separator,
    after a ``_GUTTER``-wide row-number gutter. Mirrors the curses
    ``visible_rows``/``visible_cols`` so the two views scroll identically.
    """
    rows = max(1, height - 1)
    cols = max(1, (width - _GUTTER) // (_COL_W + 1))
    return rows, cols


# Truecolor palettes for the Textual view — matched to the GUI Theme presets so
# the two front-ends look the same on a colour terminal. The GUI reads "purple"
# mostly from its dark violet-tinted background + strong violet accent, not from
# very-purple text, so the TUI mirrors those. A theme not listed here falls back
# to its xterm-256 role indices (still fine, just not truecolor).
_HEX = {
    "galaxy": {
        "bg": "#1e1e2e", "panel": "#181825",   # dark violet-tinted base / bars
        "lcd": "#cdd6f4", "label": "#a78bfa", "dim": "#6c7086",
        "accent": "#7c3aed", "banner": "#c4b5fd", "cursor": "#7c3aed",
    },
}


def _role_style(theme, role: str) -> str:
    """A Rich style for a theme role: the truecolor hex from :data:`_HEX` when the
    theme has one (matching the GUI), else the theme's xterm-256 index as
    ``color(N)`` (Rich reads the 256-palette form directly)."""
    pal = _HEX.get(theme.name)
    if pal and role in pal:
        return pal[role]
    return f"color({theme.color(role, '256')})"


def _cursor_style(theme) -> str:
    """The active cell — a solid block. Truecolor themes paint dark text on the
    accent violet; 256 themes reverse the cursor role."""
    pal = _HEX.get(theme.name)
    if pal:
        return f"{pal['bg']} on {pal['cursor']}"
    return f"color({theme.color('cursor', '256')}) reverse"


def _selection_style(theme) -> str:
    """A visual-selection cell — light text on the accent violet (truecolor) or a
    reversed accent (256)."""
    pal = _HEX.get(theme.name)
    if pal:
        return f"{pal['lcd']} on {pal['accent']}"
    return f"color({theme.color('accent', '256')}) reverse"


def theme_surface(theme) -> "dict | None":
    """Background/foreground/accent hex for the screen + docked bars + grid base,
    or ``None`` to keep Textual's defaults (a theme with no truecolor palette)."""
    pal = _HEX.get(theme.name)
    if not pal:
        return None
    return {"bg": pal["bg"], "panel": pal["panel"], "fg": pal["lcd"],
            "accent": pal["accent"]}


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


# Reference-highlight palette (Excel's coloured range boxes): background tints
# for truecolor themes, foreground tints for 256-palette themes. Order matches
# refscan's colour indices — blue, teal, orange, plum, olive.
_REF_BG = ("#1f3a5f", "#1d4a42", "#5a3a20", "#4a2a4a", "#4f4a1f")
_REF_FG256 = (33, 42, 208, 170, 178)


def _ref_cells(editor, top: int, left: int, rows: int, cols: int) -> dict:
    """``{(row, col): colour_index}`` for cells the in-progress formula
    references, clipped to the visible window (a ``=SUM(A1:A100000)`` range
    costs the viewport intersection, never the full rectangle). Empty unless
    an insert-mode formula is being typed."""
    if editor.mode != "insert" or not editor.edit_buf.startswith("="):
        return {}
    from ..core.refscan import refs_for_sheet

    out: dict = {}
    for span in refs_for_sheet(editor.edit_buf, editor.sheet.name,
                               palette_size=len(_REF_BG)):
        r_lo, r_hi = max(span.r1, top), min(span.r2, top + rows - 1)
        c_lo, c_hi = max(span.c1, left), min(span.c2, left + cols - 1)
        for r in range(r_lo, r_hi + 1):
            for c in range(c_lo, c_hi + 1):
                out.setdefault((r, c), span.color)
    return out


def render_grid(editor, width: int, height: int):
    """Build the grid body (header + data rows) as a Rich ``Text`` for a widget
    ``width`` x ``height`` cells, syncing the editor's viewport + scroll first so
    the cursor stays visible (the same reclamp the curses draw loop does). Cells
    are tinted with the active TUI theme's role colours and per-cell
    conditional-format colours — cursor and selection win over both."""
    from rich.text import Text

    from .themes import THEMES, _hex_to_256
    from ..core.reference import index_to_col

    theme = THEMES.get(getattr(editor, "theme_name", "galaxy"), THEMES["galaxy"])
    s_label = _role_style(theme, "label")
    s_dim = _role_style(theme, "dim")
    s_lcd = _role_style(theme, "lcd")
    s_accent = _role_style(theme, "accent")
    s_cursor = _cursor_style(theme)
    s_sel = _selection_style(theme)

    rows, cols = grid_viewport(width, height)
    editor.viewport_rows = rows
    editor.viewport_cols = cols
    editor._reclamp()

    sheet = editor.sheet
    top, left = editor.scroll_row, editor.scroll_col
    vsel = editor.visual_bounds() if editor.mode in ("visual", "visual-line") else None
    cond = _cond_colors(sheet)
    # Cells the in-progress formula references (Excel's coloured range boxes).
    refs = _ref_cells(editor, top, left, rows, cols)
    pal = _HEX.get(theme.name)
    if pal:
        ref_styles = [f"{pal['lcd']} on {bg}" for bg in _REF_BG]
    else:
        ref_styles = [f"color({n})" for n in _REF_FG256]

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
            ref_idx = refs.get((r, c))
            if r == editor.row and c == editor.col:
                style = s_cursor
            elif vsel is not None and vsel[0] <= r <= vsel[2] and vsel[1] <= c <= vsel[3]:
                style = s_sel
            elif ref_idx is not None:
                style = ref_styles[ref_idx]
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


def _scroll_window(idx: int, total: int, visible: int) -> int:
    """First index to show so ``idx`` stays roughly centred (curses overlay idiom)."""
    return max(0, min(idx - visible // 2, max(0, total - visible)))


def render_overlay(editor, width: int, height: int):
    """Render the active overlay mode (help / function browser / describe /
    ``:tasks``·``:critpath`` / RPN / plot) as a Rich ``Text``, from the same editor
    state the curses painters read. The grid widget swaps to this whenever
    ``editor.mode`` is one of :data:`OVERLAY_MODES`."""
    from rich.text import Text

    from .themes import THEMES

    theme = THEMES.get(getattr(editor, "theme_name", "galaxy"), THEMES["galaxy"])
    s_banner = _role_style(theme, "banner") + " bold"
    s_sel = _role_style(theme, "accent") + " reverse"
    s_lcd = _role_style(theme, "lcd")
    s_label = _role_style(theme, "label")
    s_dim = _role_style(theme, "dim")
    mode = editor.mode
    out = Text()

    def title(text: str) -> None:
        out.append(text[: width - 1] + "\n", style=s_banner)

    if mode == "browser":
        from ..core.completion import signature

        title("Function browser — j/k select · Enter insert · Esc close")
        names = editor.browser
        visible = max(1, height - 3)
        start = _scroll_window(editor.browser_idx, len(names), visible)
        for i, name in enumerate(names[start : start + visible]):
            sel = (start + i) == editor.browser_idx
            out.append("  " + name + "\n", style=s_sel if sel else s_lcd)
        if names:
            out.append("\n" + signature(names[editor.browser_idx])[: width - 1], style=s_label)

    elif mode == "help":
        from .editor import HELP_ENTRIES

        title("Help — j/k scroll · g/G top/bottom · Esc/q close")
        visible = max(1, height - 2)
        start = _scroll_window(editor.help_idx, len(HELP_ENTRIES), visible)
        for i, (key, desc) in enumerate(HELP_ENTRIES[start : start + visible]):
            if desc == "":
                out.append("  " + key + "\n", style=s_label)
            else:
                sel = (start + i) == editor.help_idx
                out.append(f"  {key:<28} {desc}\n", style=s_sel if sel else s_lcd)

    elif mode == "describe":
        summary = getattr(editor, "describe_summary", None)
        count = summary["count"] if isinstance(summary, dict) else 0
        title(getattr(editor, "describe_title", "") or (
            f"Describe {editor.describe_range}  (n={count})  ·  "
            "j/k scroll · g/G top/bottom · Esc/q close"))
        rows = editor.describe_lines
        visible = max(1, height - 2)
        start = _scroll_window(editor.describe_idx, len(rows), visible)
        for i, (label, value) in enumerate(rows[start : start + visible]):
            if not label and not value:
                out.append("\n")
                continue
            sel = (start + i) == editor.describe_idx
            out.append(f"  {label:<20} {value}\n", style=s_sel if sel else s_lcd)

    elif mode == "rpn":
        rpn = editor._ensure_rpn()
        title("RPN — tokens + Enter · '<' pull cell · '>' store X · Esc exit")
        for i, lab in enumerate(("T", "Z", "Y", "X")):
            v = _fmt_num(rpn.stack[3 - i])
            out.append(f"   {lab}: {v}\n", style=(s_label + " bold") if lab == "X" else s_lcd)
        regs = ", ".join(f"{k}={_fmt_num(v)}" for k, v in sorted(rpn.regs.items()))
        out.append(f"   [{rpn.angle}]  {regs}\n", style=s_dim)
        out.append("rpn> " + editor.rpn_input, style=s_sel)

    elif mode == "plot":
        from ..core.graphing import braille_plot

        title(f"y = {editor.plot_expr}   (Esc to close)")
        xmin, xmax, ymin, ymax = getattr(editor, "plot_bounds", None) or (None, None, None, None)
        try:
            canvas = braille_plot(editor.plot_pts, width=max(10, width - 2),
                                  height=max(4, height - 2),
                                  xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax)
            out.append(canvas, style=_role_style(theme, "accent"))
        except Exception as exc:  # pragma: no cover - defensive
            out.append(f"plot error: {exc}", style=s_dim)

    return out


def _completion_hint(candidates: list) -> str:
    """The inline hint shown while typing a formula: one function's signature, or
    a brace-list of the top candidates (mirrors the curses insert line)."""
    if not candidates:
        return ""
    if len(candidates) == 1:
        from ..core.completion import signature
        return "   " + signature(candidates[0])
    return "   {" + " ".join(candidates[:8]) + ("…}" if len(candidates) > 8 else "}")


def formula_text(editor) -> str:
    """The formula-bar line: the live edit buffer while inserting, else the
    read-only ``A1  <raw>`` readout (or the reader line in screen-reader mode)."""
    if editor.mode == "insert":
        return f"{editor.cursor_a1()}  {editor.edit_buf}"
    if getattr(editor, "screen_reader", False):
        return "» " + editor.reader_line()
    return editor.formula_bar_text()


def status_text(editor) -> str:
    """The bottom line: the ``:`` command being typed, the live edit + completion
    hint while inserting, or ``mode  A1  message`` otherwise."""
    if editor.mode == "command":
        return editor.command_buf or ":"
    if editor.mode == "insert":
        line = "=> " + editor.edit_buf
        if editor.completions:
            line += _completion_hint(editor.completions)
        elif editor.arg_hint:
            line += "   " + editor.arg_hint
        return line
    label = {"normal": "NORMAL", "visual": "-- VISUAL --",
             "visual-line": "-- VISUAL LINE --"}.get(editor.mode, editor.mode.upper())
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
    # Some terminals send the numpad Enter as LF (0x0A), which Textual reports as
    # ``ctrl+j`` rather than ``enter`` (CR / 0x0D). Normalise it so the numpad
    # Enter commits an edit / runs a command exactly like the main Enter — the
    # curses front-end already accepts LF via its ``_is_enter`` set.
    if key == "ctrl+j":
        key = "enter"
    if editor.mode in OVERLAY_MODES:
        _overlay_key(editor, key, char)
    elif editor.mode == "command":
        _command_key(editor, key, char)
    elif editor.mode == "insert":
        _insert_key(editor, key, char)
    elif editor.mode in ("visual", "visual-line"):
        _visual_key(editor, key, char)
    else:
        _normal_key(editor, key, char)


def _overlay_key(editor, key: str, char: "str | None") -> None:
    """Key handling for the full-panel overlay modes (mirrors keys.py's per-overlay
    handlers). All the list/scroll/insert actions are the editor's own methods."""
    mode = editor.mode
    k = _ARROW_VI.get(key) or char
    close = key == "escape" or k == "q"
    if mode == "rpn":                          # a text-entry overlay, not a list
        if key == "enter":
            editor.rpn_eval()
        elif key == "escape":
            editor.mode = "normal"
        elif key == "backspace":
            editor.rpn_input = editor.rpn_input[:-1]
        elif char is not None and char.isprintable():
            editor.rpn_input += char
        return
    if mode == "plot":
        if close:
            editor.mode = "normal"
        return
    if close:
        editor.mode = "normal"
        return
    if mode == "browser":
        if key == "enter":
            editor.browser_insert()
        elif k == "j":
            editor.browser_move(1)
        elif k == "k":
            editor.browser_move(-1)
        elif k == "g":
            editor.browser_idx = 0
        elif k == "G":
            editor.browser_idx = max(0, len(editor.browser) - 1)
    elif mode == "help":
        if k == "j":
            editor.help_move(1)
        elif k == "k":
            editor.help_move(-1)
        elif k == "g":
            editor.help_idx = 0
        elif k == "G":
            editor.help_move(1 << 30)
    elif mode == "describe":
        if k == "j":
            editor.describe_move(1)
        elif k == "k":
            editor.describe_move(-1)
        elif k == "g":
            editor.describe_idx = 0
        elif k == "G":
            editor.describe_move(1 << 30)


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
            editor = self.app.editor
            w, h = max(1, self.size.width), max(1, self.size.height)
            if editor.mode in OVERLAY_MODES:
                return render_overlay(editor, w, h)
            return render_grid(editor, w, h)

    class AbaxTextualApp(App):
        """Textual view over a :class:`TuiEditor`. All logic lives in the editor;
        this only paints it and forwards keys."""

        CSS = """
        Screen { layers: base; }
        #formula { dock: top; height: 1; }
        #grid { height: 1fr; }
        #status { dock: bottom; height: 1; }
        """

        def __init__(self, editor) -> None:
            super().__init__()
            self.editor = editor
            self._styled_theme = None

        def compose(self):
            yield Static(id="formula")
            yield _GridView(id="grid")
            yield Static(id="status")

        def on_mount(self) -> None:
            self.query_one("#grid", _GridView).focus()
            self._apply_theme_surface()
            self._sync()

        def _apply_theme_surface(self) -> None:
            """Paint the screen, grid base, and docked bars from the active theme
            (so galaxy reads as purple-on-black, not white). Re-applied only when
            the theme actually changes, so it costs nothing per keystroke."""
            from .themes import THEMES

            name = getattr(self.editor, "theme_name", "galaxy")
            if name == self._styled_theme:
                return
            self._styled_theme = name
            surface = theme_surface(THEMES.get(name, THEMES["galaxy"]))
            if surface is None:
                return
            self.screen.styles.background = surface["bg"]
            grid = self.query_one("#grid", _GridView)
            grid.styles.background = surface["bg"]
            grid.styles.color = surface["fg"]
            for wid in ("#formula", "#status"):
                w = self.query_one(wid, Static)
                w.styles.background = surface["panel"]
                w.styles.color = surface["fg"]

        def _sync(self) -> None:
            if not self.editor.running:
                self.exit()
                return
            self._apply_theme_surface()
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
