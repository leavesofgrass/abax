"""Shift formula references by a row/column delta — the basis for relative
macro recording (and, later, copy/paste fill).

`shift_formula` re-tokenizes a formula, offsets every *relative* reference by
``(dr, dc)``, leaves ``$``-anchored parts fixed, and reassembles. References
that move off the top/left edge become ``#REF!``. Pure stdlib → core.
"""

from __future__ import annotations

import re

from .errors import FormulaError
from .reference import col_to_index, index_to_col
from .tokenizer import Token, tokenize

# $col? letters $row? digits — the $ groups mark absolute column / row.
_REF_PARTS = re.compile(r"^(\$?)([A-Za-z]+)(\$?)([0-9]+)$")

REF_ERROR = "#REF!"


def shift_reference(ref: str, dr: int, dc: int) -> str:
    """Shift a single A1 reference. ``$`` keeps that axis fixed; a ``Sheet!``
    qualifier is preserved (only the cell part shifts)."""
    sheet = ""
    if "!" in ref:
        sheet, ref = ref.rsplit("!", 1)
        sheet += "!"
    m = _REF_PARTS.match(ref)
    if not m:
        return sheet + ref
    col_abs, col_s, row_abs, row_s = m.groups()
    col = col_to_index(col_s)
    row = int(row_s) - 1
    if not col_abs:  # column is relative
        col += dc
    if not row_abs:  # row is relative
        row += dr
    if col < 0 or row < 0:
        return REF_ERROR
    return f"{sheet}{col_abs}{index_to_col(col)}{row_abs}{row + 1}"


def shift_range(rng: str, dr: int, dc: int) -> str:
    sheet = ""
    if "!" in rng:
        sheet, rng = rng.rsplit("!", 1)
        sheet += "!"
    a, _, b = rng.partition(":")
    sa, sb = shift_reference(a, dr, dc), shift_reference(b, dr, dc)
    if sa == REF_ERROR or sb == REF_ERROR:
        return REF_ERROR
    return f"{sheet}{sa}:{sb}"


def shift_formula(raw: str, dr: int, dc: int) -> str:
    """Return ``raw`` with all relative refs shifted by ``(dr, dc)``.

    Non-formula text (no leading ``=``) and ``(0, 0)`` shifts are returned
    unchanged. Unparseable formulas are returned as-is.
    """
    if not raw.startswith("=") or (dr == 0 and dc == 0):
        return raw
    try:
        tokens = tokenize(raw[1:])
    except FormulaError:
        return raw
    out: list[Token] = []
    for t in tokens:
        if t.kind == "REF":
            out.append(Token("REF", shift_reference(t.value, dr, dc)))
        elif t.kind == "RANGE":
            out.append(Token("RANGE", shift_range(t.value, dr, dc)))
        else:
            out.append(t)
    return "=" + _detokenize(out)


def _detokenize(tokens: list[Token]) -> str:
    parts: list[str] = []
    for t in tokens:
        if t.kind == "STRING":
            parts.append('"' + t.value.replace('"', '""') + '"')
        else:
            parts.append(t.value)
    return "".join(parts)
