"""Live reference scan — which cells a formula mentions, *as it is typed*.

Both front-ends highlight the cells a formula references while the user edits
it (Excel's coloured range boxes). The formula is usually **incomplete** while
being typed — unbalanced parens, a trailing operator — so this cannot use the
parser; it is a tolerant lexical scan:

* single refs (``A1``, ``$B$2``) and ranges (``A1:C3``, with any ``$`` mix),
* optional sheet qualifiers (``Sheet2!A1``, ``'My Sheet'!A1:B2``),
* text inside double-quoted strings is ignored,
* a ref immediately followed by ``(`` is a function call (``LOG10(``), not a cell.

Each **distinct** reference (case-insensitive, ``$``-insensitive) gets a stable
colour index in first-appearance order, cycling over a small palette — so
``=A1+B2*A1`` colours both ``A1`` occurrences alike. Pure stdlib (core).
"""

from __future__ import annotations

import re
from typing import NamedTuple

from .reference import parse_range

# A cell like B12 with optional $ markers.
_CELL = r"\$?[A-Za-z]{1,3}\$?[0-9]+"
# Optional sheet qualifier: a bare name or a quoted one, then '!'.
_SHEET = r"(?:(?:'(?P<qsheet>[^']+)'|(?P<sheet>[A-Za-z_][\w ]*?))!)?"
# The full token: qualified cell or range, not glued to an identifier on the
# left (so SUM's "M" never starts a match mid-word) and not a call on the right.
_REF_RE = re.compile(
    rf"(?<![A-Za-z0-9_.$])"
    rf"{_SHEET}(?P<ref>{_CELL}(?::{_CELL})?)"
    rf"(?![A-Za-z0-9_(])"
)


class RefSpan(NamedTuple):
    """One highlighted reference: where it points and which colour to use."""

    sheet: str      # qualifier as written ("" = the formula's own sheet)
    r1: int
    c1: int
    r2: int
    c2: int
    color: int      # stable palette index (first-appearance order)


def _strip_strings(text: str) -> str:
    """Blank out double-quoted string contents (keeping length/offsets)."""
    out = []
    in_str = False
    for ch in text:
        if ch == '"':
            in_str = not in_str
            out.append(" ")
        else:
            out.append(" " if in_str else ch)
    return "".join(out)


def scan_refs(text: str, *, palette_size: int = 5) -> list[RefSpan]:
    """All cell references in a (possibly incomplete) formula, colour-indexed.

    Returns ``[]`` unless ``text`` starts with ``=``. Duplicate mentions of the
    same reference share one span/colour; distinct references cycle through
    ``palette_size`` colours in order of first appearance.
    """
    if not text.startswith("="):
        return []
    body = _strip_strings(text)
    seen: dict[tuple, int] = {}      # normalized key -> colour index
    out: list[RefSpan] = []
    for m in _REF_RE.finditer(body, 1):
        sheet = m.group("qsheet") or m.group("sheet") or ""
        ref = m.group("ref").replace("$", "")
        try:
            r1, c1, r2, c2 = parse_range(ref)
        except Exception:
            continue                  # e.g. a row beyond limits — just skip
        key = (sheet.lower(), r1, c1, r2, c2)
        if key in seen:
            continue
        color = len(seen) % palette_size
        seen[key] = color
        out.append(RefSpan(sheet, r1, c1, r2, c2, color))
    return out


def refs_for_sheet(text: str, sheet_name: str, *, palette_size: int = 5) -> list[RefSpan]:
    """The :func:`scan_refs` spans that land on ``sheet_name``.

    Unqualified references belong to the formula's own sheet, so they match;
    qualified ones match case-insensitively. Colour indices are preserved from
    the full scan (a cross-sheet ref still consumes its colour, mirroring the
    front-ends' colour assignment).
    """
    low = sheet_name.lower()
    return [s for s in scan_refs(text, palette_size=palette_size)
            if not s.sheet or s.sheet.lower() == low]
