"""The headless TUI editor state machine — cursor, modes, and command dispatch.

The curses front-end drives this; tests can drive it directly.
"""

from __future__ import annotations

from .commands import _fmt_num, parse_command
from .themes import THEMES
from ..core.reference import to_a1


class TuiEditor:
    """Headless spreadsheet editor state: cursor + mode + sheet.

    The curses front-end drives this; tests can drive it directly.
    """

    def __init__(self, document, registry=None) -> None:
        from ..recorder import MacroRecorder

        self.doc = document
        self.registry = registry
        self.recorder = MacroRecorder()
        self.row = 0
        self.col = 0
        self.mode = "normal"  # normal | insert | command | browser
        self.command_buf = ""
        self.edit_buf = ""
        self.completions: list[str] = []
        self.arg_hint = ""
        self.clip = None  # last copied region (core.fill.Clip)
        self.matches: list = []  # search hits (core.search.Match)
        self.match_idx = 0
        self.browser: list[str] = []  # function-browser entries when mode == browser
        self.browser_idx = 0
        self.theme_name = "obsidian"  # live TUI theme (changeable via :theme)
        from ..core.clipboard import ClipboardManager

        self.clips = ClipboardManager()  # text copy history
        self.rpn = None  # core.calc.rpn.RPN, lazily created
        self.rpn_input = ""  # input buffer when mode == rpn
        self.plot_pts: list = []  # sampled points when mode == plot
        self.plot_expr = ""
        self.message = ""
        self.running = True

    @property
    def sheet(self):
        return self.doc.workbook.sheet

    def move(self, dr: int, dc: int) -> None:
        self.row = max(0, self.row + dr)
        self.col = max(0, self.col + dc)

    def cursor_a1(self) -> str:
        return to_a1(self.row, self.col)

    def begin_insert(self) -> None:
        self.mode = "insert"
        self.edit_buf = self.sheet.get_raw(self.row, self.col)

    def commit_insert(self) -> None:
        self.sheet.set_cell(self.row, self.col, self.edit_buf)
        self.recorder.record_set(self.cursor_a1(), self.edit_buf)
        self.doc.mark_dirty()
        self.mode = "normal"
        self.completions = []
        self.arg_hint = ""

    def refresh_completions(self) -> None:
        """Recompute candidate names and the active-call arg hint for the buffer."""
        from ..core.completion import complete, format_hint, signature_hint

        cursor = len(self.edit_buf)
        self.completions = complete(self.edit_buf, cursor)
        hint = signature_hint(self.edit_buf, cursor)
        self.arg_hint = format_hint(hint) if hint else ""

    def complete(self) -> None:
        """Tab-completion: single match inserts ``NAME(``; many → common prefix."""
        from ..core.completion import apply_completion, common_prefix, complete, current_token

        cands = complete(self.edit_buf, len(self.edit_buf))
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
        elif cmd == "eq":
            self._handle_eq(raw[2:].strip() if raw.startswith("eq") else "")
        elif cmd == "convert":
            self._handle_convert(args)
        else:
            self.message = f"unknown command: {cmd}"

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

    def _handle_plot(self, args: list[str]) -> None:
        from ..core.graphing import GraphError, sample

        if not args:
            self.message = "usage: :plot <expr> [xmin xmax]"
            return
        try:
            xmin = float(args[1]) if len(args) > 1 else -6.283185
            xmax = float(args[2]) if len(args) > 2 else 6.283185
            self.plot_pts = sample(args[0], xmin, xmax, 240)
        except (GraphError, ValueError, IndexError) as exc:
            self.message = f"plot: {exc}"
            return
        self.plot_expr = args[0]
        self.mode = "plot"

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
                "__name__": "qcell_console",
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
        elif ch == "G":
            n_rows, _ = self.sheet.used_bounds()
            self.row = max(0, n_rows - 1)
        elif ch == "0":
            self.col = 0
        elif ch == "n":  # next search match
            self.next_match(1)
        elif ch == "N":  # previous search match
            self.next_match(-1)
        elif ch == "i":
            self.begin_insert()
        elif ch == ":":
            self.begin_command()
        elif ch == "x":
            self.sheet.set_cell(self.row, self.col, "")
            self.recorder.record_clear(self.cursor_a1())
            self.doc.mark_dirty()
        elif ch == "y":  # yank current cell
            from ..core.fill import copy_region, region_to_tsv

            self.clip = copy_region(self.sheet, self.cursor_a1())
            self.clips.add(region_to_tsv(self.sheet, self.cursor_a1()))
            self.message = f"yanked {self.cursor_a1()}"
        elif ch == "p":  # paste at cursor
            if self.clip is not None:
                from ..core.fill import paste_clip

                paste_clip(self.sheet, self.clip, self.cursor_a1(),
                           on_set=self.recorder.record_set)
                self.doc.mark_dirty()
                self.message = f"pasted at {self.cursor_a1()}"
