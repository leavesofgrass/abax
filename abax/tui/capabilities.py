"""Terminal capability detection — pure, testable (pass capabilities in)."""

from __future__ import annotations

import os


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
