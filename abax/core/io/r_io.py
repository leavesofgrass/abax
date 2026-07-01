"""R import/export — sheets as ``data.frame`` assignments.

Export writes one ``name <- data.frame(col = c(...), ...)`` per sheet (first row
is the column names). Import is a best-effort parser for that same shape and for
bare ``name <- c(...)`` vectors. Pure stdlib → core.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..sheet import Sheet
from ..workbook import Workbook

_IDENT = re.compile(r"\W+")


def _ident(name: str) -> str:
    out = _IDENT.sub(".", name.strip())
    if not out or out[0].isdigit():
        out = "df." + out
    return out


def _r_value(value) -> str:
    from ..errors import CellError

    if value is None:
        return "NA"
    if isinstance(value, CellError):
        return "NA"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(int(value)) if float(value).is_integer() else repr(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_r(workbook: Workbook) -> str:
    blocks = []
    for sheet in workbook.sheets:
        blocks.append(_sheet_to_r(sheet))
    return "\n\n".join(blocks) + "\n"


def _sheet_to_r(sheet: Sheet) -> str:
    n_rows, n_cols = sheet.used_bounds()
    var = _ident(sheet.name)
    if n_rows == 0:
        return f"{var} <- data.frame()"
    headers = [sheet.display(0, c) or f"V{c + 1}" for c in range(n_cols)]
    cols = []
    for c in range(n_cols):
        vals = [_r_value(sheet.get_value(r, c)) for r in range(1, n_rows)]
        cols.append(f"  {_ident(headers[c])} = c({', '.join(vals)})")
    body = ",\n".join(cols)
    return f"{var} <- data.frame(\n{body},\n  stringsAsFactors = FALSE\n)"


# --- import (best effort) --------------------------------------------------

_ASSIGN_DF = re.compile(r"([\w.]+)\s*<-\s*data\.frame\s*\(", re.MULTILINE)
_ASSIGN_VEC = re.compile(r"([\w.]+)\s*<-\s*c\s*\((.*?)\)", re.DOTALL)
_COL = re.compile(r"([\w.]+)\s*=\s*c\s*\((.*?)\)", re.DOTALL)


def from_r(text: str) -> Workbook:
    wb = Workbook.__new__(Workbook)
    wb.sheets = []
    wb.active = 0

    consumed_spans: list[tuple[int, int]] = []
    for m in _ASSIGN_DF.finditer(text):
        start = m.end() - 1  # at the '('
        end = _matching_paren(text, start)
        if end is None:
            continue
        inner = text[start + 1 : end]
        consumed_spans.append((m.start(), end))
        sheet = _df_from_inner(m.group(1), inner)
        if sheet is not None:
            wb.sheets.append(sheet)

    # Bare vectors not already inside a consumed data.frame block.
    for m in _ASSIGN_VEC.finditer(text):
        if any(s <= m.start() < e for s, e in consumed_spans):
            continue
        values = _parse_c(m.group(2))
        sheet = Sheet(m.group(1))
        sheet.set_cells_bulk(
            [(0, 0, m.group(1)), *((r, 0, v) for r, v in enumerate(values, start=1))]
        )
        wb.sheets.append(sheet)

    wb._add_default_if_empty()
    return wb


def _df_from_inner(name: str, inner: str) -> Sheet | None:
    cols = _COL.findall(inner)
    if not cols:
        return None
    sheet = Sheet(name)

    def _items():
        for c, (col_name, body) in enumerate(cols):
            yield 0, c, col_name
            for r, v in enumerate(_parse_c(body), start=1):
                yield r, c, v

    sheet.set_cells_bulk(_items())
    return sheet


def _parse_c(body: str) -> list[str]:
    out = []
    for tok in _split_top_commas(body):
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith('"') and tok.endswith('"'):
            out.append(tok[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        elif tok in ("TRUE", "T"):
            out.append("TRUE")
        elif tok in ("FALSE", "F"):
            out.append("FALSE")
        elif tok == "NA":
            out.append("")
        else:
            out.append(tok)
    return out


def _split_top_commas(s: str) -> list[str]:
    parts, buf, depth, in_str = [], [], 0, False
    i = 0
    while i < len(s):
        ch = s[i]
        if in_str:
            buf.append(ch)
            if ch == "\\" and i + 1 < len(s):
                buf.append(s[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _matching_paren(text: str, open_pos: int) -> int | None:
    depth = 0
    for i in range(open_pos, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return None


def save_r(workbook: Workbook, path: str | Path) -> None:
    Path(path).write_text(to_r(workbook), encoding="utf-8")


def load_r(path: str | Path) -> Workbook:
    return from_r(Path(path).read_text(encoding="utf-8"))
