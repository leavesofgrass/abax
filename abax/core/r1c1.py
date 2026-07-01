"""A1 <-> R1C1 formula reference conversion.

Needed for the Excel 2003 XML Spreadsheet (SpreadsheetML) format, whose
``ss:Formula`` attribute stores formulas in R1C1 notation relative to the cell
they live in. R1C1: ``R1C1`` is absolute (1-based); ``R[1]C[-1]`` is relative
(offsets from the formula's cell); a missing bracket means a zero offset
(``RC`` = the same cell). Pure stdlib → core.
"""

from __future__ import annotations

import re

from .errors import FormulaError
from .reference import col_to_index, index_to_col
from .tokenizer import Token, tokenize

_A1_PARTS = re.compile(r"^(\$?)([A-Za-z]+)(\$?)([0-9]+)$")
# A standalone R1C1 reference (lookbehind avoids matching inside identifiers).
_R1C1 = re.compile(r"(?<![A-Za-z0-9_])R(\[-?\d+\]|\d+)?C(\[-?\d+\]|\d+)?")
_STRING = re.compile(r'"(?:[^"]|"")*"')


# --- A1 -> R1C1 ------------------------------------------------------------


def ref_a1_to_r1c1(ref: str, base_row: int, base_col: int) -> str:
    sheet = ""
    if "!" in ref:
        sheet, ref = ref.rsplit("!", 1)
        sheet += "!"
    m = _A1_PARTS.match(ref)
    if not m:
        return sheet + ref
    col_abs, col_s, row_abs, row_s = m.groups()
    col = col_to_index(col_s)
    row = int(row_s) - 1
    rpart = f"R{row + 1}" if row_abs else ("R" if row == base_row else f"R[{row - base_row}]")
    cpart = f"C{col + 1}" if col_abs else ("C" if col == base_col else f"C[{col - base_col}]")
    return sheet + rpart + cpart


def _detok(tokens: list[Token]) -> str:
    parts = []
    for t in tokens:
        if t.kind == "STRING":
            parts.append('"' + t.value.replace('"', '""') + '"')
        else:
            parts.append(t.value)
    return "".join(parts)


def formula_a1_to_r1c1(raw: str, base_row: int, base_col: int) -> str:
    if not raw.startswith("="):
        return raw
    try:
        tokens = tokenize(raw[1:])
    except FormulaError:
        return raw
    out = []
    for t in tokens:
        if t.kind == "REF":
            out.append(Token("REF", ref_a1_to_r1c1(t.value, base_row, base_col)))
        elif t.kind == "RANGE":
            a, _, b = t.value.partition(":")
            out.append(
                Token(
                    "RANGE",
                    ref_a1_to_r1c1(a, base_row, base_col)
                    + ":"
                    + ref_a1_to_r1c1(b, base_row, base_col),
                )
            )
        else:
            out.append(t)
    return "=" + _detok(out)


# --- R1C1 -> A1 ------------------------------------------------------------


def _axis(group: str | None, base: int) -> tuple[int, bool]:
    """Return ``(zero_based_index, is_absolute)`` for one R/C axis token."""
    if group is None:
        return base, False  # bare 'R' / 'C' -> same row/col, relative
    if group.startswith("["):
        return base + int(group[1:-1]), False
    return int(group) - 1, True  # absolute, 1-based in the file


def ref_r1c1_to_a1(token: str, base_row: int, base_col: int) -> str:
    m = _R1C1.fullmatch(token)
    if not m:
        return token
    row, row_abs = _axis(m.group(1), base_row)
    col, col_abs = _axis(m.group(2), base_col)
    if row < 0 or col < 0:
        return "#REF!"
    return f"{'$' if col_abs else ''}{index_to_col(col)}{'$' if row_abs else ''}{row + 1}"


def formula_r1c1_to_a1(raw: str, base_row: int, base_col: int) -> str:
    if not raw.startswith("="):
        return raw
    body = raw[1:]
    # Protect string literals before substituting references.
    stash: list[str] = []

    def keep(m):
        stash.append(m.group(0))
        return f"\x00{len(stash) - 1}\x00"

    body = _STRING.sub(keep, body)
    body = _R1C1.sub(lambda m: ref_r1c1_to_a1(m.group(0), base_row, base_col), body)
    body = re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], body)
    return "=" + body
