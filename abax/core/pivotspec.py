"""Field-area pivot builder — the logic behind the drag-drop PivotTable sidebar.

Excel's PivotTable Fields pane sorts columns into four areas: **Filters**,
**Columns**, **Rows**, and **Values**. This module turns such an assignment
(:class:`PivotSpec`) into a finished 2-D block by routing to the already-tested
primitives in :mod:`abax.core.pivot`:

* no Columns field  → :func:`~abax.core.pivot.group_by` over the Row fields
  (one aggregated column per Value field, merged on the group key);
* one Columns field → :func:`~abax.core.pivot.pivot_table` (multiple Row fields
  are joined into one composite index column, since the classic pivot indexes on
  a single field), with the Value fields as ``value_cols``.

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


def _composite_index(rows: list[list[str]], row_fields: list[str]) -> tuple[list[list[str]], str]:
    """Add a derived column joining *row_fields*; return (new_rows, its_name)."""
    name = " / ".join(row_fields)
    existing = field_names(rows)
    while name in existing:
        name += " "
    idxs = [_header_index(rows, f) for f in row_fields]
    new_rows = [[*rows[0], name]]
    for row in rows[1:]:
        new_rows.append([*row, " / ".join(_cell(row, i) for i in idxs)])
    return new_rows, name


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

    # One column field → classic pivot. Collapse multiple row fields into a
    # single composite index column (the pivot indexes on one field).
    if len(spec.row_fields) > 1:
        data, index_col = _composite_index(data, spec.row_fields)
    else:
        index_col = spec.row_fields[0]

    if len(spec.value_fields) == 1:
        return pivot_table(
            data, index_col, spec.column_field, spec.value_fields[0], aggs[0],
            margins=spec.margins, pct_of=spec.pct_of)
    return pivot_table(
        data, index_col, spec.column_field,
        value_cols=spec.value_fields, aggs=aggs,
        margins=spec.margins, pct_of=spec.pct_of)
