"""Command-mode parsing and number formatting — pure, testable."""

from __future__ import annotations


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
