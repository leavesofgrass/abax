"""Flat-file table I/O — read/write a `Sheet` as JSON Lines or fixed-width text.

Two classic flat-file table formats are supported, each as a pair of
``loads_*``/``dumps_*`` (string) plus ``load_*``/``save_*`` (path) functions:

* **JSON Lines** (``.jsonl`` / ``.ndjson``) — one JSON object per line. On load,
  row 0 becomes the ordered union of all object keys (first-seen order) and each
  later row holds that object's values as strings (missing key -> empty). On
  dump, row 0 is read as the field names and each later row is emitted as a JSON
  object mapping field -> raw cell string.
* **Fixed-width / whitespace-aligned** text (like ``column -t`` output) — columns
  are either sliced by explicit character widths or split on runs of 2+ spaces.

Only the standard library (``json``) is used; cell text is taken verbatim via
``Sheet.get_raw`` and written via ``Sheet.set_cell``.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..sheet import Sheet

__all__ = [
    "loads_jsonl",
    "load_jsonl",
    "dumps_jsonl",
    "save_jsonl",
    "loads_fixed",
    "load_fixed",
    "dumps_fixed",
    "save_fixed",
]


# --- JSON Lines -----------------------------------------------------------


def loads_jsonl(text: str, name: str = "Sheet1") -> Sheet:
    """Parse JSON Lines text into a `Sheet`.

    Row 0 is the ordered union of all object keys (first-seen order); each later
    row holds the corresponding object's values as strings, with a missing key
    rendered as an empty cell.
    """
    records: list[dict] = []
    fields: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"expected a JSON object per line, got {type(obj).__name__}")
        records.append(obj)
        for key in obj:
            if key not in seen:
                seen.add(key)
                fields.append(key)

    sheet = Sheet(name)

    def _items():
        for col, field in enumerate(fields):
            yield 0, col, field
        for r, obj in enumerate(records, start=1):
            for col, field in enumerate(fields):
                if field in obj:
                    yield r, col, _to_cell(obj[field])

    sheet.set_cells_bulk(_items())
    return sheet


def load_jsonl(path: Path | str, name: str | None = None) -> Sheet:
    """Read a JSON Lines file. ``name`` defaults to the file stem."""
    p = Path(path)
    if name is None:
        name = p.stem
    return loads_jsonl(p.read_text(encoding="utf-8"), name=name)


def dumps_jsonl(sheet: Sheet) -> str:
    """Serialize a `Sheet` to JSON Lines text.

    Row 0 supplies the field names; each later row becomes one JSON object
    ``{field: value}``. Empty trailing fields are skipped and values are written
    as the raw cell string.
    """
    n_rows, n_cols = sheet.used_bounds()
    fields = [sheet.get_raw(0, c) for c in range(n_cols)]
    lines: list[str] = []
    for r in range(1, n_rows):
        # Find the last non-empty cell to skip empty trailing fields.
        last = -1
        for c in range(n_cols):
            if sheet.get_raw(r, c) != "":
                last = c
        obj: dict[str, str] = {}
        for c in range(last + 1):
            field = fields[c]
            if field == "":
                continue
            obj[field] = sheet.get_raw(r, c)
        lines.append(json.dumps(obj, ensure_ascii=False))
    return "\n".join(lines)


def save_jsonl(sheet: Sheet, path: Path | str) -> None:
    """Write a `Sheet` as a JSON Lines file (trailing newline included)."""
    text = dumps_jsonl(sheet)
    if text:
        text += "\n"
    Path(path).write_text(text, encoding="utf-8")


# --- Fixed-width / whitespace-aligned ------------------------------------


def loads_fixed(
    text: str, widths: list[int] | None = None, name: str = "Sheet1"
) -> Sheet:
    """Parse fixed-width / whitespace-aligned text into a `Sheet`.

    With ``widths`` (a list of column character widths) each line is sliced by
    those widths and trimmed; otherwise each line is split on runs of 2+ spaces.
    """
    sheet = Sheet(name)

    def _items():
        r = 0
        for line in text.splitlines():
            if line.strip() == "":
                continue
            if widths is not None:
                cells = _slice_widths(line, widths)
            else:
                cells = [c.strip() for c in _split_2plus(line)]
            for col, value in enumerate(cells):
                if value != "":
                    yield r, col, value
            r += 1

    sheet.set_cells_bulk(_items())
    return sheet


def load_fixed(
    path: Path | str, widths: list[int] | None = None, name: str | None = None
) -> Sheet:
    """Read a fixed-width / aligned text file. ``name`` defaults to the stem."""
    p = Path(path)
    if name is None:
        name = p.stem
    return loads_fixed(p.read_text(encoding="utf-8"), widths=widths, name=name)


def dumps_fixed(sheet: Sheet, gap: int = 2) -> str:
    """Render a `Sheet` as whitespace-aligned text.

    Each column is left-aligned and padded to its maximum display width plus
    ``gap`` spaces; trailing padding on the final column is stripped.
    """
    n_rows, n_cols = sheet.used_bounds()
    disp = [[sheet.display(r, c) for c in range(n_cols)] for r in range(n_rows)]
    col_widths = [
        max((len(disp[r][c]) for r in range(n_rows)), default=0)
        for c in range(n_cols)
    ]
    lines: list[str] = []
    for r in range(n_rows):
        parts = []
        for c in range(n_cols):
            value = disp[r][c]
            if c == n_cols - 1:
                parts.append(value)
            else:
                parts.append(value.ljust(col_widths[c] + gap))
        lines.append("".join(parts).rstrip())
    return "\n".join(lines)


def save_fixed(sheet: Sheet, path: Path | str, gap: int = 2) -> None:
    """Write a `Sheet` as aligned fixed-width text (trailing newline included)."""
    text = dumps_fixed(sheet, gap=gap)
    if text:
        text += "\n"
    Path(path).write_text(text, encoding="utf-8")


# --- helpers --------------------------------------------------------------


def _to_cell(value: object) -> str:
    """Render a JSON scalar as a cell string (no surrounding quotes for str)."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _split_2plus(line: str) -> list[str]:
    """Split a line on runs of 2 or more spaces."""
    import re

    return re.split(r" {2,}", line.strip())


def _slice_widths(line: str, widths: list[int]) -> list[str]:
    """Slice a line into fields by character widths, trimming each field."""
    cells: list[str] = []
    pos = 0
    for w in widths:
        cells.append(line[pos : pos + w].strip())
        pos += w
    return cells
