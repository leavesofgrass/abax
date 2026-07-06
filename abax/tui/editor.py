"""The headless TUI editor state machine — cursor, modes, and command dispatch.

The curses front-end drives this; tests can drive it directly.
"""

from __future__ import annotations

from .commands import _fmt_num, parse_command
from .themes import THEMES
from ..core.reference import to_a1

# Static help table: ``(key-or-command, one-line description)`` shown by the
# ``?`` / ``:help`` overlay. Kept here so both the overlay renderer and tests
# read the same source of truth.
HELP_ENTRIES: list[tuple[str, str]] = [
    ("-- movement --", ""),
    ("h j k l", "move cursor left / down / up / right (also arrow keys)"),
    ("g", "jump to the first row"),
    ("G", "jump to the last used row"),
    ("0", "jump to the first column"),
    ("gt / gT", "next / previous sheet"),
    ("n / N", "next / previous search match"),
    ("-- editing --", ""),
    ("i", "insert: edit the current cell (Enter commits, Esc cancels)"),
    ("x", "clear the current cell"),
    ("y", "yank (copy) the current cell"),
    ("p", "paste the yanked cell/region at the cursor"),
    ("u", "undo the last change"),
    ("Ctrl-R", "redo the last undone change"),
    ("-- overlays --", ""),
    ("?", "open this help overlay"),
    (":func", "open the function browser"),
    (":rpn", "open the RPN calculator"),
    (":plot", "plot an expression or a cell range"),
    ("-- commands --", ""),
    (":w [path]", "write (save) the workbook"),
    (":q", "quit"),
    (":wq / :x", "save and quit"),
    (":undo / :redo", "undo / redo the last change"),
    (":help", "open this help overlay"),
    (":find <pat>", "search cells (regex); n/N to navigate"),
    (":replace <p> <r>", "regex replace across the sheet"),
    (":s/pat/repl/[i]", "vim-style substitute on the current sheet"),
    (":copy [range]", "copy a range (default: current cell)"),
    (":paste [dest]", "paste the copied range"),
    (":fill down|right|series <range>", "fill a range"),
    (":sort <range> [col] [desc]", "sort a range"),
    (":describe <range>", "descriptive stats over a range (status line)"),
    (":describe full <range>", "full scrollable descriptive-stats overlay"),
    (":pivot <rng> <idx> <col> <val> [agg]", "pivot/group-by a table into the sheet"),
    (":fmt <spec> [range]", "apply a number format"),
    (":convert <v> <from> <to>", "unit conversion"),
    (":sheet <name|index>", "switch to a sheet (gt/gT for next/prev)"),
    (":sheets", "list the workbook's sheets"),
    (":theme <name>", "switch the colour theme"),
    (":py <python>", "run a Python snippet against the sheet"),
    (":eq <latex>", "render LaTeX math to unicode"),
    (":!<cmd>", "run a shell command"),
    (":func [filter]", "browse function names"),
    (":rpn [tokens]", "RPN calculator (REPL or one-shot)"),
    (":plot <expr|range>", "plot an expression or cell range(s)"),
    (":macro <name>", "run a saved macro"),
    (":rec ...", "record / replay a macro"),
    (":clips / :clip <i>", "clipboard history"),
]


class TuiEditor:
    """Headless spreadsheet editor state: cursor + mode + sheet.

    The curses front-end drives this; tests can drive it directly.
    """

    def __init__(self, document, registry=None, settings=None) -> None:
        from ..recorder import MacroRecorder

        self.doc = document
        self.registry = registry
        self.settings = settings
        # Accessibility knobs, read defensively off the Wave-1 settings contract
        # (older settings.json / structs simply lack them -> the features stay
        # off). ``screen_reader`` swaps the grid header for a single-line,
        # reader-friendly view of the active cell; ``speak_on_move`` additionally
        # voices that line through the optional TTS engine on every cursor move.
        self.screen_reader = bool(getattr(settings, "tui_screen_reader", False))
        self.speak_on_move = bool(getattr(settings, "speak_on_move", False))
        self.recorder = MacroRecorder()
        self.row = 0
        self.col = 0
        # Top-left of the visible window. The render loop reports how many data
        # rows/cols currently fit (``viewport_rows``/``viewport_cols``); the
        # reclamp helper then scrolls just enough to keep the cursor on screen.
        self.scroll_row = 0
        self.scroll_col = 0
        self.viewport_rows = 0  # data rows the grid can show (0 => unknown yet)
        self.viewport_cols = 0  # data cols the grid can show (0 => unknown yet)
        # normal|insert|command|browser|visual|visual-line|help|rpn|plot|describe
        self.mode = "normal"
        self.anchor_row = 0  # visual-mode selection anchor (fixed corner)
        self.anchor_col = 0
        self.pending_g = False  # a bare 'g' was pressed; awaiting the second key
        self.command_buf = ""
        self.edit_buf = ""
        self.completions: list[str] = []
        self.arg_hint = ""
        self.clip = None  # last copied region (core.fill.Clip)
        self.matches: list = []  # search hits (core.search.Match)
        self.match_idx = 0
        self.browser: list[str] = []  # function-browser entries when mode == browser
        self.browser_idx = 0
        self.help_idx = 0  # scroll offset when mode == help
        self.theme_name = "obsidian"  # live TUI theme (changeable via :theme)
        from ..core.clipboard import ClipboardManager

        self.clips = ClipboardManager()  # text copy history
        self.rpn = None  # core.calc.rpn.RPN, lazily created
        self.rpn_input = ""  # input buffer when mode == rpn
        self.plot_pts: list = []  # sampled points when mode == plot
        self.plot_expr = ""
        self.plot_bounds = None  # (xmin, xmax, ymin, ymax) for range plots, else None
        self.describe_summary: dict | None = None  # last :describe result, for tests
        self.describe_lines: list[tuple[str, str]] = []  # full-overlay rows (label, value)
        self.describe_range = ""  # range shown by the :describe full overlay
        self.describe_idx = 0  # scroll offset when mode == describe
        self.spoken: list[str] = []  # last lines handed to TTS (drives tests/replay)
        self.message = ""
        self.running = True

    @property
    def sheet(self):
        return self.doc.workbook.sheet

    def move(self, dr: int, dc: int) -> None:
        self.row = max(0, self.row + dr)
        self.col = max(0, self.col + dc)
        self._reclamp()
        self.announce()

    def _reclamp(self) -> None:
        """Keep the cursor non-negative and inside the visible window.

        Called at *every* cursor mutation (moves, g/G/0/$, goto, page, undo/redo
        cursor restore, visual-mode extension, sheet switch). Row/col are pinned
        to ``>= 0``; then, when the render loop has told us how big the window is
        (``viewport_rows``/``viewport_cols`` > 0), ``scroll_row``/``scroll_col``
        are nudged just far enough that ``scroll <= cursor < scroll + visible``.
        """
        self.row = max(0, self.row)
        self.col = max(0, self.col)
        vr, vc = self.viewport_rows, self.viewport_cols
        if vr > 0:
            if self.row < self.scroll_row:
                self.scroll_row = self.row
            elif self.row >= self.scroll_row + vr:
                self.scroll_row = self.row - vr + 1
        if vc > 0:
            if self.col < self.scroll_col:
                self.scroll_col = self.col
            elif self.col >= self.scroll_col + vc:
                self.scroll_col = self.col - vc + 1
        self.scroll_row = max(0, self.scroll_row)
        self.scroll_col = max(0, self.scroll_col)

    def cursor_a1(self) -> str:
        return to_a1(self.row, self.col)

    def begin_insert(self) -> None:
        self.mode = "insert"
        self.edit_buf = self.sheet.get_raw(self.row, self.col)

    def commit_insert(self, advance: bool = False) -> None:
        self.doc.checkpoint(f"edit {self.cursor_a1()}")
        self.sheet.set_cell(self.row, self.col, self.edit_buf)
        self.recorder.record_set(self.cursor_a1(), self.edit_buf)
        self.doc.mark_dirty()
        self.mode = "normal"
        self.completions = []
        self.arg_hint = ""
        if advance:              # Excel: Enter drops to the cell below
            self.move(1, 0)

    def cancel_insert(self) -> None:
        """Abandon the in-progress edit, keeping the cell's existing value."""
        self.mode = "normal"
        self.edit_buf = ""
        self.completions = []
        self.arg_hint = ""

    def _completion_context(self):
        """``(names, sheets)`` for autocomplete — the workbook's defined names and
        sheet names, offered alongside function names."""
        wb = self.doc.workbook
        reg = getattr(wb, "names", None)
        names = tuple(n for n, _ in reg.names()) if reg is not None else ()
        sheets = tuple(s.name for s in wb.sheets)
        return names, sheets

    def refresh_completions(self) -> None:
        """Recompute candidate names and the active-call arg hint for the buffer."""
        from ..core.completion import complete, format_hint, signature_hint

        cursor = len(self.edit_buf)
        names, sheets = self._completion_context()
        self.completions = complete(self.edit_buf, cursor, names=names, sheets=sheets)
        hint = signature_hint(self.edit_buf, cursor)
        self.arg_hint = format_hint(hint) if hint else ""

    def complete(self) -> None:
        """Tab-completion: single match inserts ``NAME(``; many → common prefix."""
        from ..core.completion import apply_completion, common_prefix, complete, current_token

        names, sheets = self._completion_context()
        cands = complete(self.edit_buf, len(self.edit_buf), names=names, sheets=sheets)
        if not cands:
            self.completions = []
            return
        if len(cands) == 1:
            self.edit_buf, _ = apply_completion(self.edit_buf, len(self.edit_buf), cands[0])
            self.completions = []
            return
        token, start = current_token(self.edit_buf, len(self.edit_buf))
        prefix = common_prefix(cands)
        if len(prefix) > len(token):
            # token ends at the cursor (end of buffer), so just extend it
            self.edit_buf = self.edit_buf[:start] + prefix
        self.completions = cands

    def begin_command(self) -> None:
        self.mode = "command"
        self.command_buf = ":"

    def run_command(self) -> None:
        raw = self.command_buf[1:] if self.command_buf.startswith(":") else self.command_buf
        # vim-style substitute: :s/pat/repl/[i]  (handles spaces in pat/repl)
        if raw.startswith("s/") or raw.startswith("%s/"):
            self.mode = "normal"
            self.command_buf = ""
            self._handle_substitute(raw)
            return
        if raw.startswith("!"):  # shell passthrough: :!<command>
            self.mode = "normal"
            self.command_buf = ""
            from ..core.shell import run

            res = run(raw[1:].strip())
            out = (res.stdout or res.stderr or "(no output)").strip().replace("\n", " ⏎ ")
            self.message = f"$ {out[:200]}"
            return
        cmd, args = parse_command(self.command_buf)
        self.mode = "normal"
        self.command_buf = ""
        if cmd in ("q", "quit"):
            self.running = False
        elif cmd in ("w", "write"):
            try:
                self.doc.save(args[0] if args else None)
                self.message = f"written {self.doc.title}"
            except Exception as exc:
                self.message = f"error: {exc}"
        elif cmd in ("wq", "x"):
            try:
                self.doc.save(args[0] if args else None)
            except Exception as exc:
                self.message = f"error: {exc}"
                return
            self.running = False
        elif cmd == "macros":
            names = sorted(self.registry.macros) if self.registry else []
            self.message = "macros: " + (", ".join(names) if names else "none")
        elif cmd == "macro":
            self._run_macro(args[0] if args else "")
        elif cmd in ("rec", "record"):
            self._handle_record(args)
        elif cmd in ("copy", "yank"):
            self._handle_copy(args)
        elif cmd in ("paste", "put"):
            self._handle_paste(args)
        elif cmd == "fill":
            self._handle_fill(args)
        elif cmd == "sort":
            self._handle_sort(args)
        elif cmd in ("find", "f"):
            self._handle_find(args)
        elif cmd in ("replace", "r"):
            self._handle_replace(args)
        elif cmd == "theme":
            self._handle_theme(args)
        elif cmd == "sheet":
            self.goto_sheet(args[0] if args else "")
        elif cmd == "sheets":
            self.list_sheets()
        elif cmd in ("func", "functions"):
            self._open_browser(args[0] if args else "")
        elif cmd == "rpn":
            self._handle_rpn_cmd(args)
        elif cmd == "clips":
            entries = self.clips.entries()
            self.message = ("clips: " + " | ".join(
                f"{i}:{e.label}" for i, e in enumerate(entries))) if entries else "clipboard empty"
        elif cmd == "clip":
            self._paste_clip_history(args)
        elif cmd == "py":
            self._handle_py(raw[2:].strip() if raw.startswith("py") else "")
        elif cmd == "fmt":
            self._handle_fmt(args)
        elif cmd == "plot":
            self._handle_plot(args)
        elif cmd in ("describe", "desc", "stats"):
            self._handle_describe(args)
        elif cmd in ("pivot", "pt"):
            self._handle_pivot(args)
        elif cmd == "eq":
            self._handle_eq(raw[2:].strip() if raw.startswith("eq") else "")
        elif cmd == "convert":
            self._handle_convert(args)
        elif cmd == "undo":
            self.do_undo()
        elif cmd == "redo":
            self.do_redo()
        elif cmd == "help":
            self._open_help()
        else:
            self.message = f"unknown command: {cmd}"

    # --- undo / redo ------------------------------------------------------

    def do_undo(self) -> None:
        """Restore the previous checkpoint and refresh the view."""
        if self.doc.undo():
            self._reclamp()
            self.message = "undone"
        else:
            self.message = "nothing to undo"

    def do_redo(self) -> None:
        """Re-apply the most recently undone checkpoint and refresh the view."""
        if self.doc.redo():
            self._reclamp()
            self.message = "redone"
        else:
            self.message = "nothing to redo"

    # --- formula bar ------------------------------------------------------

    def formula_bar_text(self) -> str:
        """The read-only formula bar: ``<A1 ref>  <raw cell content>``.

        Mirrors the GUI's cell entry — the raw text (formula or literal) of the
        active cell, so what you'd edit with ``i`` is always visible.
        """
        return f"{self.cursor_a1()}  {self.sheet.get_raw(self.row, self.col)}"

    # --- screen-reader mode ----------------------------------------------

    def reader_line(self) -> str:
        """A single-line, reader-friendly description of the active cell.

        Speaks the cell *reference*, its *displayed value* (or an explicit
        "blank"), the underlying *formula* when the raw content differs from the
        value, and the current *edit state* — so a screen-reader user gets the
        whole context of one cell on one line without scanning a 2-D grid.

        Examples::

            A1: 3 (formula =1+2)
            B2: blank
            C3: hello — editing: hel      (while typing in insert mode)
        """
        ref = self.cursor_a1()
        raw = self.sheet.get_raw(self.row, self.col)
        shown = self.sheet.display(self.row, self.col)
        value = shown if shown != "" else "blank"
        line = f"{ref}: {value}"
        # Surface the formula behind a computed value (raw starts with '=' and
        # differs from what's shown). A plain literal already appears as `value`.
        if raw.startswith("=") and raw != shown:
            line += f" (formula {raw})"
        if self.mode == "insert":
            line += f" — editing: {self.edit_buf}"
        elif self.mode in ("visual", "visual-line"):
            r1, c1, r2, c2 = self.visual_bounds()
            line += f" — selecting {to_a1(r1, c1)}:{to_a1(r2, c2)}"
        return line

    def announce(self) -> None:
        """Voice the active cell after a cursor move, if speak-on-move is on.

        A no-op unless :attr:`speak_on_move` is set. Kept separate from
        :meth:`reader_line` (which the renderer always calls in screen-reader
        mode) so movement — not every repaint — drives the speech.
        """
        if self.speak_on_move:
            self.speak(self.reader_line())

    def speak(self, text: str) -> None:
        """Hand ``text`` to the optional TTS engine, guarded and non-fatal.

        The ``engine.tts`` adapter (and its ``pyttsx3`` backend) is optional: if
        it is absent or fails, we swallow the error — speech is a courtesy, never
        a hard dependency of the TUI. Every attempt is recorded in
        :attr:`spoken` so headless tests can assert *what* would be spoken
        without a real audio device.
        """
        if not text:
            return
        self.spoken.append(text)
        try:  # optional dep: abax.engine.tts -> pyttsx3
            from ..engine import tts

            if getattr(tts, "available", lambda: False)():
                tts.speak(text)
        except Exception:
            pass  # no TTS engine / backend -> silently skip the audio

    # --- sheet switching --------------------------------------------------

    def switch_sheet(self, index: int) -> bool:
        """Make sheet ``index`` (0-based) active and re-clamp the cursor.

        No undo checkpoint is pushed — moving between tabs is navigation, not a
        mutation. Returns ``True`` on success, ``False`` for an out-of-range
        index (with an explanatory ``message``)."""
        wb = self.doc.workbook
        n = len(wb.sheets)
        if not 0 <= index < n:
            self.message = f"no sheet {index + 1} (1..{n})"
            return False
        wb.active = index
        self._reclamp()  # the new sheet may have a smaller used extent
        self.message = f"sheet {index + 1}/{n}: {self.sheet.name}"
        return True

    def next_sheet(self, step: int = 1) -> None:
        """Move to the next (``step``>0) or previous (``step``<0) sheet, wrapping."""
        wb = self.doc.workbook
        n = len(wb.sheets)
        if n <= 1:
            self.message = "only one sheet"
            return
        self.switch_sheet((wb.active + step) % n)

    def goto_sheet(self, token: str) -> None:
        """Switch by 1-based index (``:sheet 2``) or by name (``:sheet Data``)."""
        wb = self.doc.workbook
        token = token.strip()
        if not token:
            self.message = "usage: :sheet <name|index>   (see :sheets)"
            return
        if token.isdigit():
            self.switch_sheet(int(token) - 1)  # user indices are 1-based
            return
        for i, s in enumerate(wb.sheets):
            if s.name == token:
                self.switch_sheet(i)
                return
        self.message = f"no sheet named {token!r}"

    def list_sheets(self) -> None:
        """Populate ``message`` with the tab list, marking the active one with ``*``."""
        wb = self.doc.workbook
        parts = []
        for i, s in enumerate(wb.sheets):
            mark = "*" if i == wb.active else " "
            parts.append(f"{mark}{i + 1}:{s.name}")
        self.message = "sheets: " + "  ".join(parts)

    # --- help overlay -----------------------------------------------------

    def _open_help(self) -> None:
        self.help_idx = 0
        self.mode = "help"

    def help_move(self, step: int) -> None:
        n = len(HELP_ENTRIES)
        if n:
            self.help_idx = max(0, min(self.help_idx + step, n - 1))

    def _handle_convert(self, args: list[str]) -> None:
        from ..core.science.units import UnitError, convert

        if len(args) != 3:
            self.message = "usage: :convert <value> <from> <to>"
            return
        try:
            result = convert(float(args[0]), args[1], args[2])
            self.message = f"{args[0]} {args[1]} = {result:.10g} {args[2]}"
        except (UnitError, ValueError) as exc:
            self.message = f"convert: {exc}"

    def _handle_fmt(self, args: list[str]) -> None:
        from ..core.format.cellformat import FORMATS
        from ..core.reference import parse_range

        if not args:
            self.message = "fmt specs: " + " ".join(s for s, _ in FORMATS)
            return
        spec = args[0]
        rng = args[1] if len(args) > 1 else self.cursor_a1()
        try:
            r1, c1, r2, c2 = parse_range(rng)
        except Exception as exc:
            self.message = f"fmt: {exc}"
            return
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if spec == "general":
                    self.sheet.cell_formats.pop((r, c), None)
                else:
                    self.sheet.cell_formats[(r, c)] = spec
        self.doc.mark_dirty()
        self.message = f"format {spec} over {rng}"

    _RANGE_ARG = None

    def _is_range_arg(self, arg: str) -> bool:
        """True when ``arg`` looks like an A1 cell/range (e.g. ``A1`` or ``A1:A50``)."""
        import re

        if TuiEditor._RANGE_ARG is None:
            TuiEditor._RANGE_ARG = re.compile(r"^\$?[A-Za-z]{1,3}\$?\d+(:\$?[A-Za-z]{1,3}\$?\d+)?$")
        return bool(TuiEditor._RANGE_ARG.match(arg.strip()))

    def _handle_plot(self, args: list[str]) -> None:
        from ..core.graphing import GraphError, sample

        if not args:
            self.message = "usage: :plot <expr> [xmin xmax]  |  :plot A1:A50 [B1:B50]"
            return
        # Range form: :plot A1:A50  (y vs index) or :plot A1:A50 B1:B50  (x, y).
        if self._is_range_arg(args[0]):
            self._plot_ranges(args)
            return
        try:
            xmin = float(args[1]) if len(args) > 1 else -6.283185
            xmax = float(args[2]) if len(args) > 2 else 6.283185
            self.plot_pts = sample(args[0], xmin, xmax, 240)
        except (GraphError, ValueError, IndexError) as exc:
            self.message = f"plot: {exc}"
            return
        self.plot_expr = args[0]
        self.plot_bounds = None
        self.mode = "plot"

    def _range_numbers(self, rng: str) -> list[float | None]:
        """Read a range's cells in row-major order as floats (None for non-numeric)."""
        from ..core.reference import parse_range

        r1, c1, r2, c2 = parse_range(rng)
        out: list[float | None] = []
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                v = self.sheet.get_value(r, c)
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    out.append(None)
                else:
                    out.append(float(v))
        return out

    def _range_block(self, rng: str) -> list[list[str]]:
        """Read a range as a 2-D block of *raw string* cells (row-major).

        The shape :mod:`abax.core.pivot` expects: ``rows[0]`` is the header and
        the remaining rows are data. Cells are the raw text (a formula stays a
        formula string); use :meth:`_range_numbers` when you need computed
        numbers instead.
        """
        from ..core.reference import parse_range

        r1, c1, r2, c2 = parse_range(rng)
        return [[self.sheet.get_raw(r, c) for c in range(c1, c2 + 1)]
                for r in range(r1, r2 + 1)]

    def _handle_pivot(self, args: list[str]) -> None:
        """``:pivot <range> <index> <column> <value> [agg] [dest]`` — group/pivot.

        Treats ``range`` as a table whose first row is the header, then reuses
        :func:`abax.core.pivot.pivot_table` (columns are addressed by header
        *name*, per that contract). ``index`` runs down the left, distinct
        ``column`` values across the top, each body cell the ``agg`` (default
        ``sum``) of ``value``. The result block is written into the sheet at
        ``dest`` (default: two rows below the source range), under an undo
        checkpoint, and the cursor jumps there.
        """
        from ..core.pivot import AGGREGATIONS, PivotError, pivot_table
        from ..core.reference import parse_a1, parse_range

        if len(args) < 4:
            self.message = ("usage: :pivot <range> <index> <column> <value> "
                            "[agg] [dest]   (aggs: " + " ".join(AGGREGATIONS) + ")")
            return
        rng, index_col, column_col, value_col = args[0], args[1], args[2], args[3]
        agg = "sum"
        dest = None
        for a in args[4:]:
            if a in AGGREGATIONS:
                agg = a
            elif self._is_range_arg(a):
                dest = a
            else:
                self.message = f"pivot: unknown aggregation or dest {a!r}"
                return
        try:
            block = self._range_block(rng)
            result = pivot_table(block, index_col, column_col, value_col, agg=agg)
        except PivotError as exc:
            self.message = f"pivot: {exc}"
            return
        except Exception as exc:  # bad range, etc.
            self.message = f"pivot: {exc}"
            return
        # Default destination: two blank rows below the source block.
        try:
            if dest is not None:
                dr, dc = parse_a1(dest)
            else:
                _, c1, r2, _ = parse_range(rng)
                dr, dc = r2 + 2, c1
        except Exception as exc:
            self.message = f"pivot: bad dest: {exc}"
            return
        self.doc.checkpoint(f"pivot {rng}")
        for i, row in enumerate(result):
            for j, text in enumerate(row):
                self.sheet.set_cell(dr + i, dc + j, text)
                self.recorder.record_set(to_a1(dr + i, dc + j), text)
        self.doc.mark_dirty()
        self.row, self.col = dr, dc
        self._reclamp()
        self.announce()
        self.message = (f"pivot {agg}({value_col}) of {index_col} x {column_col} "
                        f"-> {to_a1(dr, dc)} ({len(result)}x{len(result[0])})")

    def _plot_ranges(self, args: list[str]) -> None:
        try:
            first = self._range_numbers(args[0])
            if len(args) > 1 and self._is_range_arg(args[1]):
                # (x, y): first range is x, second is y.
                second = self._range_numbers(args[1])
                pts = [(x, y) for x, y in zip(first, second) if x is not None]
                self.plot_expr = f"{args[1]} vs {args[0]}"
            else:
                # y vs implicit index 0,1,2,…
                pts = [(float(i), y) for i, y in enumerate(first)]
                self.plot_expr = args[0]
        except Exception as exc:
            self.message = f"plot: {exc}"
            return
        finite = [(x, y) for (x, y) in pts if y is not None]
        if not finite:
            self.message = "plot: no numeric data in range"
            return
        xs = [x for x, _ in finite]
        yvals = [y for _, y in finite]
        self.plot_pts = pts
        self.plot_bounds = (min(xs), max(xs), min(yvals), max(yvals))
        self.mode = "plot"

    def _handle_describe(self, args: list[str]) -> None:
        """``:describe A1:A50`` — descriptive stats over a range's numeric cells.

        Reuses :func:`abax.core.science.descriptive.describe` for the math and
        renders a compact summary on the status line. A bad or empty range is
        reported gracefully rather than raising.

        ``:describe full <range>`` (also ``:desc full …``) opens a scrollable
        overlay with the *complete* spread of measures instead of the one-line
        headline — see :meth:`_open_describe`.
        """
        from ..core.science.descriptive import describe

        if args and args[0] in ("full", "all", "+"):
            self._open_describe(args[1] if len(args) > 1 else self.cursor_a1())
            return

        rng = args[0] if args else self.cursor_a1()
        try:
            values = self._range_numbers(rng)
        except Exception as exc:
            self.describe_summary = None
            self.message = f"describe: {exc}"
            return
        # _range_numbers yields None for non-numeric cells; describe() already
        # drops None / non-finite entries, so hand it the raw column.
        summary = describe(values)
        self.describe_summary = summary
        if not summary["count"]:
            self.message = f"describe {rng}: no numeric data"
            return
        self.message = self._describe_text(rng, summary)

    @staticmethod
    def _describe_text(rng: str, summary: dict) -> str:
        """One-line rendering of a :func:`describe` summary for the status bar.

        Quartiles (``Q1``/``Q3``) and ``stdev`` are only appended when defined
        for the sample (small samples leave them ``None``).
        """
        parts = [f"n={summary['count']}",
                 f"mean={_fmt_num(summary['mean'])}",
                 f"median={_fmt_num(summary['median'])}"]
        if summary["stdev"] is not None:
            parts.append(f"stdev={_fmt_num(summary['stdev'])}")
        parts.append(f"min={_fmt_num(summary['min'])}")
        if summary["Q1"] is not None:
            parts.append(f"Q1={_fmt_num(summary['Q1'])}")
        if summary["Q3"] is not None:
            parts.append(f"Q3={_fmt_num(summary['Q3'])}")
        parts.append(f"max={_fmt_num(summary['max'])}")
        return f"{rng}  " + "  ".join(parts)

    # --- descriptive-stats overlay (:describe full) -----------------------

    # Order + human labels for the full overlay. Mirrors the keys returned by
    # core.science.descriptive.describe (whose FIELDS is the source of truth);
    # split into two groups with a blank spacer for readability.
    _DESCRIBE_ROWS: tuple[tuple[str, str], ...] = (
        ("count", "Count"),
        ("sum", "Sum"),
        ("mean", "Mean"),
        ("median", "Median"),
        ("mode", "Mode"),
        ("", ""),
        ("min", "Minimum"),
        ("Q1", "Q1 (25%)"),
        ("Q3", "Q3 (75%)"),
        ("max", "Maximum"),
        ("range", "Range"),
        ("", ""),
        ("variance", "Variance (sample)"),
        ("stdev", "Std dev (sample)"),
        ("variance_pop", "Variance (pop.)"),
        ("stdev_pop", "Std dev (pop.)"),
        ("", ""),
        ("skewness", "Skewness"),
        ("kurtosis", "Kurtosis (excess)"),
    )

    def _open_describe(self, rng: str) -> None:
        """Build and show the scrollable full descriptive-stats overlay.

        Computes :func:`~abax.core.science.descriptive.describe` over ``rng`` and
        stores every measure as ``(label, value)`` rows for the renderer. A bad
        range, or one with no numeric data, reports on the status line and does
        *not* enter the overlay.
        """
        from ..core.science.descriptive import describe

        try:
            values = self._range_numbers(rng)
        except Exception as exc:
            self.describe_summary = None
            self.message = f"describe: {exc}"
            return
        summary = describe(values)
        self.describe_summary = summary
        if not summary["count"]:
            self.message = f"describe {rng}: no numeric data"
            return
        self.describe_range = rng
        self.describe_lines = self._describe_full_lines(summary)
        self.describe_idx = 0
        self.mode = "describe"
        if self.speak_on_move:
            self.speak(f"Descriptive statistics for {rng}, "
                       f"{summary['count']} values")

    def _describe_full_lines(self, summary: dict) -> list[tuple[str, str]]:
        """Render a describe() summary as ordered ``(label, value)`` overlay rows.

        Undefined measures (``None`` for small samples) show an em dash rather
        than being dropped, so the panel layout is stable across sample sizes.
        Blank spacer rows in :data:`_DESCRIBE_ROWS` pass through as ``("", "")``.
        """
        rows: list[tuple[str, str]] = []
        for key, label in self._DESCRIBE_ROWS:
            if not key:
                rows.append(("", ""))
                continue
            val = summary.get(key)
            if key == "count":
                rows.append((label, str(val)))
            elif val is None:
                rows.append((label, "—"))
            else:
                rows.append((label, _fmt_num(val)))
        return rows

    def describe_move(self, step: int) -> None:
        """Scroll the describe overlay, clamped to its row range."""
        n = len(self.describe_lines)
        if n:
            self.describe_idx = max(0, min(self.describe_idx + step, n - 1))

    def _handle_eq(self, latex: str) -> None:
        if not latex:
            self.message = "usage: :eq <latex>   e.g. :eq \\frac{a}{b}"
            return
        from ..core.latexmath import to_unicode

        self.message = "eq: " + to_unicode(latex)

    def _py_namespace(self) -> dict:
        if getattr(self, "_py_ns", None) is None:
            sheet = lambda: self.sheet  # noqa: E731
            self._py_ns = {
                "doc": self.doc,
                "wb": self.doc.workbook,
                "sheet": sheet,
                "cell": lambda ref: self.sheet.get(ref),
                "put": lambda ref, v: self.sheet.set(ref, v if isinstance(v, str) else str(v)),
                "__name__": "abax_console",
            }
        return self._py_ns

    def _handle_py(self, src: str) -> None:
        import contextlib
        import io

        if not src:
            self.message = "usage: :py <python>   e.g. :py put('A1', sum(range(10)))"
            return
        ns = self._py_namespace()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                try:
                    result = eval(src, ns)  # noqa: S307 - trusted scripting, not sandboxed
                    if result is not None:
                        print(repr(result))
                except SyntaxError:
                    exec(src, ns)  # noqa: S102
        except Exception as exc:
            self.message = f"py: {type(exc).__name__}: {exc}"
            return
        self.doc.mark_dirty()
        out = buf.getvalue().strip().replace("\n", " ")
        self.message = f"py: {out}" if out else "py: ok"

    # --- RPN calculator ---------------------------------------------------

    def _ensure_rpn(self):
        if self.rpn is None:
            from ..core.calc.rpn import RPN

            self.rpn = RPN()
        return self.rpn

    def _handle_rpn_cmd(self, args: list[str]) -> None:
        from ..core.calc.rpn import RPNError

        rpn = self._ensure_rpn()
        if args:  # one-shot evaluation
            try:
                rpn.eval_line(" ".join(args))
            except RPNError as exc:
                self.message = f"rpn: {exc}"
                return
            self.message = f"X = {_fmt_num(rpn.x)}"
            return
        self.mode = "rpn"  # interactive REPL
        self.rpn_input = ""

    def rpn_eval(self) -> None:
        """Evaluate the rpn input line, or run a cell-interop command."""
        from ..core.calc.rpn import RPNError

        rpn = self._ensure_rpn()
        line = self.rpn_input.strip()
        self.rpn_input = ""
        if line in ("<", "cell"):  # pull active cell value onto the stack
            val = self.sheet.get_value(self.row, self.col)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                rpn.push(float(val))
            else:
                self.message = "cell is not a number"
            return
        if line in (">", "store"):  # write X to the active cell
            self.sheet.set_cell(self.row, self.col, _fmt_num(rpn.x))
            self.doc.mark_dirty()
            self.message = f"wrote {_fmt_num(rpn.x)} to {self.cursor_a1()}"
            return
        if not line:
            return
        try:
            rpn.eval_line(line)
        except RPNError as exc:
            self.message = f"rpn: {exc}"

    # --- clipboard history ------------------------------------------------

    def _paste_clip_history(self, args: list[str]) -> None:
        from ..core.fill import clip_from_tsv, paste_clip

        if not args or not args[0].isdigit():
            self.message = "usage: :clip <index>  (see :clips)"
            return
        entry = self.clips.get(int(args[0]))
        if entry is None:
            self.message = "no such clip"
            return
        self.doc.checkpoint(f"paste clip {args[0]}")
        clip = clip_from_tsv(entry.text, (self.row, self.col))
        paste_clip(self.sheet, clip, (self.row, self.col), mode="absolute",
                   on_set=self.recorder.record_set)
        self.doc.mark_dirty()
        self.message = f"pasted clip {args[0]}"

    # --- search / replace -------------------------------------------------

    def _handle_find(self, args: list[str]) -> None:
        from ..core.search import SearchError, SearchOptions, find_all

        if not args:
            self.message = "usage: :find <pattern>"
            return
        try:
            self.matches = find_all(self.sheet, args[0], SearchOptions(regex=True))
        except SearchError as exc:
            self.message = f"bad pattern: {exc}"
            return
        self.match_idx = 0
        if self.matches:
            self._goto_match()
            self.message = f"{len(self.matches)} match(es) — n/N to navigate"
        else:
            self.message = "no matches"

    def _goto_match(self) -> None:
        if not self.matches:
            return
        m = self.matches[self.match_idx % len(self.matches)]
        self.row, self.col = m.row, m.col
        self._reclamp()

    def next_match(self, step: int) -> None:
        if not self.matches:
            self.message = "no active search (use :find)"
            return
        self.match_idx = (self.match_idx + step) % len(self.matches)
        self._goto_match()
        self.message = f"match {self.match_idx + 1}/{len(self.matches)}"

    def _handle_replace(self, args: list[str]) -> None:
        from ..core.search import SearchError, SearchOptions, replace_all

        if len(args) < 2:
            self.message = "usage: :replace <pattern> <replacement>  (or :s/pat/repl/)"
            return
        self.doc.checkpoint("replace")
        try:
            n = replace_all(self.sheet, args[0], args[1], SearchOptions(regex=True),
                            on_set=self.recorder.record_set)
        except SearchError as exc:
            self.message = f"bad pattern: {exc}"
            return
        self.doc.mark_dirty()
        self.message = f"replaced in {n} cell(s)"

    def _handle_substitute(self, raw: str) -> None:
        from ..core.search import SearchError, SearchOptions, replace_all

        body = raw[2:] if raw.startswith("s/") else raw[3:]  # drop 's/' or '%s/'
        parts = body.split("/")
        if len(parts) < 2:
            self.message = "usage: :s/pattern/replacement/[i]"
            return
        pat, repl = parts[0], parts[1]
        flags = parts[2] if len(parts) > 2 else ""
        opts = SearchOptions(regex=True, case_sensitive=("i" not in flags))
        self.doc.checkpoint("substitute")
        try:
            n = replace_all(self.sheet, pat, repl, opts, on_set=self.recorder.record_set)
        except SearchError as exc:
            self.message = f"bad pattern: {exc}"
            return
        self.doc.mark_dirty()
        self.message = f"replaced in {n} cell(s)"

    def _handle_theme(self, args: list[str]) -> None:
        if not args or args[0] not in THEMES:
            self.message = "themes: " + ", ".join(sorted(THEMES))
            return
        self.theme_name = args[0]
        self.message = f"theme: {args[0]}"

    # --- function browser -------------------------------------------------

    def _open_browser(self, filt: str) -> None:
        from ..core.completion import function_names

        up = filt.upper()
        self.browser = [n for n in function_names() if up in n]
        self.browser_idx = 0
        self.mode = "browser"
        if not self.browser:
            self.mode = "normal"
            self.message = f"no functions match {filt!r}"

    def browser_move(self, step: int) -> None:
        if self.browser:
            self.browser_idx = max(0, min(self.browser_idx + step, len(self.browser) - 1))

    def browser_insert(self) -> None:
        if self.browser:
            name = self.browser[self.browser_idx]
            self.mode = "insert"
            self.edit_buf = f"={name}("
            self.refresh_completions()

    def _handle_copy(self, args: list[str]) -> None:
        from ..core.fill import copy_region, region_to_tsv

        rng = args[0] if args else self.cursor_a1()
        try:
            self.clip = copy_region(self.sheet, rng)
            self.clips.add(region_to_tsv(self.sheet, rng))
        except Exception as exc:
            self.message = f"copy error: {exc}"
            return
        self.message = f"copied {self.clip.nrows}x{self.clip.ncols} from {rng}"

    def _handle_paste(self, args: list[str]) -> None:
        from ..core.fill import paste_clip

        if self.clip is None:
            self.message = "nothing to paste (use :copy first)"
            return
        dest = args[0] if args else self.cursor_a1()
        self.doc.checkpoint(f"paste {dest}")
        paste_clip(self.sheet, self.clip, dest, on_set=self.recorder.record_set)
        self.doc.mark_dirty()
        self.message = f"pasted at {dest}"

    def _handle_fill(self, args: list[str]) -> None:
        from ..core.fill import fill_down, fill_right, fill_series

        if len(args) < 2:
            self.message = "usage: :fill down|right|series <range>"
            return
        kind, rng = args[0], args[1]
        fn = {"down": fill_down, "right": fill_right, "series": fill_series}.get(kind)
        if fn is None:
            self.message = "fill: down | right | series"
            return
        self.doc.checkpoint(f"fill {kind} {rng}")
        try:
            fn(self.sheet, rng, on_set=self.recorder.record_set)
        except Exception as exc:
            self.message = f"fill error: {exc}"
            return
        self.doc.mark_dirty()
        self.message = f"filled {kind} over {rng}"

    def _handle_sort(self, args: list[str]) -> None:
        from ..core.fill import sort_region
        from ..core.reference import col_to_index

        if not args:
            self.message = "usage: :sort <range> [keycol] [desc]"
            return
        rng = args[0]
        key_col = None
        descending = False
        for a in args[1:]:
            if a.lower() in ("desc", "descending", "rev"):
                descending = True
            elif a.isalpha():
                key_col = col_to_index(a)
        self.doc.checkpoint(f"sort {rng}")
        try:
            sort_region(self.sheet, rng, key_col, descending=descending,
                        on_set=self.recorder.record_set)
        except Exception as exc:
            self.message = f"sort error: {exc}"
            return
        self.doc.mark_dirty()
        self.message = f"sorted {rng}" + (" desc" if descending else "")

    def _handle_record(self, args: list[str]) -> None:
        sub = args[0] if args else "toggle"
        if sub == "toggle":
            on = self.recorder.toggle()
            self.message = "● recording" if on else f"recorded {self.recorder.count} action(s)"
        elif sub in ("rel", "relative"):
            self.recorder.start(relative=True)
            self.message = "● recording (relative)"
        elif sub == "start":
            relative = "rel" in args[1:] or "relative" in args[1:]
            name = next((a for a in args[1:] if a not in ("rel", "relative")), "")
            self.recorder.start(name, relative=relative)
            self.message = "● recording" + (" (relative)" if relative else "")
        elif sub == "stop":
            self.recorder.stop()
            self.message = f"recorded {self.recorder.count} action(s)"
        elif sub == "replay":
            self.recorder.replay(self.doc.workbook, at=(self.row, self.col))
            self.doc.mark_dirty()
            where = f" at {self.cursor_a1()}" if self.recorder.relative else ""
            self.message = f"replayed {self.recorder.count} action(s){where}"
        elif sub == "save":
            if len(args) < 2:
                self.message = "usage: :rec save <path.py>"
                return
            saved = self.recorder.save_macro(args[1])
            if self.registry is not None:
                from ..macros import load_macro_file

                try:
                    load_macro_file(saved, self.registry)  # immediately runnable
                except Exception as exc:  # pragma: no cover - defensive
                    self.message = f"saved {saved} (reload failed: {exc})"
                    return
            self.message = f"saved macro {saved} ({self.recorder.count} action(s))"
        else:
            self.message = "rec: toggle | start [name] | stop | save <path> | replay"

    def _run_macro(self, name: str) -> None:
        if not self.registry or not name:
            self.message = "usage: :macro <name>"
            return
        from ..macros import MacroError, run_macro

        try:
            ctx = run_macro(self.registry, name, self.doc.workbook, cursor=(self.row, self.col))
        except MacroError as exc:
            self.message = str(exc)
            return
        self.doc.mark_dirty()
        tail = f" — {ctx.messages[-1]}" if ctx.messages else ""
        self.message = f"ran macro {name}{tail}"

    def dispatch_normal(self, ch: str) -> None:
        """Handle a normal-mode keystroke (single character)."""
        if ch in ("h",):
            self.move(0, -1)
        elif ch in ("l",):
            self.move(0, 1)
        elif ch in ("j",):
            self.move(1, 0)
        elif ch in ("k",):
            self.move(-1, 0)
        elif ch == "g":
            self.row = 0
            self._reclamp()
            self.announce()
        elif ch == "G":
            n_rows, _ = self.sheet.used_bounds()
            self.row = max(0, n_rows - 1)
            self._reclamp()
            self.announce()
        elif ch == "0":
            self.col = 0
            self._reclamp()
            self.announce()
        elif ch == "n":  # next search match
            self.next_match(1)
        elif ch == "N":  # previous search match
            self.next_match(-1)
        elif ch in ("i", "a"):  # enter edit mode (vim insert/append)
            self.begin_insert()
        elif ch == "v":  # visual (cell-range) selection
            self.begin_visual(line=False)
        elif ch == "V":  # visual-line (whole-row) selection
            self.begin_visual(line=True)
        elif ch == ":":
            self.begin_command()
        elif ch == "x":
            self.doc.checkpoint(f"clear {self.cursor_a1()}")
            self.sheet.set_cell(self.row, self.col, "")
            self.recorder.record_clear(self.cursor_a1())
            self.doc.mark_dirty()
        elif ch == "u":  # undo
            self.do_undo()
        elif ch == "\x12":  # Ctrl-R — redo
            self.do_redo()
        elif ch == "?":  # help overlay
            self._open_help()
        elif ch == "y":  # yank current cell
            from ..core.fill import copy_region, region_to_tsv

            self.clip = copy_region(self.sheet, self.cursor_a1())
            self.clips.add(region_to_tsv(self.sheet, self.cursor_a1()))
            self.message = f"yanked {self.cursor_a1()}"
        elif ch == "p":  # paste at cursor
            if self.clip is not None:
                from ..core.fill import paste_clip

                self.doc.checkpoint(f"paste {self.cursor_a1()}")
                paste_clip(self.sheet, self.clip, self.cursor_a1(),
                           on_set=self.recorder.record_set)
                self.doc.mark_dirty()
                self.message = f"pasted at {self.cursor_a1()}"

    # --- visual selection mode -------------------------------------------

    def begin_visual(self, *, line: bool = False) -> None:
        """Enter visual (``v``) or visual-line (``V``) mode.

        The current cell becomes the *anchor*; subsequent movement extends the
        selection from it. The live selection aggregate is shown immediately.
        """
        self.anchor_row, self.anchor_col = self.row, self.col
        self.mode = "visual-line" if line else "visual"
        self.message = self._visual_aggregate_text()

    def cancel_visual(self) -> None:
        """Leave visual mode without acting on the selection (``Esc``)."""
        self.mode = "normal"
        self.message = ""

    def visual_bounds(self) -> tuple[int, int, int, int]:
        """``(r1, c1, r2, c2)`` for the active selection, normalized r1<=r2 etc.

        In visual-line mode the columns span the whole used width so the
        selection always covers complete rows.
        """
        r1, r2 = sorted((self.anchor_row, self.row))
        if self.mode == "visual-line":
            _, n_cols = self.sheet.used_bounds()
            c1, c2 = 0, max(0, n_cols - 1)
        else:
            c1, c2 = sorted((self.anchor_col, self.col))
        return r1, c1, r2, c2

    def visual_aggregate(self) -> tuple[float, int, float | None]:
        """``(sum, count, average)`` over the numeric cells of the selection.

        ``count`` is the number of numeric (non-blank, non-bool) cells; the
        average is ``None`` when there are none.
        """
        r1, c1, r2, c2 = self.visual_bounds()
        total = 0.0
        count = 0
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                val = self.sheet.get_value(r, c)
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    total += float(val)
                    count += 1
        avg = (total / count) if count else None
        return total, count, avg

    def _visual_aggregate_text(self) -> str:
        r1, c1, r2, c2 = self.visual_bounds()
        rng = f"{to_a1(r1, c1)}:{to_a1(r2, c2)}"
        total, count, avg = self.visual_aggregate()
        if not count:
            return f"{rng}  count=0"
        return (f"{rng}  sum={_fmt_num(total)}  count={count}  "
                f"avg={_fmt_num(avg)}")

    def visual_refresh(self) -> None:
        """Recompute the status-line aggregate after the selection moved."""
        self.message = self._visual_aggregate_text()

    def visual_yank(self) -> None:
        """Copy the selection to the clipboard/registers, then leave visual mode."""
        from ..core.fill import copy_region, region_to_tsv

        rng = self.visual_bounds()
        self.clip = copy_region(self.sheet, rng)
        self.clips.add(region_to_tsv(self.sheet, rng))
        r1, c1, r2, c2 = rng
        label = f"{to_a1(r1, c1)}:{to_a1(r2, c2)}"
        self.mode = "normal"
        self.message = f"yanked {label}"

    def visual_delete(self) -> None:
        """Clear the selected cells with an undo checkpoint, then leave visual mode."""
        r1, c1, r2, c2 = self.visual_bounds()
        label = f"{to_a1(r1, c1)}:{to_a1(r2, c2)}"
        self.doc.checkpoint(f"delete {label}")
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if self.sheet.get_raw(r, c):
                    self.sheet.set_cell(r, c, "")
                    self.recorder.record_clear(to_a1(r, c))
        self.doc.mark_dirty()
        self.mode = "normal"
        self.message = f"cleared {label}"
