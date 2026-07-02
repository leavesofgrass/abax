"""Statistical-format import (Stata ``.dta`` / SPSS ``.sav``) via pyreadstat.

Stata and SPSS are the two dominant proprietary statistical file formats and a
long-standing gap in abax's importers. They are read here through the optional
**pyreadstat** package (a thin, fast C binding around ReadStat). Like the Parquet
adapter, this module imports gracefully: importing it never fails when pyreadstat
is absent, and any operation that actually needs it raises a descriptive
:class:`StatFileError` telling the user how to enable it. That keeps the core
engine free of any hard third-party dependency (see docs/architecture.md).

The workbook shape mirrors ``engine/parquet_io``: a one-sheet workbook whose
first row holds the column (variable) names and whose remaining rows hold cell
*text* — every value is stringified, nulls become the empty string, whole floats
collapse to ints, and dates/datetimes render as ISO strings so abax's engine
recognises them as dates. Built with ``Sheet.set_cells_bulk`` /
``Workbook.from_sheets``, exactly like every other importer.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from ..core.sheet import Sheet
from ..core.workbook import Workbook


class StatFileError(Exception):
    """Raised when a ``.dta``/``.sav`` operation cannot proceed (missing dep)."""


_FALLBACK_MSG = (
    "Reading Stata (.dta) / SPSS (.sav) files requires 'pyreadstat'. Install it "
    "with:\n"
    "    pip install pyreadstat\n"
    "or install abax's stats-io extra:  pip install abax[stats-io]"
)


def _import_pyreadstat():
    """Lazy-import pyreadstat, raising :class:`StatFileError` if unavailable."""
    try:
        import pyreadstat  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise StatFileError(_FALLBACK_MSG) from exc
    return pyreadstat


def available() -> bool:
    """True iff pyreadstat can be imported (does not raise)."""
    try:
        import pyreadstat  # type: ignore  # noqa: F401
    except Exception:
        return False
    return True


# Extension -> pyreadstat reader-function name. ``.zsav`` is the compressed SPSS
# variant, which the same reader handles transparently.
_READERS = {
    ".dta": "read_dta",
    ".sav": "read_sav",
    ".zsav": "read_sav",
    ".por": "read_por",
}


def _is_stat_path(path: Path) -> bool:
    return path.suffix.lower() in _READERS


def _stringify(value) -> str:
    """Render one DataFrame cell as abax cell text.

    ``None``/``NaN`` -> ``""``; whole floats collapse to ints (``3.0`` -> ``3``);
    dates/datetimes render as ISO strings so the engine recognises them.
    """
    if value is None:
        return ""
    # pandas NaN / NaT: not equal to itself.
    if value != value:  # noqa: PLR0124 - NaN check without importing numpy
        return ""
    if isinstance(value, _dt.datetime):
        # Drop a midnight time component so a pure date reads as a date.
        if value.hour == value.minute == value.second == value.microsecond == 0:
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return str(value)


def load_statfile(path: str | Path) -> Workbook:
    """Read a ``.dta`` (Stata) or ``.sav`` (SPSS) file into a one-sheet workbook.

    The variable names become the header row; every value is rendered as cell
    text (nulls as the empty string). Raises :class:`StatFileError` if
    pyreadstat is not installed or the extension is unsupported.
    """
    path = Path(path)
    reader_name = _READERS.get(path.suffix.lower())
    if reader_name is None:
        raise StatFileError(
            f"unsupported statistical file type: {path.suffix!r} "
            f"(expected one of {', '.join(sorted(_READERS))})"
        )

    pyreadstat = _import_pyreadstat()
    reader = getattr(pyreadstat, reader_name)
    df, _meta = reader(str(path))

    sheet = Sheet(path.stem)
    columns = [str(col) for col in df.columns]

    def _items():
        for c, name in enumerate(columns):
            if name != "":
                yield 0, c, name
        for r, (_, row) in enumerate(df.iterrows(), start=1):
            for c, col in enumerate(df.columns):
                text = _stringify(row[col])
                if text != "":
                    yield r, c, text

    sheet.set_cells_bulk(_items())
    return Workbook.from_sheets([sheet])


__all__ = [
    "StatFileError",
    "available",
    "load_statfile",
]
