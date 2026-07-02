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
  ``value_col`` for that ``(index, column)`` pair. Optionally adds grand-total
  **margins** (a totals row and/or column), aggregates **multiple value
  fields** at once (each with its own aggregator), and renders cells as a
  **percent-of-total** (of the grand total, or each cell's row/column).
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


def _as_number(text: str) -> float | None:
    """Parse an *already-aggregated* cell back into a float, or ``None``.

    Used when re-expressing a pivot as a percent-of-total: only numeric cells
    participate; blanks and non-numeric aggregates (e.g. a ``first`` of text)
    stay untouched.
    """
    return _to_number(text)


def _fmt_fraction(part: float, whole: float, *, as_percent: bool) -> str:
    """Render ``part / whole`` as a fraction (or percent) cell.

    A zero (or non-finite) ``whole`` yields ``""`` — there is nothing to take a
    share of. ``as_percent`` scales by 100; the raw ratio is used otherwise.
    """
    if whole == 0 or whole != whole or whole in (float("inf"), float("-inf")):
        return ""
    ratio = part / whole
    return _fmt_number(ratio * 100 if as_percent else ratio)


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


# Percent-of-total display modes accepted by :func:`pivot_table`.
_PCT_MODES = frozenset({"grand", "row", "col", "column"})


def pivot_table(
    rows: list[list[str]],
    index_col: str,
    column_col: str,
    value_col: str | None = None,
    agg: str = "sum",
    *,
    margins: bool = False,
    margins_name: str = "Total",
    value_cols: list[str] | None = None,
    aggs: list[str] | None = None,
    pct_of: str | None = None,
    as_percent: bool = True,
) -> list[list[str]]:
    """Spreadsheet pivot of ``rows``.

    ``index_col`` runs down the left, the distinct ``column_col`` values run
    across the top, and each cell is the ``agg`` of ``value_col`` for that
    ``(index, column)`` pair (``""`` where the combination has no data).

    Returns a NEW 2-D block: header ``[index_col, *sorted distinct column_col]``,
    one row per distinct ``index_col`` value (sorted), then the aggregated cells.

    Optional extensions (all backward-compatible — omit them for the classic
    single-value pivot):

    * **margins** — when ``True``, append a grand-total column on the right and a
      grand-total row at the bottom, both labelled ``margins_name``. Margins are
      recomputed from the pooled raw ``value_col`` cells, so a ``mean``/``median``
      total is the true aggregate of all rows/columns (not a sum of cell means).
    * **multiple value fields** — pass ``value_cols`` (a list of column names) and
      optionally ``aggs`` (a matching list of aggregators; defaults to ``agg``
      for every field). Each ``column_col`` value then yields one sub-column per
      value field, headed ``"<colkey> - <agg>(<value_col>)"``. ``value_col`` +
      ``agg`` remain the single-field shorthand.
    * **pct_of** — ``"grand"``, ``"row"``, or ``"col"`` re-expresses each numeric
      body cell as a share of the grand total / its row total / its column total.
      ``as_percent`` (default ``True``) scales the share by 100; pass ``False``
      for a raw fraction. Percent-of works per value field independently. When
      combined with ``margins``, the margin cells hold ``100`` (the whole).

    Raises :class:`PivotError` on an unknown column, aggregation, or ``pct_of``.
    """
    # Resolve the value-field spec: (value_cols, aggs) win; else single field.
    if value_cols is None:
        if value_col is None:
            raise PivotError("pivot_table needs value_col or value_cols")
        fields = [value_col]
        field_aggs = [agg]
    else:
        if not value_cols:
            raise PivotError("value_cols must be non-empty")
        fields = list(value_cols)
        field_aggs = list(aggs) if aggs is not None else [agg] * len(fields)
        if len(field_aggs) != len(fields):
            raise PivotError("aggs must match value_cols in length")
    for a in field_aggs:
        if a not in AGGREGATIONS:
            raise PivotError(f"unknown aggregation: {a!r}")
    if pct_of is not None and pct_of not in _PCT_MODES:
        raise PivotError(f"unknown pct_of mode: {pct_of!r}")
    pct_row = pct_of == "row"
    pct_grand = pct_of == "grand"

    iidx = _header_index(rows, index_col)
    cidx = _header_index(rows, column_col)
    vidxs = [_header_index(rows, f) for f in fields]

    # Per field: bucket the raw value cells by (index, column).
    cells: list[dict[tuple[str, str], list[str]]] = [{} for _ in fields]
    index_keys: set[str] = set()
    column_keys: set[str] = set()
    for row in rows[1:]:
        ikey = _cell(row, iidx)
        ckey = _cell(row, cidx)
        index_keys.add(ikey)
        column_keys.add(ckey)
        for f, vidx in enumerate(vidxs):
            cells[f].setdefault((ikey, ckey), []).append(_cell(row, vidx))

    index_order = _sort_keys(list(index_keys))
    column_order = _sort_keys(list(column_keys))
    multi = value_cols is not None

    def _agg_cell(field: int, ikeys: list[str], ckeys: list[str]) -> str:
        """Aggregate the pooled raw cells over the given index/column keys."""
        pooled: list[str] = []
        for ik in ikeys:
            for ck in ckeys:
                pooled.extend(cells[field].get((ik, ck), []))
        return _aggregate(pooled, field_aggs[field])

    # --- header -----------------------------------------------------------
    header: list[str] = [index_col]
    for ckey in column_order:
        for f in range(len(fields)):
            header.append(f"{ckey} - {field_aggs[f]}({fields[f]})" if multi else ckey)
    if margins:
        for f in range(len(fields)):
            header.append(
                f"{margins_name} - {field_aggs[f]}({fields[f]})" if multi
                else margins_name)
    out = [header]

    # --- body (raw aggregates, kept for margins/percent math) -------------
    body: list[list[str]] = []
    for ikey in index_order:
        cell_row: list[str] = []
        for ckey in column_order:
            for f in range(len(fields)):
                bucket = cells[f].get((ikey, ckey))
                cell_row.append(_aggregate(bucket, field_aggs[f])
                                if bucket is not None else "")
        if margins:
            for f in range(len(fields)):
                cell_row.append(_agg_cell(f, [ikey], column_order))
        body.append(cell_row)
    if margins:
        total_row: list[str] = []
        for ckey in column_order:
            for f in range(len(fields)):
                total_row.append(_agg_cell(f, index_order, [ckey]))
        for f in range(len(fields)):
            total_row.append(_agg_cell(f, index_order, column_order))
        body.append(total_row)

    if pct_of is None:
        for ridx, ikey in enumerate(index_order):
            out.append([ikey, *body[ridx]])
        if margins:
            out.append([margins_name, *body[-1]])
        return out

    # --- percent-of-total re-expression -----------------------------------
    # Column layout: fields cycle fastest, then column_order, then margins.
    n_fields = len(fields)
    n_body_cols = len(column_order) * n_fields
    data_index = index_order + ([margins_name] if margins else [])

    def _grand(field: int) -> float | None:
        return _as_number(_agg_cell(field, index_order, column_order))

    for ridx, ikey in enumerate(data_index):
        src = body[ridx]
        out_row = [ikey]
        for col in range(len(src)):
            field = col % n_fields
            text = src[col]
            part = _as_number(text)
            if part is None:
                out_row.append(text)
                continue
            in_margin_col = col >= n_body_cols
            in_margin_row = margins and ridx == len(data_index) - 1
            if pct_grand:
                whole = _grand(field)
            elif pct_row:
                # Share within this row: its own body cells (the row total).
                # A margin *row* cell is measured against the grand total.
                rkeys = index_order if in_margin_row else [ikey]
                whole = _as_number(_agg_cell(field, rkeys, column_order))
            else:  # pct_col
                # Share within this column: its body cells (the column total).
                # A margin *column* cell is measured against the grand total.
                ckeys = column_order if in_margin_col else [column_order[col // n_fields]]
                whole = _as_number(_agg_cell(field, index_order, ckeys))
            out_row.append(_fmt_fraction(part, whole, as_percent=as_percent)
                           if whole is not None else "")
        out.append(out_row)
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
