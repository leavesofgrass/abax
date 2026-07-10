"""Field-area pivot builder — the logic behind the drag-drop PivotTable sidebar.

Excel's PivotTable Fields pane sorts columns into four areas: **Filters**,
**Columns**, **Rows**, and **Values**. This module turns such an assignment
(:class:`PivotSpec`) into a finished 2-D block by routing to the already-tested
primitives in :mod:`abax.core.pivot`:

* no Columns field  → :func:`~abax.core.pivot.group_by` over the Row fields
  (one aggregated column per Value field, merged on the group key);
* one Columns field → :func:`~abax.core.pivot.pivot_table` with the Value fields
  as ``value_cols``. A single Row field indexes the pivot directly; **multiple**
  Row fields are pivoted on a composite index that is then split back into one
  leading column per row field (true nested rows), so the group keys stay in
  their own columns rather than collapsing into one ``" / "``-joined string.

Filters keep only the rows whose cell in a filter field equals a chosen value.
Keeping this pure (no Qt) makes the whole builder unit-testable; the sidebar is a
thin shell that assembles a :class:`PivotSpec` and renders the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .pivot import PivotError, _cell, _header_index, group_by, pivot_table

#: Filter sentinel meaning "keep every value of this field" (no restriction).
ALL = "(All)"


@dataclass
class PivotSpec:
    """A field-area assignment for a pivot, mirroring Excel's four boxes."""

    row_fields: list[str] = field(default_factory=list)
    column_field: str | None = None
    value_fields: list[str] = field(default_factory=list)
    aggs: list[str] = field(default_factory=list)  # parallel to value_fields
    filters: dict[str, str] = field(default_factory=dict)  # field -> keep-value
    margins: bool = False
    pct_of: str | None = None

    def normalized_aggs(self) -> list[str]:
        """Aggregations padded/truncated to match ``value_fields`` (default sum)."""
        out = list(self.aggs)
        while len(out) < len(self.value_fields):
            out.append("sum")
        return out[: len(self.value_fields)]


def field_names(rows: list[list[str]]) -> list[str]:
    """The header row as a list of field names (``[]`` for an empty block)."""
    return [str(h) for h in rows[0]] if rows else []


def distinct_values(rows: list[list[str]], name: str) -> list[str]:
    """Sorted distinct values found in field *name* (for a filter drop-down)."""
    idx = _header_index(rows, name)
    seen = {_cell(r, idx) for r in rows[1:]}
    return sorted(seen)


def filter_values(rows: list[list[str]], field: str) -> list[str]:
    """Keep-value picker options for a filter *field*.

    Reuses :func:`distinct_values`, prefixing the :data:`ALL` sentinel so the UI
    can offer "no restriction" as the default choice: ``[ALL, *distinct]``.
    """
    return [ALL, *distinct_values(rows, field)]


def _apply_filters(rows: list[list[str]], filters: dict[str, str]) -> list[list[str]]:
    active = {f: v for f, v in filters.items() if v not in (None, "", ALL)}
    if not active:
        return rows
    idx = {f: _header_index(rows, f) for f in active}
    out = [rows[0]]
    for row in rows[1:]:
        if all(_cell(row, idx[f]) == v for f, v in active.items()):
            out.append(row)
    return out


def _composite_index(
    rows: list[list[str]], row_fields: list[str],
) -> tuple[list[list[str]], str, dict[str, tuple[str, ...]]]:
    """Add a derived column joining *row_fields*.

    Returns ``(new_rows, name, mapping)`` where *mapping* takes each composite
    cell string back to the tuple of individual row-field values — so a nested
    pivot can split the joined index back into one column per row field.
    """
    name = " / ".join(row_fields)
    existing = field_names(rows)
    while name in existing:
        name += " "
    idxs = [_header_index(rows, f) for f in row_fields]
    new_rows = [[*rows[0], name]]
    mapping: dict[str, tuple[str, ...]] = {}
    for row in rows[1:]:
        key = tuple(_cell(row, i) for i in idxs)
        joined = " / ".join(key)
        mapping[joined] = key
        new_rows.append([*row, joined])
    return new_rows, name, mapping


def _split_nested_rows(
    result: list[list[str]], row_fields: list[str],
    mapping: dict[str, tuple[str, ...]], margins_name: str = "Total",
) -> list[list[str]]:
    """Split a composite-index pivot's leading column into per-row-field columns.

    *result* is a :func:`~abax.core.pivot.pivot_table` block whose first column
    holds the ``" / "``-joined row-field keys. Replace that single column with
    ``len(row_fields)`` separate columns, repeating each group's key values. A
    grand-total (margins) row keyed *margins_name* keeps that label in the first
    column with the remaining leading columns left blank.
    """
    n = len(row_fields)
    out = [[*row_fields, *result[0][1:]]]
    for row in result[1:]:
        key = row[0]
        tup = mapping.get(key)
        if tup is not None:
            lead = list(tup)
        elif key == margins_name:
            lead = [margins_name, *[""] * (n - 1)]
        else:  # defensive: fall back to splitting the joined string
            lead = (key.split(" / ") + [""] * n)[:n]
        out.append([*lead, *row[1:]])
    return out


def _group_multi(rows: list[list[str]], row_fields: list[str],
                 value_fields: list[str], aggs: list[str]) -> list[list[str]]:
    """group_by over *row_fields*, one aggregated column per value field."""
    base = group_by(rows, row_fields, value_fields[0], aggs[0])
    n = len(row_fields)
    for value, agg in zip(value_fields[1:], aggs[1:]):
        extra = group_by(rows, row_fields, value, agg)
        mapping = {tuple(r[:n]): r[-1] for r in extra[1:]}
        base[0].append(extra[0][-1])
        for r in base[1:]:
            r.append(mapping.get(tuple(r[:n]), ""))
    return base


def build_pivot(rows: list[list[str]], spec: PivotSpec) -> list[list[str]]:
    """Render *spec* against *rows*, returning a new header+body 2-D block.

    Raises :class:`PivotError` if the spec is unsatisfiable (no rows, no value
    fields, or an unknown column/aggregation surfaced by the primitives).
    """
    if not rows:
        raise PivotError("no data to pivot")
    if not spec.row_fields:
        raise PivotError("add at least one Rows field")
    if not spec.value_fields:
        raise PivotError("add at least one Values field")

    data = _apply_filters(rows, spec.filters)
    aggs = spec.normalized_aggs()

    if not spec.column_field:
        return _group_multi(data, spec.row_fields, spec.value_fields, aggs)

    # One column field → classic pivot. A single row field indexes directly; two
    # or more are pivoted on a composite index, then split back into separate
    # leading columns (true nested rows) rather than a joined string.
    if len(spec.row_fields) > 1:
        composite, index_col, mapping = _composite_index(data, spec.row_fields)
        result = _pivot_block(composite, index_col, spec, aggs)
        return _split_nested_rows(result, spec.row_fields, mapping)

    return _pivot_block(data, spec.row_fields[0], spec, aggs)


def _pivot_block(rows: list[list[str]], index_col: str, spec: PivotSpec,
                 aggs: list[str]) -> list[list[str]]:
    """Run :func:`~abax.core.pivot.pivot_table` for *spec* on a single index col."""
    if len(spec.value_fields) == 1:
        return pivot_table(
            rows, index_col, spec.column_field, spec.value_fields[0], aggs[0],
            margins=spec.margins, pct_of=spec.pct_of)
    return pivot_table(
        rows, index_col, spec.column_field,
        value_cols=spec.value_fields, aggs=aggs,
        margins=spec.margins, pct_of=spec.pct_of)
