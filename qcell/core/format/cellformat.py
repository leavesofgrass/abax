"""Per-cell number formats — the "format tables" layer.

A format spec is a short string (``"currency"``, ``"percent"``, ``"fixed2"``…)
attached to a cell. :func:`format_cell` turns a computed value into display text
according to the spec; text, blanks, and errors pass through unformatted. Specs
are stored per-cell on the :class:`~qcell.core.sheet.Sheet` and persisted in the
workbook envelope, so both the GUI and TUI render the same formatting.
"""

from __future__ import annotations

import re

from ..errors import is_error

# (spec, menu label) — the offered formats.
FORMATS: list[tuple[str, str]] = [
    ("general", "General"),
    ("int", "Integer"),
    ("fixed2", "2 decimals"),
    ("comma", "Thousands"),
    ("currency", "Currency"),
    ("percent", "Percent"),
    ("sci", "Scientific"),
    ("text", "Text"),
]

_FIXED = re.compile(r"^fixed:?(\d+)$")


def _general(v: float) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v:g}"


def format_cell(value, spec: str | None) -> str:
    """Format ``value`` per ``spec``. Non-numbers/errors/blanks pass through."""
    if value is None or value == "":
        return ""
    if is_error(value):
        return str(value)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    spec = (spec or "general").lower()
    if spec == "text" or not isinstance(value, (int, float)):
        return str(value)
    v = float(value)
    if spec == "general":
        return _general(v)
    if spec == "int":
        return str(int(round(v)))
    if spec == "comma":
        return f"{int(v):,}" if v.is_integer() else f"{v:,.2f}"
    if spec == "currency":
        return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"
    if spec == "percent":
        return f"{v * 100:g}%"
    if spec == "sci":
        return f"{v:.3e}"
    m = _FIXED.match(spec)
    if m:
        return f"{v:.{int(m.group(1))}f}"
    return _general(v)
