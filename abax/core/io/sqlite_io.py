"""SQLite import/export for abax sheets and workbooks.

Pure stdlib (:mod:`sqlite3`). A table maps to a :class:`Sheet` where row 0
holds the column names and rows 1.. hold the data; every value is stored as
text. Going the other way, a sheet's row 0 supplies column names (sanitized
to safe identifiers) and rows 1.. become ``TEXT`` columns inserted via
parameterized queries.

Identifiers are always double-quoted with embedded quotes escaped; values are
never string-formatted into SQL.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..reference import index_to_col
from ..sheet import Sheet
from ..workbook import Workbook


def _quote_ident(name: str) -> str:
    """Double-quote an SQL identifier, escaping embedded double quotes."""
    return '"' + name.replace('"', '""') + '"'


def _sanitize_ident(name: str, fallback: str) -> str:
    """Make a safe-ish column identifier; use ``fallback`` for blanks."""
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name).strip("_")
    return cleaned or fallback


def list_tables(db_path: str | Path) -> list[str]:
    """Names of user tables (excluding ``sqlite_*`` internals), sorted."""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        return sorted(row[0] for row in cur.fetchall())
    finally:
        conn.close()


def load_table(
    db_path: str | Path,
    table_or_query: str,
    name: str | None = None,
) -> Sheet:
    """Load a table or query result into a :class:`Sheet`.

    If ``table_or_query`` (stripped, uppercased) starts with ``SELECT`` it is
    run as-is; otherwise ``SELECT * FROM "<table_or_query>"`` is run. Row 0 of
    the resulting sheet is the column names (from ``cursor.description``) and
    rows 1.. are the result rows. Each value is stored as text via ``str``;
    ``None`` becomes an empty cell. ``name`` defaults to the table name (or
    ``"query"`` for an ad-hoc query).
    """
    stripped = table_or_query.strip()
    is_query = stripped.upper().startswith("SELECT")
    if is_query:
        sql = stripped
        default_name = "query"
    else:
        sql = f"SELECT * FROM {_quote_ident(table_or_query)}"
        default_name = table_or_query

    sheet = Sheet(name or default_name)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []

        def _items():
            for col, header in enumerate(columns):
                yield 0, col, str(header)
            for r, datarow in enumerate(cur.fetchall(), start=1):
                for col, value in enumerate(datarow):
                    if value is not None:
                        yield r, col, str(value)

        sheet.set_cells_bulk(_items())
    finally:
        conn.close()
    return sheet


def save_table(
    sheet: Sheet,
    db_path: str | Path,
    table: str,
    if_exists: str = "replace",
) -> None:
    """Write a sheet to a SQLite table.

    Row 0 supplies column names (sanitized; blanks fall back to ``col_1``..).
    ``if_exists`` is ``"replace"`` (drop first), ``"append"`` (keep existing
    rows), or ``"fail"`` (raise if the table exists). Columns are created as
    ``TEXT``; data rows (1..) are inserted with parameterized queries and empty
    cells become ``NULL``.
    """
    if if_exists not in ("replace", "append", "fail"):
        raise ValueError(f"invalid if_exists: {if_exists!r}")

    n_rows, n_cols = sheet.used_bounds()

    # Column names from row 0, sanitized and de-duplicated.
    col_names: list[str] = []
    seen: set[str] = set()
    for c in range(n_cols):
        raw = sheet.get_raw(0, c)
        ident = _sanitize_ident(raw, f"col_{c + 1}")
        base = ident
        i = 2
        while ident.lower() in seen:
            ident = f"{base}_{i}"
            i += 1
        seen.add(ident.lower())
        col_names.append(ident)

    conn = sqlite3.connect(str(db_path))
    try:
        exists = (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            is not None
        )
        if if_exists == "fail" and exists:
            raise ValueError(f"table already exists: {table!r}")
        if if_exists == "replace" and exists:
            conn.execute(f"DROP TABLE {_quote_ident(table)}")
            exists = False

        if not exists:
            if not col_names:
                # No header row: create a single placeholder column.
                col_names = ["col_1"]
            cols_sql = ", ".join(f"{_quote_ident(c)} TEXT" for c in col_names)
            conn.execute(f"CREATE TABLE {_quote_ident(table)} ({cols_sql})")

        if col_names:
            placeholders = ", ".join("?" for _ in col_names)
            cols_sql = ", ".join(_quote_ident(c) for c in col_names)
            insert_sql = (
                f"INSERT INTO {_quote_ident(table)} ({cols_sql}) VALUES ({placeholders})"
            )
            for r in range(1, n_rows):
                values = []
                for c in range(len(col_names)):
                    raw = sheet.get_raw(r, c)
                    values.append(raw if raw != "" else None)
                conn.execute(insert_sql, values)
        conn.commit()
    finally:
        conn.close()


def load_database(db_path: str | Path, name: str | None = None) -> Workbook:
    """Load every user table into a sheet and wrap them in a :class:`Workbook`.

    ``name`` is accepted for symmetry but is unused; sheet names come from the
    table names.
    """
    sheets = [load_table(db_path, table) for table in list_tables(db_path)]
    return Workbook.from_sheets(sheets)


# index_to_col is imported to match the requested core surface and is available
# to callers building A1-style headers from this module.
__all__ = [
    "list_tables",
    "load_table",
    "save_table",
    "load_database",
    "index_to_col",
]
