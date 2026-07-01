"""Parquet / Feather import/export via pandas — optional, with a clear fallback.

Parquet and Feather are columnar binary formats best produced by pandas (which
needs a parquet/feather engine such as pyarrow or fastparquet). Like the Excel
adapter, this module imports gracefully: importing it never fails when pandas is
absent, and any operation that actually needs pandas raises a descriptive
:class:`ParquetError` telling the user how to enable it. This keeps the core
engine free of any hard third-party dependency (see docs/architecture.md).

The workbook shape mirrors ``core/csv_io``: a one-sheet workbook whose first row
holds the column names and whose remaining rows hold cell *text* (every value is
stringified; nulls become the empty string), via ``Sheet.set_cell`` /
``Workbook.from_sheets``. Export reads back through ``Sheet.display`` /
``Sheet.used_bounds`` exactly as the CSV writer does.
"""

from __future__ import annotations

from pathlib import Path

from ..core.sheet import Sheet
from ..core.workbook import Workbook


class ParquetError(Exception):
    """Raised when a Parquet/Feather operation cannot proceed (missing deps)."""


_FALLBACK_MSG = (
    "Parquet/Feather import/export requires 'pandas' plus a parquet engine "
    "('pyarrow' or 'fastparquet'). Install them with:\n"
    "    pip install pandas pyarrow\n"
    "or install abax's fast-io extra:  pip install abax[fast-io]"
)


def _import_pandas():
    """Lazy-import pandas, raising :class:`ParquetError` if unavailable."""
    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise ParquetError(_FALLBACK_MSG) from exc
    return pd


def _has_parquet_engine() -> bool:
    """True if any pandas-supported parquet engine is importable."""
    for name in ("pyarrow", "fastparquet"):
        try:
            __import__(name)
            return True
        except ImportError:
            continue
    return False


def available() -> bool:
    """True if pandas and a parquet engine are both importable."""
    try:
        import pandas  # type: ignore  # noqa: F401
    except ImportError:
        return False
    return _has_parquet_engine()


def _is_feather(path: Path) -> bool:
    return path.suffix.lower() in (".feather", ".ft")


def load_parquet(path: str | Path) -> Workbook:
    """Read a ``.parquet`` / ``.feather`` file into a one-sheet workbook.

    The DataFrame's column names become the header row; every value is rendered
    as a string (nulls as the empty string).
    """
    pd = _import_pandas()
    path = Path(path)
    if _is_feather(path):
        df = pd.read_feather(path)
    else:
        df = pd.read_parquet(path)

    sheet = Sheet(path.stem)
    columns = [str(col) for col in df.columns]

    def _items():
        for c, name in enumerate(columns):
            if name != "":
                yield 0, c, name
        for r, (_, row) in enumerate(df.iterrows(), start=1):
            for c, name in enumerate(df.columns):
                value = row[name]
                text = "" if pd.isna(value) else str(value)
                if text != "":
                    yield r, c, text

    sheet.set_cells_bulk(_items())
    return Workbook.from_sheets([sheet])


def save_parquet(workbook: Workbook, path: str | Path) -> None:
    """Write the active sheet to ``.parquet`` (or ``.feather`` by extension).

    The first row is treated as the header (column names); subsequent rows are
    written as displayed cell values, matching ``core/csv_io.save_csv``.
    """
    pd = _import_pandas()
    path = Path(path)
    sheet = workbook.sheet
    n_rows, n_cols = sheet.used_bounds()

    if n_cols == 0:
        columns: list[str] = []
        data: list[list[str]] = []
    else:
        columns = [sheet.display(0, c) for c in range(n_cols)]
        data = [
            [sheet.display(r, c) for c in range(n_cols)]
            for r in range(1, n_rows)
        ]
    df = pd.DataFrame(data, columns=columns)

    if _is_feather(path):
        df.to_feather(path)
    else:
        df.to_parquet(path)


__all__ = [
    "ParquetError",
    "available",
    "load_parquet",
    "save_parquet",
]
