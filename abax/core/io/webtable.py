"""Extract HTML ``<table>`` elements into text grids — stdlib only, so it lives
in core.

Fed a chunk of HTML (a whole page or a fragment), :func:`tables_from_html`
returns one rectangular grid per ``<table>`` it finds, with every cell reduced
to its plain text. ``<thead>``/``<tbody>``/``<tfoot>`` are flattened away — a
header row and the body rows land in one grid, in document order — because the
callers here treat row 0 as the header regardless of how the markup grouped it.

The parser is deliberately small and forgiving (built on :mod:`html.parser`,
which tolerates the unclosed ``<td>``/``<tr>`` that real pages are littered
with) rather than a strict tree builder:

* Cell text is the concatenation of all character data inside the cell, with
  runs of whitespace collapsed to single spaces and the ends trimmed. Nested
  inline markup (``<a>``, ``<b>``, ``<span>`` ...) contributes its text;
  ``<br>`` becomes a space. HTML entities are unescaped (``html.parser`` hands
  us already-decoded text for ``&amp;`` and friends).
* ``colspan`` is honoured by repeating the cell's text across that many columns
  (a common, lossless-enough choice — the alternative of one wide cell does not
  fit a rectangular grid). ``rowspan`` is honoured by carrying the cell down
  into the following rows' same column so later rows stay column-aligned.
* Nested tables are returned as their own separate grids (the inner table's
  text does **not** also appear inside the outer cell), listed after the row of
  the outer table that contained them.

Every returned grid is padded to a rectangle: each row is the same length as
the widest row of that table.
"""

from __future__ import annotations

from html.parser import HTMLParser

__all__ = [
    "tables_from_html",
    "largest_table_from_html",
    "WebTableError",
]

# Tags whose *text* we drop entirely (script/style bodies are not user content).
_SKIP_CONTENT_TAGS = frozenset({"script", "style"})

# Cell-level tags (a new cell starts at either of these).
_CELL_TAGS = frozenset({"td", "th"})


class WebTableError(Exception):
    """Raised when HTML cannot be parsed into any table."""


class _Cell:
    """One in-progress table cell: accumulated text plus its span attributes."""

    __slots__ = ("parts", "colspan", "rowspan")

    def __init__(self, colspan: int, rowspan: int) -> None:
        self.parts: list[str] = []
        self.colspan = colspan
        self.rowspan = rowspan

    def text(self) -> str:
        # Join fragments, collapse internal whitespace, trim the ends.
        return " ".join("".join(self.parts).split())


class _Table:
    """A table being assembled: a list of rows, each a list of finished cells.

    ``rowspan`` is tracked with ``_pending`` — a map from column index to the
    ``(text, rows_left)`` still owed to lower rows in that column."""

    __slots__ = ("rows", "cur", "_pending", "_col")

    def __init__(self) -> None:
        self.rows: list[list[str]] = []
        self.cur: list[str] | None = None
        # column -> [text, rows_left] carried down by a rowspan.
        self._pending: dict[int, list] = {}
        self._col = 0

    def start_row(self) -> None:
        self.cur = []
        self._col = 0
        self._fill_pending()

    def _fill_pending(self) -> None:
        """Emit any rowspan-carried cells that occupy the current column."""
        while self._col in self._pending:
            carried = self._pending[self._col]
            assert self.cur is not None
            self.cur.append(carried[0])
            self._col += 1
            carried[1] -= 1
            if carried[1] <= 0:
                del self._pending[self._col - 1]

    def add_cell(self, cell: _Cell) -> None:
        if self.cur is None:  # a <td> outside any <tr>: start an implicit row.
            self.start_row()
        assert self.cur is not None
        text = cell.text()
        span = max(1, cell.colspan)
        for _ in range(span):
            self.cur.append(text)
            self._col += 1
            if cell.rowspan > 1:
                # Owe this column's text to the next rowspan-1 rows.
                self._pending[self._col - 1] = [text, cell.rowspan - 1]
            self._fill_pending()

    def end_row(self) -> None:
        if self.cur is not None:
            self.rows.append(self.cur)
        self.cur = None

    def finish(self) -> list[list[str]]:
        self.end_row()
        width = max((len(r) for r in self.rows), default=0)
        for r in self.rows:
            if len(r) < width:
                r.extend([""] * (width - len(r)))
        return self.rows


class _TableParser(HTMLParser):
    """Collect every ``<table>`` (including nested ones) as text grids.

    A stack of open ``_Table`` builders lets nested tables be assembled
    independently; each finished table is appended to ``self.tables`` in the
    order its ``</table>`` is seen, which for nested tables is inner-before-outer
    — matching the "listed after the containing row" contract."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._stack: list[_Table] = []
        self._cell: _Cell | None = None
        self._skip_depth = 0

    # -- helpers -----------------------------------------------------------

    @property
    def _top(self) -> _Table | None:
        return self._stack[-1] if self._stack else None

    def _close_open_cell(self) -> None:
        if self._cell is not None and self._top is not None:
            self._top.add_cell(self._cell)
        self._cell = None

    # -- tag handling ------------------------------------------------------

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_CONTENT_TAGS:
            self._skip_depth += 1
            return
        if tag == "table":
            # A new <td> implicitly closed the previous cell of the outer table.
            self._close_open_cell()
            self._stack.append(_Table())
            return
        if not self._stack:
            return
        if tag == "tr":
            self._close_open_cell()
            self._top.end_row()
            self._top.start_row()
        elif tag in _CELL_TAGS:
            self._close_open_cell()
            self._cell = _Cell(_span(attrs, "colspan"), _span(attrs, "rowspan"))
        elif tag == "br" and self._cell is not None:
            self._cell.parts.append(" ")

    def handle_startendtag(self, tag: str, attrs) -> None:
        # Self-closing form, e.g. <br/> — treat like a start tag (no body).
        if tag == "br" and self._cell is not None:
            self._cell.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_CONTENT_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if tag == "table":
            self._close_open_cell()
            if self._stack:
                grid = self._stack.pop().finish()
                self.tables.append(grid)
            return
        if not self._stack:
            return
        if tag in _CELL_TAGS:
            self._close_open_cell()
        elif tag == "tr":
            self._close_open_cell()
            self._top.end_row()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._cell is not None:
            self._cell.parts.append(data)


def _span(attrs, name: str) -> int:
    """Parse a ``colspan``/``rowspan`` attribute; default 1, clamp junk to 1."""
    for key, value in attrs:
        if key == name and value is not None:
            try:
                n = int(value.strip())
            except ValueError:
                return 1
            return n if n > 0 else 1
    return 1


def tables_from_html(html_text: str) -> list[list[list[str]]]:
    """Return one text grid per ``<table>`` found in ``html_text``.

    Each grid is ``list[rows]`` of ``list[cell_text]``, rectangular (all rows
    padded to the widest row). ``<thead>``/``<tbody>``/``<tfoot>`` are ignored
    as structure — their rows are flattened in document order. ``colspan``
    repeats a cell's text; ``rowspan`` carries it into following rows. Nested
    tables are returned as their own grids (inner before outer).

    Never raises for malformed markup — an input with no tables yields ``[]``.
    """
    parser = _TableParser()
    parser.feed(html_text)
    parser.close()
    return parser.tables


def largest_table_from_html(html_text: str) -> list[list[str]]:
    """Return the single largest table grid in ``html_text``.

    "Largest" is by total cell count (rows x width), which picks the real data
    table over small layout/navigation tables. Ties go to the earliest table in
    document order. Raises :class:`WebTableError` when the HTML has no table.
    """
    tables = tables_from_html(html_text)
    if not tables:
        raise WebTableError("no <table> found in HTML")

    def size(grid: list[list[str]]) -> int:
        return len(grid) * (len(grid[0]) if grid else 0)

    best_i = 0
    best = size(tables[0])
    for i in range(1, len(tables)):
        s = size(tables[i])
        if s > best:
            best, best_i = s, i
    return tables[best_i]
