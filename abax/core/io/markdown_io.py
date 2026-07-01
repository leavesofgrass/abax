"""GitHub-Flavored-Markdown table import/export — a first-class abax format.

Export produces a padded, alignment-aware GFM table; import parses one (or the
first) GFM table back into a sheet. Pipes and newlines in cell text are escaped.
Pure stdlib → core.
"""

from __future__ import annotations

from pathlib import Path

from ..reference import index_to_col
from ..sheet import Sheet

_ALIGN_MARK = {"l": ":---", "c": ":---:", "r": "---:"}


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _unescape(text: str) -> str:
    return text.replace("<br>", "\n").replace("\\|", "|").replace("\\\\", "\\")


def to_markdown(
    sheet: Sheet,
    *,
    header: bool = True,
    align: list[str] | None = None,
    values: bool = True,
) -> str:
    """Render a sheet as a GFM table.

    ``header=True`` uses the sheet's first row as the header; otherwise column
    letters (A, B, C…) are used. ``align`` is a per-column list of
    ``'l'|'c'|'r'`` (default left). ``values`` renders computed values.
    """
    n_rows, n_cols = sheet.used_bounds()
    if n_cols == 0:
        return ""

    def cell(r, c):
        return _escape(sheet.display(r, c) if values else sheet.get_raw(r, c))

    if header:
        head = [cell(0, c) or index_to_col(c) for c in range(n_cols)]
        body = [[cell(r, c) for c in range(n_cols)] for r in range(1, n_rows)]
    else:
        head = [index_to_col(c) for c in range(n_cols)]
        body = [[cell(r, c) for c in range(n_cols)] for r in range(n_rows)]

    align = align or ["l"] * n_cols
    widths = [len(head[c]) for c in range(n_cols)]
    for row in body:
        for c in range(n_cols):
            widths[c] = max(widths[c], len(row[c]))
    widths = [max(w, 3) for w in widths]

    def fmt_row(cells):
        return "| " + " | ".join(cells[c].ljust(widths[c]) for c in range(n_cols)) + " |"

    sep = "| " + " | ".join(
        _align_sep(align[c] if c < len(align) else "l", widths[c]) for c in range(n_cols)
    ) + " |"
    lines = [fmt_row(head), sep] + [fmt_row(row) for row in body]
    return "\n".join(lines) + "\n"


def _align_sep(a: str, width: int) -> str:
    mark = _ALIGN_MARK.get(a, ":---")
    if mark == ":---:":
        return ":" + "-" * max(width - 2, 1) + ":"
    if mark == "---:":
        return "-" * max(width - 1, 1) + ":"
    return ":" + "-" * max(width - 1, 1)


def from_markdown(text: str, name: str = "Sheet1") -> Sheet:
    """Parse the first GFM table found in ``text`` into a sheet."""
    rows = _extract_table(text)
    sheet = Sheet(name)
    sheet.set_cells_bulk(
        (r, c, val)
        for r, cells in enumerate(rows)
        for c, val in enumerate(cells)
        if val != ""
    )
    return sheet


def _extract_table(text: str) -> list[list[str]]:
    table_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            table_lines.append(stripped)
        elif table_lines:
            break  # table ended
    if not table_lines:
        return []
    parsed = [_split_row(line) for line in table_lines]
    # Drop the alignment separator row (cells made of -, :, space).
    parsed = [row for row in parsed if not _is_separator(row)]
    return parsed


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    # split on unescaped pipes
    cells, buf, i = [], [], 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            buf.append(line[i : i + 2])
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append("".join(buf))
    return [_unescape(c.strip()) for c in cells]


def _is_separator(cells: list[str]) -> bool:
    return all(set(c) <= set("-: ") and "-" in c for c in cells) if cells else False


def save_markdown(sheet: Sheet, path: str | Path, **kw) -> None:
    Path(path).write_text(to_markdown(sheet, **kw), encoding="utf-8")


def load_markdown(path: str | Path, name: str | None = None) -> Sheet:
    path = Path(path)
    return from_markdown(path.read_text(encoding="utf-8"), name or path.stem)
