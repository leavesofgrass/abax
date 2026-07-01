"""Shared coercion helpers for the built-in spreadsheet functions.

The toolbox the function implementations lean on: flatten range/array args,
coerce to numbers/text, compare Excel-style. Pure stdlib.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..errors import CellError, is_error
from ..values import RangeValue

# --- coercion helpers ------------------------------------------------------


def _flatten(args: Iterable[Any]) -> list[Any]:
    out: list[Any] = []
    for a in args:
        if isinstance(a, RangeValue):
            out.extend(a.flat())
        elif isinstance(a, list):
            out.extend(_flatten(a))
        else:
            out.append(a)
    return out


def _first_error(values: Iterable[Any]) -> CellError | None:
    for v in values:
        if is_error(v):
            return v
    return None


def _numbers_from(flat: Iterable[Any]) -> list[float]:
    """Keep only numeric values from an already-flattened iterable (SUM/AVERAGE rules)."""
    nums: list[float] = []
    for v in flat:
        if isinstance(v, bool):
            nums.append(1.0 if v else 0.0)
        elif isinstance(v, (int, float)):
            nums.append(float(v))
    return nums


def _numbers(args: Iterable[Any]) -> list[float]:
    """Flatten and keep only numeric values (Excel SUM/AVERAGE rules)."""
    return _numbers_checked(args)[1]


def _numbers_checked(args: Iterable[Any]) -> "tuple[CellError | None, list[float]]":
    """Single traversal of the flattened arguments, returning ``(first_error,
    numbers)``.

    Fuses :func:`_flatten`, :func:`_first_error` and :func:`_numbers_from` into
    one pass: a range is walked once and only the numeric list is built -- the
    full value list is never materialized. For ``SUM(A1:A100000)`` that drops two
    whole-range allocations (the flat list and a separate error scan). The
    returned ``numbers`` and ``first_error`` are byte-for-byte what
    ``_numbers_from(_flatten(args))`` and ``_first_error(_flatten(args))`` would
    produce over the same arguments (same values, same flatten order), so every
    aggregate keeps Excel's exact SUM/AVERAGE numeric and error-propagation
    semantics."""
    nums: list[float] = []
    push = nums.append
    state: list[CellError | None] = [None]

    def leaf(v: Any) -> None:
        if isinstance(v, bool):
            push(1.0 if v else 0.0)
        elif isinstance(v, (int, float)):
            push(float(v))
        elif state[0] is None and is_error(v):
            state[0] = v

    def walk(items: Iterable[Any]) -> None:
        for a in items:
            if isinstance(a, RangeValue):
                for row in a.grid:
                    for v in row:
                        if isinstance(v, bool):
                            push(1.0 if v else 0.0)
                        elif isinstance(v, (int, float)):
                            push(float(v))
                        elif state[0] is None and is_error(v):
                            state[0] = v
            elif isinstance(a, list):
                walk(a)
            else:
                leaf(a)

    walk(args)
    return state[0], nums


def _flat_checked(args: Iterable[Any]) -> "tuple[CellError | None, list[Any]]":
    """Flatten once, returning ``(first_error, flat_list)`` so callers that need
    both an error short-circuit and the values don't flatten the args twice."""
    flat = _flatten(args)
    return _first_error(flat), flat


def _as_number(v: Any) -> float:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if v is None or v == "":
        return 0.0
    return float(v)  # may raise ValueError -> caught by the dispatcher


def _try_num(v: Any) -> float | None:
    try:
        return _as_number(v)
    except (TypeError, ValueError):
        return None


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1")
    return bool(v)


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


def _arg(args: list, i: int, default: Any = None) -> Any:
    return args[i] if i < len(args) else default




__all__ = [
    "_flatten",
    "_first_error",
    "_numbers_from",
    "_numbers",
    "_numbers_checked",
    "_flat_checked",
    "_as_number",
    "_try_num",
    "_truthy",
    "_text",
    "_equal",
    "_arg",
]
