"""Run SQL over spreadsheet sheets using the stdlib ``sqlite3`` module.

Each :class:`~abax.core.sheet.Sheet` is loaded into an in-memory SQLite table
named after the sheet. The first used row supplies column names; the remaining
rows are data. Each column's SQLite affinity is inferred from its values
(INTEGER / REAL / TEXT) so that numeric columns aggregate as numbers rather than
concatenating as text.

Stdlib-only: the sole import beyond the standard library is the local
:class:`Sheet`, imported lazily inside :func:`result_to_sheet`.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any


class SqlError(Exception):
    """Raised for any SQL execution or table-construction failure."""


_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")


def _sanitize_identifier(name: str, fallback: str) -> str:
    """Turn arbitrary text into a valid SQL identifier.

    Non-alphanumeric characters become underscores; a leading digit (or an empty
    result) is prefixed so the identifier never starts with a digit.
    """
    text = _IDENT_RE.sub("_", str(name).strip())
    if not text:
        text = fallback
    if text[0].isdigit():
        text = "_" + text
    return text


def _dedupe(names: list[str]) -> list[str]:
    """De-duplicate column names by appending a numeric suffix to collisions."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for name in names:
        if name in seen:
            seen[name] += 1
            new = f"{name}_{seen[name]}"
            # Guard against the suffixed name itself colliding.
            while new in seen:
                seen[name] += 1
                new = f"{name}_{seen[name]}"
            seen[new] = 0
            out.append(new)
        else:
            seen[name] = 0
            out.append(name)
    return out


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value == "")


def _parses_as_int(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    try:
        int(str(value))
        return True
    except (ValueError, TypeError):
        return False


def _parses_as_float(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        float(str(value))
        return True
    except (ValueError, TypeError):
        return False


def _infer_affinity(values: list[Any]) -> str:
    """Return 'INTEGER', 'REAL', or 'TEXT' for a column's non-empty values."""
    non_empty = [v for v in values if not _is_empty(v)]
    if not non_empty:
        return "TEXT"
    if all(_parses_as_int(v) for v in non_empty):
        return "INTEGER"
    if all(_parses_as_float(v) for v in non_empty):
        return "REAL"
    return "TEXT"


def _coerce(value: Any, affinity: str) -> Any:
    """Coerce a raw cell value to the Python type matching the column affinity."""
    if _is_empty(value):
        return None
    if affinity == "INTEGER":
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, float):
            return int(value)
        return int(str(value))
    if affinity == "REAL":
        return float(value)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def _load_sheet(conn: sqlite3.Connection, sheet: Any, used_names: set[str]) -> None:
    """Create and populate an in-memory table for one sheet."""
    nrows, ncols = sheet.used_bounds()
    table = _sanitize_identifier(sheet.name, "Sheet")
    # Keep table names unique across sheets that sanitize to the same identifier.
    base = table
    n = 1
    while table.lower() in used_names:
        n += 1
        table = f"{base}_{n}"
    used_names.add(table.lower())

    if nrows == 0 or ncols == 0:
        conn.execute(f'CREATE TABLE "{table}" (col_1 TEXT)')
        return

    # Header row -> sanitized, de-duplicated column names.
    raw_headers = []
    for c in range(ncols):
        val = sheet.get_value(0, c)
        header = "" if _is_empty(val) else str(val)
        raw_headers.append(_sanitize_identifier(header, f"col_{c + 1}"))
    columns = _dedupe(raw_headers)

    # Gather data cells (rows 1..nrows-1) for affinity inference.
    data: list[list[Any]] = []
    for r in range(1, nrows):
        data.append([sheet.get_value(r, c) for c in range(ncols)])

    affinities = [
        _infer_affinity([row[c] for row in data]) for c in range(ncols)
    ]

    col_defs = ", ".join(
        f'"{col}" {aff}' for col, aff in zip(columns, affinities)
    )
    conn.execute(f'CREATE TABLE "{table}" ({col_defs})')

    placeholders = ", ".join("?" for _ in columns)
    insert = f'INSERT INTO "{table}" VALUES ({placeholders})'
    rows = [
        tuple(_coerce(row[c], affinities[c]) for c in range(ncols))
        for row in data
    ]
    conn.executemany(insert, rows)


def run_sql(sheets: dict[str, Any], sql: str) -> tuple[list[str], list[tuple]]:
    """Run ``sql`` over the given sheets.

    ``sheets`` maps names to :class:`Sheet` objects; each becomes an in-memory
    SQLite table. Returns ``(column_names, rows)`` from the executed statement.
    Any SQLite error (including references to unknown tables) is wrapped in
    :class:`SqlError`.
    """
    conn = sqlite3.connect(":memory:")
    try:
        used_names: set[str] = set()
        for sheet in sheets.values():
            _load_sheet(conn, sheet, used_names)
        try:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            raise SqlError(str(exc)) from exc
        description = cursor.description or []
        columns = [d[0] for d in description]
        return columns, rows
    finally:
        conn.close()


def result_to_sheet(columns: list[str], rows: list[tuple], name: str = "Query") -> Any:
    """Build a new :class:`Sheet` with ``columns`` as row 0 and ``rows`` below."""
    from .sheet import Sheet

    sheet = Sheet(name=name)
    for c, col in enumerate(columns):
        sheet.set_cell(0, c, "" if col is None else str(col))
    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row):
            sheet.set_cell(r, c, "" if value is None else str(value))
    return sheet
