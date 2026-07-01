"""Modern spreadsheet array functions (XLOOKUP, UNIQUE, SORT, FILTER, SEQUENCE).

Pure-stdlib companion to :mod:`abax.core.functions`. Each callable follows the
same eager-function convention: it receives a single ``args`` list of
already-evaluated values, where a *range* argument arrives as a
:class:`abax.core.values.RangeValue` (use ``.flat()`` / ``.grid`` /
``.nrows`` / ``.ncols``) and scalars arrive as plain Python values. Errors are
:class:`abax.core.errors.CellError` values that propagate.

These functions return **plain Python lists** rather than spilling into a
rectangular block of cells. Full grid "spill" (writing an array result across
neighbouring cells) is deliberately **out of scope** for this module: returning
a list lets the results compose inside aggregates, because abax's ``_flatten``
recurses into lists (e.g. ``=SUM(UNIQUE(A1:A9))`` works).

The helpers here are re-implemented locally (rather than imported from
``functions.py``) to keep this module decoupled; ``arrayfuncs`` is imported
lazily by the engine, so a cross-import would be legal, but staying local avoids
any import-cycle surprises.

Register with the engine via :func:`register`, which merges :data:`EAGER`
(UPPERCASE name -> callable) into the engine's function table.
"""

from __future__ import annotations

from typing import Any, Callable

from .errors import CellError
from .values import RangeValue

# --- local coercion helpers (kept independent of functions.py) -------------


def _arg(args: list, i: int, default: Any = None) -> Any:
    return args[i] if i < len(args) else default


def _as_number(v: Any) -> float:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if v is None or v == "":
        return 0.0
    return float(v)  # may raise ValueError


def _try_num(v: Any) -> float | None:
    try:
        return _as_number(v)
    except (TypeError, ValueError):
        return None


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _equal(a: Any, b: Any) -> bool:
    an, bn = _try_num(a), _try_num(b)
    if an is not None and bn is not None and not isinstance(a, str) and not isinstance(b, str):
        return an == bn
    return _text(a).lower() == _text(b).lower()


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1")
    return bool(v)


def _is_blank(v: Any) -> bool:
    return v is None or v == ""


def _flat(v: Any) -> list[Any]:
    """Flatten a RangeValue (or scalar) to a flat list of values."""
    if isinstance(v, RangeValue):
        return v.flat()
    if isinstance(v, list):
        out: list[Any] = []
        for item in v:
            out.extend(_flat(item))
        return out
    return [v]


# --- array functions -------------------------------------------------------


def xlookup(args: list) -> Any:
    """XLOOKUP(lookup_value, lookup_array, return_array, [if_not_found], [match_mode]).

    Exact match only. Returns the ``return_array`` element at the first index
    where ``lookup_array`` matches ``lookup_value``; otherwise ``if_not_found``
    when supplied, else ``#N/A``.
    """
    lookup_value = _arg(args, 0)
    lookup_array = _flat(_arg(args, 1))
    return_array = _flat(_arg(args, 2))
    has_default = len(args) > 3
    if_not_found = _arg(args, 3)
    for i, candidate in enumerate(lookup_array):
        if _equal(candidate, lookup_value):
            return return_array[i] if i < len(return_array) else CellError(CellError.NA)
    return if_not_found if has_default else CellError(CellError.NA)


def unique(args: list) -> list:
    """UNIQUE(range) — distinct non-empty values in first-occurrence order."""
    seen: list[Any] = []
    out: list[Any] = []
    for v in _flat(_arg(args, 0)):
        if _is_blank(v):
            continue
        if any(_equal(v, s) for s in seen):
            continue
        seen.append(v)
        out.append(v)
    return out


def _sort_key(v: Any) -> tuple:
    """Sort key: numbers first (by value), then text (case-insensitive), blanks last."""
    if _is_blank(v):
        return (2, "")
    n = _try_num(v)
    if n is not None and not isinstance(v, str):
        return (0, n)
    return (1, _text(v).lower())


def sort(args: list) -> list:
    """SORT(range, [ascending=TRUE]) — numeric values sort numerically, others
    as text, blanks last."""
    values = list(_flat(_arg(args, 0)))
    ascending = _truthy(_arg(args, 1, True))
    ordered = sorted(values, key=_sort_key)
    if not ascending:
        ordered.reverse()
    return ordered


def filter_(args: list) -> Any:
    """FILTER(range, condition_range) — values of ``range`` where the parallel
    ``condition_range`` value is truthy. Length mismatch -> ``#VALUE!``.

    Named ``filter_`` to avoid shadowing the builtin; registered as ``FILTER``.
    """
    values = _flat(_arg(args, 0))
    conditions = _flat(_arg(args, 1))
    if len(values) != len(conditions):
        return CellError(CellError.VALUE)
    return [v for v, cond in zip(values, conditions) if _truthy(cond)]


def sequence(args: list) -> Any:
    """SEQUENCE(rows, [cols=1], [start=1], [step=1]) — flat list of
    ``rows*cols`` numbers ``start, start+step, ...``."""
    rows = _try_num(_arg(args, 0))
    cols = _try_num(_arg(args, 1, 1))
    start = _try_num(_arg(args, 2, 1))
    step = _try_num(_arg(args, 3, 1))
    if rows is None or cols is None or start is None or step is None:
        return CellError(CellError.VALUE)
    rows, cols = int(rows), int(cols)
    if rows < 0 or cols < 0:
        return CellError(CellError.VALUE)
    count = rows * cols
    return [start + i * step for i in range(count)]


# --- registry --------------------------------------------------------------

EAGER: dict[str, Callable[[list], Any]] = {
    "XLOOKUP": xlookup,
    "UNIQUE": unique,
    "SORT": sort,
    "FILTER": filter_,
    "SEQUENCE": sequence,
}


def register(functions: dict) -> None:
    """Merge :data:`EAGER` into the engine's eager-function table."""
    functions.update(EAGER)
