"""Excel-style structured references (Tables).

A *table* is a named, rectangular region whose first row holds column headers.
Once a region is named as a table, formulas may reference its columns by label
rather than by absolute A1 coordinates:

    =SUM(Sales[Amount])            # the Amount column's data body
    =Sales[@Amount] * Sales[@Qty]  # this row's Amount / Qty cells
    =SUM(Sales[[#Totals],[Amount]])# the totals cell of Amount

This module is pure stdlib. It provides:

* :class:`Table` -- the geometry + header model for one table.
* :class:`TableRegistry` -- a case-insensitive ``name -> Table`` store (the
  integrator attaches an instance to the workbook; ``Workbook`` is untouched).
* :func:`parse_structured_ref` -- parse a ``Table1[...]`` / ``[...]`` string
  into a :class:`StructuredRef` (or ``None`` if it is not a structured ref).
* :func:`resolve_structured_ref` -- turn a :class:`StructuredRef` into a
  ``(sheet, r1, c1, r2, c2)`` zero-based inclusive range.
* :func:`detect_table` -- build a :class:`Table` from a selected region.

All coordinates are zero-based, mirroring :mod:`abax.core.reference` (whose
``parse_a1`` / ``to_a1`` / ``index_to_col`` this module reuses rather than
reimplementing A1 math).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import reference

__all__ = [
    "TableError",
    "Table",
    "TableRegistry",
    "StructuredRef",
    "parse_structured_ref",
    "resolve_structured_ref",
    "detect_table",
    "to_a1_range",
]


class TableError(Exception):
    """Raised when a structured reference names an unknown table/column, or
    resolves against a table that lacks the requested region (e.g. a totals
    row that does not exist)."""


# --- special-region normalization -----------------------------------------

# Canonical region keys (the ``#Item`` specifiers, minus the ``#``, lower-cased
# and space-stripped). ``thisrow`` is handled like the ``@`` shorthand: it sets
# the ``this_row`` flag rather than living on ``region``.
_REGIONS = {
    "all": "all",
    "data": "data",
    "headers": "headers",
    "header": "headers",
    "totals": "totals",
    "total": "totals",
    "thisrow": "thisrow",
}


def _normalize_region(item: str) -> str | None:
    """``"#Headers"`` -> ``"headers"``; unknown specifiers -> ``None``."""
    key = item.lstrip("#").strip().lower().replace(" ", "")
    return _REGIONS.get(key)


# --- the Table model -------------------------------------------------------


@dataclass
class Table:
    """The geometry and headers of one Excel-style table.

    All row/column bounds are zero-based and *inclusive*. The layout is::

        header_row      -> [ H0  H1  H2 ]   <- the column labels
        first_data_row  -> [  .   .   . ]
                           [  .   .   . ]
        last_data_row   -> [  .   .   . ]
        totals_row      -> [  T0  T1  T2 ]   <- optional (None if absent)

    with columns spanning ``first_col .. last_col``.

    ``headers`` are the labels for columns ``first_col .. last_col`` in order;
    ``len(headers)`` should equal the column count (:attr:`width`).
    """

    name: str
    sheet: str
    header_row: int
    first_data_row: int
    last_data_row: int
    first_col: int
    last_col: int
    headers: list[str] = field(default_factory=list)
    totals_row: int | None = None

    def __post_init__(self) -> None:
        # Case-insensitive label -> local (0-based within the table) index.
        # First occurrence wins so a duplicate label never shadows the original.
        self._index: dict[str, int] = {}
        for i, label in enumerate(self.headers):
            self._index.setdefault(str(label).strip().lower(), i)

    # -- derived geometry ---------------------------------------------------

    @property
    def width(self) -> int:
        """Number of columns (``last_col - first_col + 1``)."""
        return self.last_col - self.first_col + 1

    @property
    def columns(self) -> list[str]:
        """The header labels, in left-to-right order."""
        return list(self.headers)

    @property
    def last_row(self) -> int:
        """The last physical row of the table (the totals row if present,
        else :attr:`last_data_row`)."""
        return self.totals_row if self.totals_row is not None else self.last_data_row

    # -- lookups ------------------------------------------------------------

    def has_column(self, name: str) -> bool:
        """Return ``True`` if *name* is a column label (case-insensitive)."""
        return str(name).strip().lower() in self._index

    def column_index(self, name: str) -> int:
        """Absolute (sheet-level) column index for header label *name*.

        Case-insensitive. Raises :class:`TableError` if there is no such column.
        """
        local = self._index.get(str(name).strip().lower())
        if local is None:
            raise TableError(f"unknown column {name!r} in table {self.name!r}")
        return self.first_col + local

    def contains(self, row: int, col: int) -> bool:
        """Return ``True`` if ``(row, col)`` falls anywhere inside the table
        (header, data, or totals row included)."""
        return (
            self.header_row <= row <= self.last_row
            and self.first_col <= col <= self.last_col
        )

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a plain-``dict`` snapshot (JSON-friendly)."""
        return {
            "name": self.name,
            "sheet": self.sheet,
            "header_row": self.header_row,
            "first_data_row": self.first_data_row,
            "last_data_row": self.last_data_row,
            "first_col": self.first_col,
            "last_col": self.last_col,
            "headers": list(self.headers),
            "totals_row": self.totals_row,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Table:
        """Rebuild a :class:`Table` from :meth:`to_dict` output."""
        return cls(
            name=d["name"],
            sheet=d["sheet"],
            header_row=d["header_row"],
            first_data_row=d["first_data_row"],
            last_data_row=d["last_data_row"],
            first_col=d["first_col"],
            last_col=d["last_col"],
            headers=list(d.get("headers", [])),
            totals_row=d.get("totals_row"),
        )


class TableRegistry:
    """A case-insensitive registry of :class:`Table` objects.

    Mirrors :class:`abax.core.names.NameRegistry`: keyed on the upper-cased
    table name, preserving each table's display case. ``Workbook`` is *not*
    modified by this module -- the integrator attaches an instance
    (``wb.tables = TableRegistry()``).
    """

    def __init__(self) -> None:
        self._by_upper: dict[str, Table] = {}
        # Bumped on every mutation, so callers that cache structured-ref
        # resolutions can invalidate cheaply (parallels NameRegistry.version).
        self._version = 0

    @property
    def version(self) -> int:
        """A counter bumped on every mutation (add/remove/rename)."""
        return self._version

    def touch(self) -> None:
        """Bump :attr:`version` after mutating a table's fields in place.

        The registry can't observe direct ``Table`` attribute writes (structural
        row/column shifts edit bounds directly), so such callers bump explicitly
        to invalidate memoized structured-ref resolutions.
        """
        self._version += 1

    def __len__(self) -> int:
        return len(self._by_upper)

    def __iter__(self):
        return iter(self._by_upper.values())

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.upper() in self._by_upper

    def add(self, table: Table) -> None:
        """Add (or overwrite) *table*, keyed case-insensitively on its name."""
        self._by_upper[table.name.upper()] = table
        self._version += 1

    def get(self, name: str) -> Table | None:
        """Return the table named *name* (case-insensitive), or ``None``."""
        return self._by_upper.get(name.upper())

    def has(self, name: str) -> bool:
        """Return ``True`` if a table named *name* exists (case-insensitive)."""
        return name.upper() in self._by_upper

    def remove(self, name: str) -> None:
        """Remove the table named *name*. Raises :class:`TableError` if absent."""
        key = name.upper()
        if key not in self._by_upper:
            raise TableError(f"no such table: {name!r}")
        del self._by_upper[key]
        self._version += 1

    def rename(self, old: str, new: str) -> None:
        """Rename table *old* to *new* (updating the stored display name).

        Raises :class:`TableError` if *old* is missing or *new* collides with a
        different existing table.
        """
        old_key = old.upper()
        if old_key not in self._by_upper:
            raise TableError(f"no such table: {old!r}")
        new_key = new.upper()
        if new_key != old_key and new_key in self._by_upper:
            raise TableError(f"table already exists: {new!r}")
        table = self._by_upper.pop(old_key)
        table.name = new
        self._by_upper[new_key] = table
        self._version += 1

    def names(self) -> list[str]:
        """Display names, sorted case-insensitively."""
        return sorted((t.name for t in self._by_upper.values()), key=str.upper)

    def table_at(self, sheet: str, row: int, col: int) -> Table | None:
        """Return the table covering cell ``(row, col)`` on *sheet*, or ``None``.

        Useful for supplying ``current_table`` / ``current_row`` when a formula
        containing an implicit ``[Col]`` / ``[@Col]`` is entered inside a table.
        """
        for t in self._by_upper.values():
            if t.sheet == sheet and t.contains(row, col):
                return t
        return None

    def to_dict(self) -> dict:
        """Return ``{display_name: table.to_dict()}``."""
        return {t.name: t.to_dict() for t in self._by_upper.values()}

    @classmethod
    def from_dict(cls, d: dict) -> TableRegistry:
        """Rebuild a registry from :meth:`to_dict` output."""
        reg = cls()
        for payload in d.values():
            reg.add(Table.from_dict(payload))
        return reg


# --- the parsed structured reference ---------------------------------------


@dataclass(frozen=True)
class StructuredRef:
    """A parsed structured reference, before it is resolved to coordinates.

    Attributes:
        table: The table name, or ``None`` for a bare ``[Col]`` / ``[@Col]``
            reference that implies the *current* table.
        column: A single column label, or the first label of a span. ``None``
            means "the whole table width" (e.g. ``Table1[#Data]``).
        column_end: The second label of a ``[[Col1]:[Col2]]`` span, else ``None``.
        region: One of ``"all"``, ``"data"``, ``"headers"``, ``"totals"``, or
            ``None`` (the default -- the data body).
        this_row: ``True`` for the ``@`` / ``#This Row`` shorthand.
    """

    table: str | None
    column: str | None = None
    column_end: str | None = None
    region: str | None = None
    this_row: bool = False

    @property
    def is_implicit(self) -> bool:
        """``True`` when no table name was given (bare ``[Col]`` form)."""
        return self.table is None

    @property
    def is_span(self) -> bool:
        """``True`` for a ``[[Col1]:[Col2]]`` column span."""
        return self.column_end is not None


# A table name: same shape as a defined name (letter/underscore, then
# letters/digits/underscore/dot). Kept in sync with abax.core.names._NAME_RE.
def _is_table_name(text: str) -> bool:
    if not text or not (text[0].isalpha() or text[0] == "_"):
        return False
    return all(ch.isalnum() or ch in "_." for ch in text)


def _outer_balanced(selector: str) -> bool:
    """Return ``True`` if *selector* is a single ``[...]`` group whose opening
    bracket closes exactly at the final character (honoring ``'`` escapes)."""
    depth = 0
    i, n = 0, len(selector)
    while i < n:
        ch = selector[i]
        if ch == "'":  # escape: the next char is literal
            i += 2
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i == n - 1
            if depth < 0:
                return False
        i += 1
    return False


def _split_bracket_groups(body: str) -> list[tuple[str, str]] | None:
    """Split a bracketed body into ``(inner, separator)`` groups.

    ``"[#Data],[Amount]"`` -> ``[("#Data", ","), ("Amount", "")]``;
    ``"[Q1]:[Q4]"``        -> ``[("Q1", ":"), ("Q4", "")]``.

    Inner text is un-escaped (``'`` before a special char yields the literal).
    Returns ``None`` if the body is not a well-formed sequence of bracket groups.
    """
    groups: list[tuple[str, str]] = []
    i, n = 0, len(body)
    while i < n:
        while i < n and body[i] == " ":
            i += 1
        if i >= n:
            break
        if body[i] != "[":
            return None
        i += 1
        inner: list[str] = []
        while i < n and body[i] != "]":
            if body[i] == "'" and i + 1 < n:
                inner.append(body[i + 1])
                i += 2
                continue
            inner.append(body[i])
            i += 1
        if i >= n:  # ran off the end with no closing ']'
            return None
        i += 1  # consume ']'
        while i < n and body[i] == " ":
            i += 1
        if i < n:
            sep = body[i]
            if sep not in (",", ":"):
                return None
            i += 1
            groups.append(("".join(inner), sep))
        else:
            groups.append(("".join(inner), ""))
    return groups or None


def parse_structured_ref(text: str) -> StructuredRef | None:
    """Parse an Excel structured reference into a :class:`StructuredRef`.

    Recognizes, with or without a leading table name (a bare form implies the
    current table)::

        Table1[Amount]                  single column (data body)
        Table1[@Amount]                 this-row cell of a column
        Table1[#All] / [#Data]          whole table / data body
        Table1[#Headers] / [#Totals]    the header row / totals row
        Table1[[#Data],[Amount]]        region + column
        Table1[[Q1]:[Q4]]               column span
        [Amount] / [@Amount]            bare (implicit current table)

    Returns ``None`` when *text* is not a structured reference (e.g. a plain
    A1 range, an external ``[Book]Sheet!A1`` ref, or unbalanced brackets), so
    callers can fall through to ordinary reference handling.
    """
    if not isinstance(text, str):
        return None
    s = text.strip()
    open_at = s.find("[")
    if open_at < 0:
        return None

    table_part = s[:open_at]
    selector = s[open_at:]
    table: str | None = None
    if table_part:
        if not _is_table_name(table_part):
            return None
        table = table_part

    # The selector must be exactly one balanced [...] spanning the whole tail.
    if not _outer_balanced(selector):
        return None
    body = selector[1:-1].strip()
    if not body:
        return None

    this_row = False
    if body.startswith("@"):
        this_row = True
        body = body[1:].strip()
        if not body:  # bare "[@]" -> this row, whole width
            return StructuredRef(table, this_row=True)

    # Gather (region, columns) from either a bracketed group list or a bare item.
    if body.startswith("["):
        groups = _split_bracket_groups(body)
        if groups is None:
            return None
    else:
        # A single bare item: "#Data", "Amount", ...
        groups = [(body, "")]

    region: str | None = None
    columns: list[str] = []
    saw_colon = False
    for inner, sep in groups:
        item = inner.strip()
        if sep == ":":
            saw_colon = True
        if item.startswith("#"):
            r = _normalize_region(item)
            if r is None:
                return None
            if r == "thisrow":
                this_row = True
            elif region is not None:
                return None  # two region specifiers
            else:
                region = r
        elif item.startswith("@"):
            this_row = True
            rest = item[1:].strip()
            if rest:
                columns.append(rest)
        else:
            if not item:
                return None
            columns.append(item)

    column: str | None = None
    column_end: str | None = None
    if len(columns) == 1:
        column = columns[0]
    elif len(columns) == 2:
        if not saw_colon:  # two columns are only meaningful as a ':' span
            return None
        column, column_end = columns
    elif len(columns) > 2:
        return None

    return StructuredRef(
        table=table,
        column=column,
        column_end=column_end,
        region=region,
        this_row=this_row,
    )


# --- resolution ------------------------------------------------------------


def _resolve_table(
    ref: StructuredRef,
    registry: TableRegistry,
    current_table: Table | str | None,
) -> Table:
    """Return the concrete :class:`Table` a *ref* targets."""
    if ref.table is not None:
        table = registry.get(ref.table)
        if table is None:
            raise TableError(f"unknown table: {ref.table!r}")
        return table
    # Implicit (bare) reference -> the current table.
    if current_table is None:
        raise TableError(
            "structured reference has no table name and no current-table context"
        )
    if isinstance(current_table, Table):
        return current_table
    table = registry.get(current_table)
    if table is None:
        raise TableError(f"unknown current table: {current_table!r}")
    return table


def resolve_structured_ref(
    ref: StructuredRef,
    registry: TableRegistry,
    *,
    current_table: Table | str | None = None,
    current_row: int | None = None,
) -> tuple[str, int, int, int, int]:
    """Resolve *ref* to ``(sheet, r1, c1, r2, c2)``, zero-based inclusive.

    ``current_table`` supplies the table for a bare ``[Col]`` reference (a
    :class:`Table` or a name to look up). ``current_row`` supplies the row for
    a ``[@Col]`` / ``#This Row`` reference (the absolute 0-based sheet row of
    the formula cell).

    Raises :class:`TableError` on an unknown table, an unknown column, a
    ``[@...]`` without ``current_row``, or a ``#Totals`` request against a
    table that has no totals row.
    """
    table = _resolve_table(ref, registry, current_table)

    # Columns -> (c1, c2).
    if ref.column is None:
        c1, c2 = table.first_col, table.last_col
    elif ref.column_end is not None:
        a = table.column_index(ref.column)
        b = table.column_index(ref.column_end)
        c1, c2 = min(a, b), max(a, b)
    else:
        c1 = c2 = table.column_index(ref.column)

    # Rows -> (r1, r2).
    if ref.this_row:
        if current_row is None:
            raise TableError(
                "this-row reference (@) requires a current row context"
            )
        r1 = r2 = current_row
    elif ref.region == "headers":
        r1 = r2 = table.header_row
    elif ref.region == "totals":
        if table.totals_row is None:
            raise TableError(f"table {table.name!r} has no totals row")
        r1 = r2 = table.totals_row
    elif ref.region == "all":
        r1 = table.header_row
        r2 = table.last_row
    else:  # "data" or None -> the data body
        r1, r2 = table.first_data_row, table.last_data_row

    return table.sheet, r1, c1, r2, c2


def _quote_sheet(sheet: str) -> str:
    """Quote a sheet name for an ``A1`` prefix if it is not a bare identifier.

    Bare names match the tokenizer's ``[A-Za-z_][A-Za-z0-9_.]*``; anything else
    (spaces, punctuation) is wrapped in single quotes with ``''`` escaping.
    """
    if sheet and (sheet[0].isalpha() or sheet[0] == "_") and all(
        ch.isalnum() or ch in "_." for ch in sheet
    ):
        return sheet
    return "'" + sheet.replace("'", "''") + "'"


def to_a1_range(
    sheet: str, r1: int, c1: int, r2: int, c2: int, *, qualify: bool = True
) -> str:
    """Format a resolved range as a sheet-qualified A1 string.

    ``("Sheet1", 2, 2, 4, 2)`` -> ``"Sheet1!C3:C5"``; a 1x1 range collapses to a
    single cell (``"Sheet1!C3"``). With ``qualify=False`` the ``Sheet!`` prefix
    is omitted. Reuses :func:`abax.core.reference.to_a1` -- no A1 math is
    reimplemented here. Handy for splicing a structured ref into an ordinary
    formula (rewrite ``Sales[Amount]`` to ``Sheet1!C3:C5`` before parsing).
    """
    a = reference.to_a1(r1, c1)
    b = reference.to_a1(r2, c2)
    body = a if a == b else f"{a}:{b}"
    if qualify and sheet:
        return f"{_quote_sheet(sheet)}!{body}"
    return body


# --- construction from a selection -----------------------------------------


def _normalize_headers(headers: list[str], width: int) -> list[str]:
    """Return exactly *width* unique, non-empty header labels.

    Blank/missing labels become ``Column1``, ``Column2``, ...; duplicates get a
    numeric suffix (case-insensitively unique), mirroring Excel's auto-naming.
    """
    out: list[str] = []
    seen: set[str] = set()
    for i in range(width):
        raw = headers[i] if i < len(headers) else ""
        label = str(raw).strip() or f"Column{i + 1}"
        candidate = label
        n = 1
        while candidate.lower() in seen:
            n += 1
            candidate = f"{label}{n}"
        seen.add(candidate.lower())
        out.append(candidate)
    return out


def detect_table(
    sheet_name: str,
    r1: int,
    c1: int,
    r2: int,
    c2: int,
    name: str,
    headers: list[str],
    *,
    has_totals: bool = False,
) -> Table:
    """Build a :class:`Table` from a selected region whose first row is the header.

    The region ``(r1, c1)..(r2, c2)`` is normalized (so the arguments may be
    given in any corner order). Its first row becomes the header row and the
    remaining rows the data body; when ``has_totals`` is set the *last* row is
    treated as the totals row instead of data.

    ``headers`` are the labels read from the header row (``len`` need not match
    the column count -- it is padded / de-duplicated to fit, like Excel).
    """
    top, bottom = min(r1, r2), max(r1, r2)
    left, right = min(c1, c2), max(c1, c2)
    width = right - left + 1

    header_row = top
    first_data_row = top + 1
    if has_totals and bottom > first_data_row:
        totals_row: int | None = bottom
        last_data_row = bottom - 1
    else:
        totals_row = None
        last_data_row = bottom
    # A header-only selection still yields a (possibly empty) data body row.
    if last_data_row < first_data_row:
        last_data_row = first_data_row

    return Table(
        name=name,
        sheet=sheet_name,
        header_row=header_row,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        first_col=left,
        last_col=right,
        headers=_normalize_headers(list(headers), width),
        totals_row=totals_row,
    )
