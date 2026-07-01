"""Column type inference — pure stdlib, so it lives in core.

CSV/TSV import leaves every field as raw cell *text*. This module looks at the
string values of a column and infers its logical type (``int``, ``float``,
``bool``, ``date``, or ``text``), and can coerce a string into the inferred
Python value. It never imports anything beyond the standard library.

Typical use::

    types = infer_types(rows)              # one type per column
    value = coerce(cell_text, types[col])  # parsed Python object
"""

from __future__ import annotations

from datetime import date, datetime

# Case-insensitive string literals recognised as booleans.
_TRUE_WORDS = frozenset({"true", "yes"})
_FALSE_WORDS = frozenset({"false", "no"})
_BOOL_WORDS = _TRUE_WORDS | _FALSE_WORDS


def _is_int(text: str) -> bool:
    """True if ``text`` is an optional sign followed by digits only."""
    if not text:
        return False
    body = text[1:] if text[0] in "+-" else text
    return body.isdigit()


def _is_float(text: str) -> bool:
    """True if ``text`` parses as a float (decimal or scientific notation).

    Rejects values that Python's ``float`` accepts but a spreadsheet should
    not treat as a plain number — ``inf``, ``nan`` and the like.
    """
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    lowered = text.strip().lower().lstrip("+-")
    if lowered in ("inf", "infinity", "nan"):
        return False
    return True


def _is_date(text: str) -> bool:
    """True if ``text`` is a valid ISO ``YYYY-MM-DD`` date."""
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except (TypeError, ValueError):
        return False
    return True


def infer_value_type(value: str) -> str:
    """Infer the logical type of a single string cell value.

    Returns one of ``"int"``, ``"float"``, ``"bool"``, ``"date"``,
    ``"empty"`` or ``"text"``. The empty string is ``"empty"``.
    """
    if value == "":
        return "empty"
    if _is_int(value):
        return "int"
    if _is_float(value):
        return "float"
    if value.lower() in _BOOL_WORDS:
        return "bool"
    if _is_date(value):
        return "date"
    return "text"


def infer_column_type(values: list[str]) -> str:
    """Infer the consensus type for a column of string values.

    Empty cells are ignored. If all remaining cells share a type, that type
    wins; ``int`` and ``float`` mixed together promote to ``"float"``. Any
    other mixture (or an unrecognised value) falls back to ``"text"``. A column
    that is entirely empty (or has no cells) is ``"empty"``.
    """
    seen: set[str] = set()
    for value in values:
        t = infer_value_type(value)
        if t == "empty":
            continue
        seen.add(t)
    if not seen:
        return "empty"
    if len(seen) == 1:
        return next(iter(seen))
    if seen == {"int", "float"}:
        return "float"
    return "text"


def infer_types(rows: list[list[str]], *, header: bool = True) -> list[str]:
    """Infer one type per column across the data rows.

    ``rows`` is a row-major grid of string cells. With ``header=True`` (the
    default) the first row is treated as column names and skipped. Ragged rows
    are tolerated — short rows simply contribute no value to absent columns.
    """
    data = rows[1:] if header else rows
    if not data:
        return []
    n_cols = max((len(row) for row in data), default=0)
    types: list[str] = []
    for c in range(n_cols):
        column = [row[c] for row in data if c < len(row)]
        types.append(infer_column_type(column))
    return types


def coerce(value: str, type_name: str) -> object:
    """Parse a string cell into the Python value implied by ``type_name``.

    Empty strings always coerce to ``None``. On any parse failure the original
    string is returned unchanged, so coercion is always lossless-or-passthrough.

    * ``"int"``   -> ``int``
    * ``"float"`` -> ``float``
    * ``"bool"``  -> ``True`` / ``False``
    * ``"date"``  -> ``datetime.date``
    * anything else (``"text"``, ``"empty"``) -> the string itself
    """
    if value == "":
        return None
    try:
        if type_name == "int":
            return int(value)
        if type_name == "float":
            return float(value)
        if type_name == "bool":
            lowered = value.lower()
            if lowered in _TRUE_WORDS:
                return True
            if lowered in _FALSE_WORDS:
                return False
            return value
        if type_name == "date":
            return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return value
    return value


__all__ = [
    "infer_value_type",
    "infer_column_type",
    "infer_types",
    "coerce",
    "date",
]
