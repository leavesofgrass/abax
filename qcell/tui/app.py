"""The curses front-end entry point — wires settings, document, and the loop."""

from __future__ import annotations

from .capabilities import detect_terminal
from .editor import TuiEditor
from .render import _draw_loop
from .themes import THEMES


def run_tui(file: str | None = None, registry=None) -> int:
    try:
        import curses
    except ImportError:  # pragma: no cover - Windows without windows-curses
        print("curses is unavailable; install 'windows-curses' on Windows.")
        return 1

    from .. import _runtime as rt
    from ..engine.document import Document
    from ..settings import load_settings

    settings = load_settings(rt.CONFIG_DIR / "settings.json")

    # Same full-fat auto-install as the GUI: fetch optional deps in the background.
    from .. import autodeps
    autodeps.set_enabled(getattr(settings, "auto_install", True))
    autodeps.prefetch_all()

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
