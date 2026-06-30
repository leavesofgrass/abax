"""Curses TUI — vim-first, SSH-safe, degrades to ASCII + 8-color / mono.

Pure-logic helpers (terminal detection, command parsing, theme allocation) are
module-level functions so they can be unit-tested without a real terminal
(spec §12: test command parse / theme allocation / vim dispatch). The curses
loop itself lives in :func:`run_tui`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .core.reference import index_to_col, to_a1

# --- capability detection (testable) --------------------------------------


def detect_terminal(has_colors: bool = True, colors: int = 256) -> str:
    """Return 'full' | '256' | '8' | 'mono'. Pure: pass capabilities in."""
    colorterm = os.environ.get("COLORTERM", "")
    term = os.environ.get("TERM", "")
    if not has_colors:
        return "mono"
    if colorterm in ("truecolor", "24bit") or "256color" in term:
        return "256"
    if colors >= 8:
        return "8"
    return "mono"


def is_ssh() -> bool:
    return bool(os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"))


def can_use_powerline(cap: str) -> bool:
    """Powerline glyphs need a Nerd Font AND a non-SSH terminal."""
    return cap == "256" and not is_ssh()


# --- theme (role -> (index256, index8)) -----------------------------------


@dataclass(frozen=True)
class TuiTheme:
    name: str
    roles: dict  # role -> (index256, index8)

    def color(self, role: str, cap: str) -> int:
        idx256, idx8 = self.roles.get(role, (7, 7))
        return idx256 if cap == "256" else idx8


THEMES = {
    "mono": TuiTheme("mono", {}),  # attribute-only
    "obsidian": TuiTheme(
        "obsidian",
        {
            "lcd": (189, 7),
            "frame": (240, 7),
            "label": (146, 6),
            "dim": (244, 7),
            "accent": (99, 5),
            "banner": (183, 5),
            "cursor": (99, 3),
        },
    ),
    "hacker": TuiTheme(
        "hacker",
        {
            "lcd": (46, 2),
            "frame": (22, 2),
            "label": (40, 2),
            "dim": (28, 2),
            "accent": (118, 2),
            "banner": (46, 2),
            "cursor": (46, 2),
        },
    ),
    "phosphor": TuiTheme(
        "phosphor",
        {
            "lcd": (214, 3),
            "frame": (130, 3),
            "label": (208, 3),
            "dim": (94, 3),
            "accent": (220, 3),
            "banner": (214, 3),
            "cursor": (214, 3),
        },
    ),
    "solarized": TuiTheme(
        "solarized",
        {
            "lcd": (245, 7), "frame": (240, 7), "label": (33, 4), "dim": (240, 7),
            "accent": (33, 4), "banner": (100, 2), "cursor": (33, 4),
        },
    ),
    "nord": TuiTheme(
        "nord",
        {
            "lcd": (188, 7), "frame": (240, 7), "label": (110, 6), "dim": (244, 7),
            "accent": (110, 6), "banner": (151, 6), "cursor": (67, 4),
        },
    ),
    "dark_one": TuiTheme(
        "dark_one",
        {
            "lcd": (250, 7), "frame": (240, 7), "label": (75, 4), "dim": (243, 7),
            "accent": (75, 4), "banner": (114, 2), "cursor": (75, 4),
        },
    ),
    "crt_green": TuiTheme(
        "crt_green",
        {
            "lcd": (48, 2), "frame": (22, 2), "label": (40, 2), "dim": (28, 2),
            "accent": (83, 2), "banner": (48, 2), "cursor": (48, 2),
        },
    ),
    "crt_amber": TuiTheme(
        "crt_amber",
        {
            "lcd": (214, 3), "frame": (130, 3), "label": (208, 3), "dim": (94, 3),
            "accent": (220, 3), "banner": (214, 3), "cursor": (214, 3),
        },
    ),
}


# --- command-mode parsing (testable) --------------------------------------


def _fmt_num(v) -> str:
    """Format an RPN value for the TUI display."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v:.10g}"


def parse_command(line: str) -> tuple[str, list[str]]:
    """``":w foo.csv"`` -> ``("w", ["foo.csv"])``. Leading ``:`` optional."""
    line = line.strip()
    if line.startswith(":"):
        line = line[1:]
    parts = line.split()
    if not parts:
        return "", []
    return parts[0], parts[1:]


# --- editor state machine (mostly testable) -------------------------------


class TuiEditor:
    """Headless spreadsheet editor state: cursor + mode + sheet.

    The curses front-end drives this; tests can drive it directly.
    """

    def __init__(self, document, registry=None) -> None:
        from .recorder import MacroRecorder

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
        from .core.clipboard import ClipboardManager

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
        from .core.completion import complete, format_hint, signature_hint

        cursor = len(self.edit_buf)
        self.completions = complete(self.edit_buf, cursor)
        hint = signature_hint(self.edit_buf, cursor)
        self.arg_hint = format_hint(hint) if hint else ""

    def complete(self) -> None:
        """Tab-completion: single match inserts ``NAME(``; many → common prefix."""
        from .core.completion import apply_completion, common_prefix, complete, current_token

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
            from .core.shell import run

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
        from .core.units import UnitError, convert

        if len(args) != 3:
            self.message = "usage: :convert <value> <from> <to>"
            return
        try:
            result = convert(float(args[0]), args[1], args[2])
            self.message = f"{args[0]} {args[1]} = {result:.10g} {args[2]}"
        except (UnitError, ValueError) as exc:
            self.message = f"convert: {exc}"

    def _handle_fmt(self, args: list[str]) -> None:
        from .core.cellformat import FORMATS
        from .core.reference import parse_range

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
        from .core.graphing import GraphError, sample

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
        from .core.latexmath import to_unicode

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
            from .core.calc.rpn import RPN

            self.rpn = RPN()
        return self.rpn

    def _handle_rpn_cmd(self, args: list[str]) -> None:
        from .core.calc.rpn import RPNError

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
        from .core.calc.rpn import RPNError

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
        from .core.fill import clip_from_tsv, paste_clip

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
        from .core.search import SearchError, SearchOptions, find_all

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
        from .core.search import SearchError, SearchOptions, replace_all

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
        from .core.search import SearchError, SearchOptions, replace_all

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
        from .core.completion import function_names

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
        from .core.fill import copy_region, region_to_tsv

        rng = args[0] if args else self.cursor_a1()
        try:
            self.clip = copy_region(self.sheet, rng)
            self.clips.add(region_to_tsv(self.sheet, rng))
        except Exception as exc:
            self.message = f"copy error: {exc}"
            return
        self.message = f"copied {self.clip.nrows}x{self.clip.ncols} from {rng}"

    def _handle_paste(self, args: list[str]) -> None:
        from .core.fill import paste_clip

        if self.clip is None:
            self.message = "nothing to paste (use :copy first)"
            return
        dest = args[0] if args else self.cursor_a1()
        paste_clip(self.sheet, self.clip, dest, on_set=self.recorder.record_set)
        self.doc.mark_dirty()
        self.message = f"pasted at {dest}"

    def _handle_fill(self, args: list[str]) -> None:
        from .core.fill import fill_down, fill_right, fill_series

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
        from .core.fill import sort_region
        from .core.reference import col_to_index

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
                from .macros import load_macro_file

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
        from .macros import MacroError, run_macro

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
            from .core.fill import copy_region, region_to_tsv

            self.clip = copy_region(self.sheet, self.cursor_a1())
            self.clips.add(region_to_tsv(self.sheet, self.cursor_a1()))
            self.message = f"yanked {self.cursor_a1()}"
        elif ch == "p":  # paste at cursor
            if self.clip is not None:
                from .core.fill import paste_clip

                paste_clip(self.sheet, self.clip, self.cursor_a1(),
                           on_set=self.recorder.record_set)
                self.doc.mark_dirty()
                self.message = f"pasted at {self.cursor_a1()}"


# --- curses front-end ------------------------------------------------------


def run_tui(file: str | None = None, registry=None) -> int:
    try:
        import curses
    except ImportError:  # pragma: no cover - Windows without windows-curses
        print("curses is unavailable; install 'windows-curses' on Windows.")
        return 1

    from . import _runtime as rt
    from .engine.document import Document
    from .settings import load_settings

    settings = load_settings(rt.CONFIG_DIR / "settings.json")
    doc = Document.open(file) if file else Document()
    editor = TuiEditor(doc, registry)
    theme_name = getattr(settings, "tui_theme", "obsidian")

    editor.theme_name = theme_name if theme_name in THEMES else "obsidian"

    def _main(stdscr) -> int:
        curses.curs_set(0)
        cap = detect_terminal(curses.has_colors(), curses.COLORS if curses.has_colors() else 0)
        _draw_loop(stdscr, curses, editor, cap)
        return 0

    return curses.wrapper(_main)


def _hex_to_256(hexc: str) -> int:
    """Nearest xterm-256 color index for a ``#rrggbb`` string."""
    r, g, b = int(hexc[1:3], 16), int(hexc[3:5], 16), int(hexc[5:7], 16)
    if abs(r - g) < 12 and abs(g - b) < 12:  # grayscale ramp
        if r < 8:
            return 16
        if r > 248:
            return 231
        return 232 + round((r - 8) / 247 * 24)

    def q(v: int) -> int:
        return 0 if v < 48 else 1 if v < 115 else 2 if v < 155 else 3 if v < 195 else 4 if v < 235 else 5

    return 16 + 36 * q(r) + 6 * q(g) + q(b)


def _hex_to_8(hexc: str) -> int:
    r, g, b = int(hexc[1:3], 16), int(hexc[3:5], 16), int(hexc[5:7], 16)
    return (1 if r > 127 else 0) | (2 if g > 127 else 0) | (4 if b > 127 else 0)


def _draw_loop(stdscr, curses, editor: TuiEditor, cap: str) -> None:
    state = {"name": None, "pairs": {}, "cond": {}, "next": 1, "theme": THEMES["obsidian"]}

    def rebuild(theme: TuiTheme) -> None:
        state["pairs"], state["cond"], state["next"], state["theme"] = {}, {}, 1, theme
        if cap == "mono":
            return
        for role in ("lcd", "frame", "label", "dim", "accent", "banner", "cursor"):
            try:
                curses.init_pair(state["next"], theme.color(role, cap), -1)
                state["pairs"][role] = state["next"]
                state["next"] += 1
            except curses.error:
                pass
        try:
            curses.use_default_colors()
        except curses.error:
            pass

    def attr(role: str) -> int:
        pn = state["pairs"].get(role)
        if pn is not None:
            return curses.color_pair(pn)
        return curses.A_BOLD if role in ("accent", "banner") else curses.A_NORMAL

    def cond_attr(hexc):
        if cap == "mono" or not hexc:
            return None
        idx = _hex_to_256(hexc) if cap == "256" else _hex_to_8(hexc)
        pn = state["cond"].get(idx)
        if pn is None:
            if state["next"] > min(getattr(curses, "COLOR_PAIRS", 64) - 1, 240):
                return None
            try:
                curses.init_pair(state["next"], idx, -1)
            except curses.error:
                return None
            pn = state["next"]
            state["cond"][idx] = pn
            state["next"] += 1
        return curses.color_pair(pn) | curses.A_BOLD

    while editor.running:
        if editor.theme_name != state["name"]:
            rebuild(THEMES.get(editor.theme_name, THEMES["obsidian"]))
            state["name"] = editor.theme_name
        sheet = editor.sheet
        colors = {}
        if sheet.cond_rules:
            from .core.condformat import evaluate

            try:
                colors = evaluate(sheet, sheet.cond_rules)
            except Exception:
                colors = {}
        stdscr.erase()
        _render(stdscr, curses, editor, attr, cap, colors, cond_attr)
        stdscr.refresh()
        try:
            ch = stdscr.get_wch()
        except curses.error:
            continue
        _handle_key(editor, ch)


def _render(stdscr, curses, editor, attr, cap, colors, cond_attr) -> None:
    max_y, max_x = stdscr.getmaxyx()
    sep = "|" if (cap in ("8", "mono") or is_ssh()) else "▌"

    if editor.mode == "browser":
        _render_browser(stdscr, curses, editor, attr, max_y, max_x)
        return
    if editor.mode == "rpn":
        _render_rpn(stdscr, curses, editor, attr, max_y, max_x)
        return
    if editor.mode == "plot":
        _render_plot(stdscr, curses, editor, attr, max_y, max_x)
        return

    sheet = editor.sheet
    col_w = 10
    n_cols = max(1, (max_x - 5) // (col_w + 1))
    # Header row.
    _addstr(stdscr, 0, 0, " " * 5, attr("label"))
    x = 5
    for c in range(editor.col, editor.col + n_cols):
        _addstr(stdscr, 0, x, index_to_col(c).ljust(col_w)[: max_x - x], attr("label"))
        x += col_w + 1
    # Data rows — drawn cell-by-cell so conditional-format colors apply per cell.
    for screen_r, r in enumerate(range(editor.row, editor.row + max_y - 3), start=1):
        if screen_r >= max_y - 2:
            break
        _addstr(stdscr, screen_r, 0, str(r + 1).rjust(4) + " ", attr("dim"))
        x = 5
        for c in range(editor.col, editor.col + n_cols):
            if x >= max_x:
                break
            text = sheet.display(r, c)[:col_w].ljust(col_w)
            if r == editor.row and c == editor.col:
                a = attr("cursor") | curses.A_REVERSE
            else:
                ca = cond_attr(colors.get((r, c)))
                a = ca if ca is not None else attr("lcd")
            _addstr(stdscr, screen_r, x, text[: max_x - x], a)
            x += col_w + 1

    # Status bar.
    mode = editor.mode.upper()
    if editor.recorder.recording:
        tag = "REL" if editor.recorder.relative else "REC"
        rec = f" {sep} ● {tag} {editor.recorder.count}"
    else:
        rec = ""
    status = f"{mode}{rec} {sep} {editor.cursor_a1()} {sep} {editor.doc.title}"
    if editor.message:
        status += f" {sep} {editor.message}"
    _addstr(stdscr, max_y - 2, 0, status[: max_x - 1], attr("banner"))
    # Command / insert line.
    if editor.mode == "command":
        _addstr(stdscr, max_y - 1, 0, editor.command_buf[: max_x - 1], attr("accent"))
    elif editor.mode == "insert":
        line = "=> " + editor.edit_buf
        if editor.completions:
            line += _completion_hint(editor.completions)
        elif editor.arg_hint:
            line += "   " + editor.arg_hint
        _addstr(stdscr, max_y - 1, 0, line[: max_x - 1], attr("accent"))
    else:
        hint = "i edit  :find  :rpn  :plot  :eq  :fmt  :py  :!cmd  :func  :w :q"
        _addstr(stdscr, max_y - 1, 0, hint[: max_x - 1], attr("dim"))


def _completion_hint(candidates: list[str]) -> str:
    if not candidates:
        return ""
    if len(candidates) == 1:
        from .core.completion import signature

        return "   " + signature(candidates[0])
    return "   {" + " ".join(candidates[:8]) + ("…}" if len(candidates) > 8 else "}")


def _addstr(stdscr, y: int, x: int, text: str, attr_val: int) -> None:
    try:
        stdscr.addstr(y, x, text, attr_val)
    except Exception:
        pass  # writing to last cell raises; ignore


def _render_browser(stdscr, curses, editor, attr, max_y, max_x) -> None:
    from .core.completion import signature

    title = "Function browser — j/k select · Enter insert · Esc close"
    _addstr(stdscr, 0, 0, title.ljust(max_x)[: max_x - 1], attr("banner"))
    visible = max(1, max_y - 4)
    start = max(0, min(editor.browser_idx - visible // 2, len(editor.browser) - visible))
    start = max(0, start)
    for i, name in enumerate(editor.browser[start : start + visible]):
        idx = start + i
        selected = idx == editor.browser_idx
        a = (attr("accent") | curses.A_REVERSE) if selected else attr("lcd")
        _addstr(stdscr, i + 1, 2, name.ljust(max_x - 3)[: max_x - 3], a)
    if editor.browser:
        sig = signature(editor.browser[editor.browser_idx])
        _addstr(stdscr, max_y - 2, 0, sig[: max_x - 1], attr("label"))


def _render_rpn(stdscr, curses, editor, attr, max_y, max_x) -> None:
    rpn = editor._ensure_rpn()
    title = "RPN calculator — tokens + Enter · '<' pull cell · '>' store X · Esc exit"
    _addstr(stdscr, 0, 0, title.ljust(max_x)[: max_x - 1], attr("banner"))
    for i, lab in enumerate(("T", "Z", "Y", "X")):
        v = rpn.stack[3 - i]
        a = (attr("accent") | curses.A_BOLD) if lab == "X" else attr("lcd")
        _addstr(stdscr, 2 + i, 3, f"{lab}: {_fmt_num(v)}"[: max_x - 4], a)
    regs = ", ".join(f"{k}={_fmt_num(v)}" for k, v in sorted(rpn.regs.items()))
    _addstr(stdscr, 7, 3, f"[{rpn.angle}]  {regs}"[: max_x - 4], attr("dim"))
    _addstr(stdscr, max_y - 1, 0, ("rpn> " + editor.rpn_input)[: max_x - 1], attr("accent"))


def _handle_rpn(editor: TuiEditor, ch) -> None:
    if ch in ("\n", "\r", 10, 13):
        editor.rpn_eval()
    elif ch == "\x1b":
        editor.mode = "normal"
    elif ch in ("\b", "\x7f", 8, 127):
        editor.rpn_input = editor.rpn_input[:-1]
    elif isinstance(ch, str) and ch.isprintable():
        editor.rpn_input += ch


def _render_plot(stdscr, curses, editor, attr, max_y, max_x) -> None:
    from .core.graphing import braille_plot

    _addstr(stdscr, 0, 0, f"y = {editor.plot_expr}   (Esc to close)".ljust(max_x)[: max_x - 1],
            attr("banner"))
    try:
        canvas = braille_plot(editor.plot_pts, width=max(10, max_x - 2), height=max(4, max_y - 3))
    except Exception as exc:  # pragma: no cover - defensive
        _addstr(stdscr, 2, 0, f"plot error: {exc}"[: max_x - 1], attr("dim"))
        return
    for i, line in enumerate(canvas.splitlines(), start=1):
        if i >= max_y - 1:
            break
        _addstr(stdscr, i, 1, line[: max_x - 2], attr("accent"))


def _handle_plot(editor: TuiEditor, ch) -> None:
    if ch == "\x1b" or ch == "q":
        editor.mode = "normal"


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
