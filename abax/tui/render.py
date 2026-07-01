"""Curses rendering — the draw loop and per-mode screen painters."""

from __future__ import annotations

from .capabilities import is_ssh
from .commands import _fmt_num
from .keys import _handle_key
from .themes import THEMES, TuiTheme, _hex_to_8, _hex_to_256
from ..core.reference import index_to_col


def _draw_loop(stdscr, curses, editor, cap: str) -> None:
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
            from ..core.format.condformat import evaluate

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
        from ..core.completion import signature

        return "   " + signature(candidates[0])
    return "   {" + " ".join(candidates[:8]) + ("…}" if len(candidates) > 8 else "}")


def _addstr(stdscr, y: int, x: int, text: str, attr_val: int) -> None:
    try:
        stdscr.addstr(y, x, text, attr_val)
    except Exception:
        pass  # writing to last cell raises; ignore


def _render_browser(stdscr, curses, editor, attr, max_y, max_x) -> None:
    from ..core.completion import signature

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


def _render_plot(stdscr, curses, editor, attr, max_y, max_x) -> None:
    from ..core.graphing import braille_plot

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
