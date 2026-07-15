"""The curses front-end entry point — wires settings, document, and the loop."""

from __future__ import annotations

from .capabilities import detect_terminal
from .render import _draw_loop
from .session import build_session


def run_tui(file: str | None = None, registry=None) -> int:
    try:
        import curses
    except ImportError:  # pragma: no cover - Windows without windows-curses
        print("curses is unavailable; install 'windows-curses' on Windows.")
        return 1

    # Shared preamble: settings, first-run dep hint, live-data/extern consent,
    # document open, editor + theme (see abax.tui.session).
    editor = build_session(file, registry)

    def _main(stdscr) -> int:
        curses.curs_set(0)
        cap = detect_terminal(curses.has_colors(), curses.COLORS if curses.has_colors() else 0)
        _draw_loop(stdscr, curses, editor, cap)
        return 0

    return curses.wrapper(_main)
