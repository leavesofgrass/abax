"""Group-by / pivot-table engine — pure stdlib, so it lives in core.

The brain behind abax's "Pivot / group-by" tool. Input is a 2-D block of
**string** cells: ``rows: list[list[str]]`` where ``rows[0]`` is the header
(column names) and the rest are data rows. Data rows are *ragged-tolerant* — a
short row's missing trailing cells are treated as blanks (``""``). Columns are
addressed by **name** (the header text), not by index.

Three operations, all returning a NEW 2-D ``list[list[str]]`` block:

* :func:`group_by` — group data rows by the tuple of values in one or more
  ``group_cols`` and aggregate ``value_col`` with one of :data:`AGGREGATIONS`.
* :func:`pivot_table` — a spreadsheet pivot: ``index_col`` down the left,
  distinct ``column_col`` values across the top, each cell the aggregate of
  ``value_col`` for that ``(index, column)`` pair.
* :func:`crosstab` — a frequency cross-tabulation (counts of co-occurrences),
  the same shape as a ``pivot_table`` with ``agg="count"``.

Conventions shared by every operation:

* A **blank** cell is the empty string ``""``.
* **Numeric** aggregations (``sum``/``mean``/``min``/``max``/``median``/``std``)
  parse ``value_col`` with :func:`_to_number`, which *skips* blanks and
  non-numeric cells rather than raising — a group with no numeric values
  aggregates to ``""``.
* ``count`` counts the non-blank ``value_col`` entries; ``nunique`` counts the
  distinct non-blank entries; ``first`` is the first non-blank entry.
* ``std`` is the **sample** standard deviation (``statistics.stdev``, ``n-1``);
  with fewer than two numeric values it is ``"0"`` (or ``""`` when there are
  none).
* Group keys and column headers are sorted **naturally**: numerically when every
  key parses as a number, else lexicographically.
* Floats render compactly (``%g``-ish); whole numbers drop the trailing ``.0``.

Bad arguments (an unknown column name, an unknown aggregation) raise
:class:`PivotError` rather than returning a bogus block.
"""

from __future__ import annotations

import statistics


class PivotError(Exception):
    """Raised when a pivot / group-by operation cannot produce a valid result."""


# Aggregation name -> human label, for a GUI to enumerate the options.
AGGREGATIONS: dict[str, str] = {
    "sum": "Sum",
    "mean": "Mean",
    "count": "Count",
    "min": "Min",
    "max": "Max",
    "median": "Median",
    "std": "Std dev (sample)",
    "nunique": "Distinct count",
    "first": "First",
}

# Aggregations that parse value_col as numbers (blanks/non-numeric skipped).
_NUMERIC_AGGS = frozenset({"sum", "mean", "min", "max", "median", "std"})


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _to_number(value: str) -> float | None:
    """Parse a cell as a float for a numeric aggregation.

    Blank cells and cells that are not plain numbers return ``None`` (skipped by
    the caller) — numeric aggregations never raise on dirty data, they ignore it.
    """
    if value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_number(x: float) -> str:
    """Render a float as compact ``%g``-ish text (``5.0`` -> ``"5"``)."""
    if x != x or x in (float("inf"), float("-inf")):
        return repr(x)
    return f"{x:.12g}"


def _header_index(rows: list[list[str]], name: str) -> int:
    """Return the column index of ``name`` in the header (``rows[0]``).

    Raises :class:`PivotError` if there is no header or no such column.
    """
    if not rows:
        raise PivotError("no header row")
    header = rows[0]
    try:
        return header.index(name)
    except ValueError:
        raise PivotError(f"unknown column: {name!r}")


def _cell(row: list[str], idx: int) -> str:
    """Fetch ``row[idx]``, treating an out-of-range index as a blank cell."""
    return row[idx] if idx < len(row) else ""


def _sort_keys(keys: list[str]) -> list[str]:
    """Sort distinct string keys naturally: numeric if all parse, else lexical."""
    parsed = [_to_number(k) for k in keys]
    if keys and all(p is not None for p in parsed):
        return sorted(keys, key=lambda k: (float(k), k))
    return sorted(keys)


def _aggregate(texts: list[str], agg: str) -> str:
    """Aggregate the ``value_col`` cells ``texts`` (a single group) per ``agg``.

    Numeric aggregations skip blanks and non-numeric cells; an empty numeric
    group yields ``""``. ``count``/``nunique``/``first`` work on the raw
    non-blank cells.
    """
    if agg in _NUMERIC_AGGS:
        nums = [n for t in texts if (n := _to_number(t)) is not None]
        if not nums:
            return ""
        if agg == "sum":
            return _fmt_number(sum(nums))
        if agg == "mean":
            return _fmt_number(statistics.mean(nums))
        if agg == "min":
            return _fmt_number(min(nums))
        if agg == "max":
            return _fmt_number(max(nums))
        if agg == "median":
            return _fmt_number(statistics.median(nums))
        # std: sample standard deviation; n < 2 -> "0".
        if len(nums) < 2:
            return "0"
        return _fmt_number(statistics.stdev(nums))

    nonblank = [t for t in texts if t != ""]
    if agg == "count":
        return str(len(nonblank))
    if agg == "nunique":
        return str(len(set(nonblank)))
    if agg == "first":
        return nonblank[0] if nonblank else ""
    raise PivotError(f"unknown aggregation: {agg!r}")


# --------------------------------------------------------------------------- #
# operations                                                                   #
# --------------------------------------------------------------------------- #
def group_by(
    rows: list[list[str]],
    group_cols: list[str],
    value_col: str,
    agg: str = "sum",
) -> list[list[str]]:
    """Group data rows by ``group_cols`` and aggregate ``value_col`` with ``agg``.

    Returns a NEW 2-D block whose header is ``[*group_cols, f"{agg}({value_col})"]``
    followed by one row per group: the group key values then the aggregated value
    as text. Groups are sorted by their key tuple (each component naturally —
    numeric if every value of that component parses as a number, else lexical).

    Raises :class:`PivotError` on an unknown column or aggregation.
    """
    if agg not in AGGREGATIONS:
        raise PivotError(f"unknown aggregation: {agg!r}")
    if not group_cols:
        raise PivotError("group_by needs at least one group column")

    gidx = [_header_index(rows, c) for c in group_cols]
    vidx = _header_index(rows, value_col)

    # Collect value_col cells per group key, preserving first-seen order of keys.
    groups: dict[tuple[str, ...], list[str]] = {}
    for row in rows[1:]:
        key = tuple(_cell(row, i) for i in gidx)
        groups.setdefault(key, []).append(_cell(row, vidx))

    # Sort each group-key component naturally and independently.
    keys = list(groups.keys())
    for col in range(len(group_cols) - 1, -1, -1):
        order = {k: i for i, k in enumerate(_sort_keys(sorted({key[col] for key in keys})))}
        keys.sort(key=lambda key, c=col, o=order: o[key[c]])

    header = [*group_cols, f"{agg}({value_col})"]
    out = [header]
    for key in keys:
        out.append([*key, _aggregate(groups[key], agg)])
    return out


def pivot_table(
    rows: list[list[str]],
    index_col: str,
    column_col: str,
    value_col: str,
    agg: str = "sum",
) -> list[list[str]]:
    """Spreadsheet pivot of ``rows``.

    ``index_col`` runs down the left, the distinct ``column_col`` values run
    across the top, and each cell is the ``agg`` of ``value_col`` for that
    ``(index, column)`` pair (``""`` where the combination has no data).

    Returns a NEW 2-D block: header ``[index_col, *sorted distinct column_col]``,
    one row per distinct ``index_col`` value (sorted), then the aggregated cells.

    Raises :class:`PivotError` on an unknown column or aggregation.
    """
    if agg not in AGGREGATIONS:
        raise PivotError(f"unknown aggregation: {agg!r}")

    iidx = _header_index(rows, index_col)
    cidx = _header_index(rows, column_col)
    vidx = _header_index(rows, value_col)

    cells: dict[tuple[str, str], list[str]] = {}
    index_keys: set[str] = set()
    column_keys: set[str] = set()
    for row in rows[1:]:
        ikey = _cell(row, iidx)
        ckey = _cell(row, cidx)
        index_keys.add(ikey)
        column_keys.add(ckey)
        cells.setdefault((ikey, ckey), []).append(_cell(row, vidx))

    index_order = _sort_keys(list(index_keys))
    column_order = _sort_keys(list(column_keys))

    out = [[index_col, *column_order]]
    for ikey in index_order:
        row_out = [ikey]
        for ckey in column_order:
            bucket = cells.get((ikey, ckey))
            row_out.append(_aggregate(bucket, agg) if bucket is not None else "")
        out.append(row_out)
    return out


def crosstab(
    rows: list[list[str]],
    index_col: str,
    column_col: str,
) -> list[list[str]]:
    """Frequency cross-tabulation of ``index_col`` against ``column_col``.

    Each cell is the count of data rows with that ``(index, column)`` pair. The
    shape matches :func:`pivot_table` with ``agg="count"``: header
    ``[index_col, *sorted distinct column_col]``, one row per distinct index
    value, counts in the body (``0`` where a pair never co-occurs). No margins.

    Raises :class:`PivotError` on an unknown column name.
    """
    iidx = _header_index(rows, index_col)
    cidx = _header_index(rows, column_col)

    counts: dict[tuple[str, str], int] = {}
    index_keys: set[str] = set()
    column_keys: set[str] = set()
    for row in rows[1:]:
        ikey = _cell(row, iidx)
        ckey = _cell(row, cidx)
        index_keys.add(ikey)
        column_keys.add(ckey)
        pair = (ikey, ckey)
        counts[pair] = counts.get(pair, 0) + 1

    index_order = _sort_keys(list(index_keys))
    column_order = _sort_keys(list(column_keys))

    out = [[index_col, *column_order]]
    for ikey in index_order:
        out.append([ikey, *(str(counts.get((ikey, ckey), 0)) for ckey in column_order)])
    return out


__all__ = [
    "PivotError",
    "AGGREGATIONS",
    "group_by",
    "pivot_table",
    "crosstab",
]
