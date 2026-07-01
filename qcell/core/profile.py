"""Data profiling — a "describe" for a spreadsheet column or a whole sheet.

Pure standard library (``statistics``, ``collections``). Given a list of cell
values (as produced by :meth:`Sheet.get_value`), :func:`profile_column`
infers a dtype and computes summary statistics; :func:`profile_sheet` runs it
over every used column of a sheet, labelling each with a name.

Dtype inference treats ``None`` and ``""`` as *missing*. A column is numeric
(``bool``/``int``/``float``) only when *every* non-missing value parses as that
type; ``bool`` is tried before ``int`` (a bool is an ``int`` in Python, so the
order matters). Anything else is ``text``. A column with no non-missing values
is ``empty``.
"""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from .reference import index_to_col

_MISSING = (None, "")


def _is_missing(value: Any) -> bool:
    return value is None or value == ""


def _as_bool(value: Any) -> bool | None:
    """Return the bool value, or None if ``value`` is not a clean bool.

    Accepts genuine ``bool`` objects and the strings ``TRUE``/``FALSE``
    (case-insensitive) — the textual form :meth:`Sheet.format_value` emits.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low == "true":
            return True
        if low == "false":
            return False
    return None


def _as_int(value: Any) -> int | None:
    """Return the int value, or None. Rejects bools (handled separately)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _as_float(value: Any) -> float | None:
    """Return the float value, or None. Rejects bools."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _infer_dtype(present: list[Any]) -> str:
    """Pick a dtype for the non-missing values.

    ``bool`` before ``int`` before ``float``; each requires *every* value to
    parse. Falls back to ``text``.
    """
    if not present:
        return "empty"
    if all(_as_bool(v) is not None for v in present):
        return "bool"
    if all(_as_int(v) is not None for v in present):
        return "int"
    if all(_as_float(v) is not None for v in present):
        return "float"
    return "text"


def _numeric_stats(nums: list[float]) -> dict:
    """min/max/mean/median/std/q1/q3 over a non-empty numeric list."""
    stats: dict[str, Any] = {
        "min": min(nums),
        "max": max(nums),
        "mean": statistics.mean(nums),
        "median": statistics.median(nums),
        # Population standard deviation; 0.0 for a single value.
        "std": statistics.pstdev(nums) if len(nums) >= 2 else 0.0,
    }
    if len(nums) >= 2:
        # statistics.quantiles(n=4) → the three cut points [q1, q2, q3].
        q1, _q2, q3 = statistics.quantiles(nums, n=4)
        stats["q1"] = q1
        stats["q3"] = q3
    else:
        stats["q1"] = nums[0]
        stats["q3"] = nums[0]
    return stats


def profile_column(values: list[Any]) -> dict:
    """Profile a single column given its list of cell values.

    ``None`` and ``""`` count as missing. Always returns ``dtype``, ``count``
    (non-missing), ``missing``, ``unique`` (distinct non-missing). Numeric
    dtypes add ``min/max/mean/median/std/q1/q3``; ``text`` adds ``max_len`` and
    ``top`` (up to five most-common ``(value, count)`` pairs, ties broken by
    first appearance).
    """
    present = [v for v in values if not _is_missing(v)]
    dtype = _infer_dtype(present)

    profile: dict[str, Any] = {
        "dtype": dtype,
        "count": len(present),
        "missing": len(values) - len(present),
        "unique": len(set(present)),
    }

    if dtype in ("bool", "int", "float"):
        if dtype == "bool":
            nums = [1.0 if _as_bool(v) else 0.0 for v in present]
        elif dtype == "int":
            nums = [float(_as_int(v)) for v in present]
        else:
            nums = [_as_float(v) for v in present]
        profile.update(_numeric_stats(nums))
    elif dtype == "text":
        texts = [str(v) for v in present]
        profile["max_len"] = max((len(t) for t in texts), default=0)
        # Counter.most_common is insertion-ordered on ties (Python 3.7+),
        # which gives the required "first appearance" tie-break.
        profile["top"] = Counter(texts).most_common(5)

    return profile


def profile_sheet(sheet, header_row: bool = True) -> list[dict]:
    """Profile every used column of ``sheet``, one dict per column.

    Each dict is a :func:`profile_column` result plus a ``"name"`` key. When
    ``header_row`` is True the first row supplies column names and is excluded
    from the profiled data; otherwise names are the column letters (A, B, …).
    """
    nrows, ncols = sheet.used_bounds()
    data_start = 1 if header_row else 0

    profiles: list[dict] = []
    for col in range(ncols):
        values = [sheet.get_value(row, col) for row in range(data_start, nrows)]
        profile = profile_column(values)

        if header_row:
            header = sheet.get_value(0, col)
            name = str(header) if not _is_missing(header) else index_to_col(col)
        else:
            name = index_to_col(col)
        profile["name"] = name
        profiles.append(profile)

    return profiles
