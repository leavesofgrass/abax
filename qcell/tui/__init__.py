"""Curses TUI — vim-first, SSH-safe, degrades to ASCII + 8-color / mono.

Split (2026-06-29) from the former single ``tui.py`` into focused modules:

- :mod:`~qcell.tui.capabilities` — terminal detection (pure, testable).
- :mod:`~qcell.tui.themes` — colour themes + hex→palette mapping.
- :mod:`~qcell.tui.commands` — command parsing + number formatting.
- :mod:`~qcell.tui.editor` — the :class:`TuiEditor` state machine.
- :mod:`~qcell.tui.keys` — per-mode keystroke handling.
- :mod:`~qcell.tui.render` — the curses draw loop + screen painters.
- :mod:`~qcell.tui.app` — :func:`run_tui`, the entry point.

This module re-exports the public surface so ``from qcell.tui import …`` keeps
working unchanged.
"""

from __future__ import annotations

from .app import run_tui
from .capabilities import can_use_powerline, detect_terminal, is_ssh
from .commands import _fmt_num, parse_command
from .editor import TuiEditor
from .themes import THEMES, TuiTheme, _hex_to_8, _hex_to_256

__all__ = [
    "run_tui",
    "TuiEditor",
    "TuiTheme",
    "THEMES",
    "detect_terminal",
    "is_ssh",
    "can_use_powerline",
    "parse_command",
]
