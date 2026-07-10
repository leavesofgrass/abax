"""Public Python automation API — script abax workbooks headlessly.

This is the small, documented, ergonomic surface for driving abax from a plain
Python program: open or create a workbook, read and write cells (by A1 or by
zero-based coordinates), let formulas recompute, and save back out. It is a thin
convenience *wrapper* over the engine — :class:`abax.engine.document.Document`
and the core :class:`abax.core.workbook.Workbook` / :class:`abax.core.sheet.Sheet`
— and adds no new evaluation logic of its own.

    >>> import abax
    >>> book = abax.new()
    >>> sheet = book.active
    >>> sheet["A1"] = 10
    >>> sheet["A2"] = 20
    >>> sheet["A3"] = "=SUM(A1:A2)"
    >>> sheet["A3"]
    30
    >>> book.save("totals.abax")

**Recalculation timing.** This API relies on the engine's default *automatic*
calculation mode. Every edit invalidates the cached values of the cells that
depend on it (via the workbook's incremental dependency graph), so the very next
*read* recomputes them lazily and on demand. Reads therefore always reflect the
current formulas — there is no explicit step to remember, and no stale-value
window. :meth:`Book.recalc` is still provided for the rare cases you want to
force a full recompute of every cell (the equivalent of the GUI's F9): after a
bulk edit, to refresh volatile functions, or if you have switched the underlying
workbook to manual calculation.

**Dependencies.** Only the standard library and the always-present engine are
needed to import and use this module; nothing here requires an optional extra.
Opening or saving a *foreign* format (``.xlsx``, ``.parquet``, ``.ods`` …) uses
the engine's adapters, which may need their own optional dependency — exactly as
they do for the GUI/TUI — but the native ``.abax`` / ``.json`` format never does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from .core.errors import FormulaError
from .core.reference import parse_a1, parse_range
from .core.sheet import Sheet as _CoreSheet
from .engine.document import Document

__all__ = ["Book", "Sheet", "open", "new"]


# --- module-level constructors ------------------------------------------------


def open(path: str | Path) -> "Book":  # noqa: A001 - the public entry point abax.open(...)
    """Open a workbook file and return a :class:`Book`.

    ``path`` may be any format the engine understands from its extension —
    ``.abax`` / ``.json`` (native), ``.csv`` / ``.tsv``, ``.xlsx``, ``.parquet``,
    ``.ods``, and more (see :meth:`abax.engine.document.Document.open`). A
    foreign format may require its optional dependency; the native format never
    does.

    Raises :class:`ValueError` for an unsupported extension (propagated from the
    engine) and the usual :class:`OSError` if the file cannot be read.

        >>> book = abax.open("data.csv")
        >>> book.active["C1"]
        3
    """
    return Book(Document.open(path))


def new() -> "Book":
    """Create a fresh, empty workbook (one blank sheet named ``"Sheet1"``).

        >>> book = abax.new()
        >>> book.sheets
        ['Sheet1']
    """
    return Book(Document())


# --- coercion helpers ---------------------------------------------------------


def _coerce(value: Any) -> str:
    """Turn a Python value into the raw cell text the engine stores.

    Strings pass through verbatim (so ``"=SUM(A1:A2)"`` stays a formula and
    ``"3.14"`` stays that literal). ``None`` clears the cell. Everything else is
    rendered with :func:`str`, which round-trips numbers and booleans through the
    engine's own literal parsing (``5`` → ``"5"`` → ``5``; ``True`` → ``"True"``
    → ``True``) — the same result as typing the value into a cell.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if value is True:
        return "TRUE"
    if value is False:
        return "FALSE"
    return str(value)


def _cell_coords(ref: str) -> tuple[int, int]:
    """Parse a single A1 reference to ``(row, col)``; clean error on garbage."""
    if not isinstance(ref, str):
        raise TypeError(f"cell reference must be a string, got {type(ref).__name__}")
    try:
        return parse_a1(ref)
    except FormulaError as exc:
        raise ValueError(f"invalid cell reference: {ref!r}") from exc


def _range_coords(ref: str) -> tuple[int, int, int, int]:
    """Parse an A1 range to ``(r1, c1, r2, c2)``; clean error on garbage."""
    try:
        return parse_range(ref)
    except FormulaError as exc:
        raise ValueError(f"invalid range reference: {ref!r}") from exc


# --- Sheet --------------------------------------------------------------------


class Sheet:
    """An ergonomic view over one core :class:`abax.core.sheet.Sheet`.

    Obtain one from a :class:`Book` — ``book["Sheet1"]``, ``book.active``, or
    ``book.add_sheet(...)`` — never construct it directly. Cells are addressed
    two ways:

    * **By A1 string**, subscript-style. ``sheet["B2"]`` reads a single computed
      value; ``sheet["A1:B3"]`` reads a 2-D list (rows of columns) of computed
      values; ``sheet["B2"] = "=A1*2"`` writes a cell.
    * **By zero-based coordinates.** ``sheet.value(row, col)`` reads and
      ``sheet.set(row, col, text)`` writes — handy inside loops.

    Reads return the *computed* value: a Python ``int`` / ``float`` / ``str`` /
    ``bool``, ``None`` for a blank cell, or a :class:`abax.core.errors.CellError`
    (e.g. ``#DIV/0!``) for a formula that errored. :meth:`formula` returns the
    raw source text instead.
    """

    __slots__ = ("_sheet",)

    def __init__(self, core_sheet: _CoreSheet) -> None:
        self._sheet = core_sheet

    # -- identity ----------------------------------------------------------

    @property
    def name(self) -> str:
        """The sheet's name."""
        return self._sheet.name

    @property
    def core(self) -> _CoreSheet:
        """The wrapped core :class:`abax.core.sheet.Sheet` (an escape hatch for
        advanced use — styling, structure edits, and the rest of the engine)."""
        return self._sheet

    # -- subscript access --------------------------------------------------

    def __getitem__(self, ref: str) -> Any:
        """``sheet["A1"]`` → a scalar value; ``sheet["A1:B2"]`` → a 2-D list."""
        if isinstance(ref, str) and ":" in ref:
            return self._read_range(ref)
        row, col = _cell_coords(ref)
        return self._sheet.get_value(row, col)

    def __setitem__(self, ref: str, value: Any) -> None:
        """``sheet["A1"] = "=SUM(B1:B3)"`` — set a single cell.

        A range key is rejected (:class:`ValueError`): assign cell-by-cell (or
        via :meth:`set`) instead. ``value`` is coerced by :func:`_coerce`.
        """
        if isinstance(ref, str) and ":" in ref:
            raise ValueError(
                f"cannot assign to a range {ref!r}; assign to a single cell, "
                "e.g. sheet['A1'] = ..., or use sheet.set(row, col, value)")
        row, col = _cell_coords(ref)
        self._sheet.set_cell(row, col, _coerce(value))

    def _read_range(self, ref: str) -> list[list[Any]]:
        r1, c1, r2, c2 = _range_coords(ref)
        get = self._sheet.get_value
        return [[get(r, c) for c in range(c1, c2 + 1)] for r in range(r1, r2 + 1)]

    # -- coordinate access -------------------------------------------------

    def value(self, row: int, col: int) -> Any:
        """The computed value at zero-based ``(row, col)`` (``None`` if blank)."""
        _check_coords(row, col)
        return self._sheet.get_value(row, col)

    def set(self, row: int, col: int, text: Any) -> None:
        """Set the cell at zero-based ``(row, col)``.

        ``text`` is normally a string (``"=A1*2"`` or a literal like ``"42"``)
        but any value is accepted and coerced by :func:`_coerce` — so
        ``sheet.set(0, 0, 42)`` works too. Passing ``None`` clears the cell.
        """
        _check_coords(row, col)
        self._sheet.set_cell(row, col, _coerce(text))

    def formula(self, ref: str) -> str:
        """The raw source text of a cell — the formula (with its leading ``=``)
        or literal you entered, ``""`` for a blank cell. Contrast ``sheet[ref]``,
        which returns the *computed* value.

            >>> sheet["A3"] = "=SUM(A1:A2)"
            >>> sheet.formula("A3")
            '=SUM(A1:A2)'
        """
        row, col = _cell_coords(ref)
        return self._sheet.get_raw(row, col)

    def __repr__(self) -> str:
        rows, cols = self._sheet.used_bounds()
        return f"<abax.Sheet {self.name!r} {rows}x{cols}>"


def _check_coords(row: int, col: int) -> None:
    if not isinstance(row, int) or not isinstance(col, int):
        raise TypeError("row and col must be integers (zero-based)")
    if row < 0 or col < 0:
        raise ValueError(f"row and col must be non-negative, got ({row}, {col})")


# --- Book ---------------------------------------------------------------------


class Book:
    """A workbook — an ordered collection of named sheets, backed by a
    :class:`abax.engine.document.Document`.

    Create one with :func:`abax.open` or :func:`abax.new`. Index it by sheet name
    to get a :class:`Sheet` (``book["Sheet1"]``, :class:`KeyError` if absent), or
    use :attr:`active` for the current sheet. It is also a context manager, so a
    ``with`` block scopes its use::

        with abax.open("data.abax") as book:
            book.active["A1"] = "=NOW()"
            book.save()

    The context manager does **not** auto-save on exit — persistence is always an
    explicit :meth:`save`, so a read-only or aborted block leaves the file
    untouched.
    """

    __slots__ = ("_doc", "_wrappers")

    def __init__(self, document: Document) -> None:
        self._doc = document
        # Stable wrapper identity: the same core sheet always yields the same
        # Sheet object (so ``book["S"] is book["S"]``). Keyed by object id; the
        # core sheets live for the workbook's lifetime, which the Book owns.
        self._wrappers: dict[int, Sheet] = {}

    # -- underlying handles ------------------------------------------------

    @property
    def document(self) -> Document:
        """The wrapped :class:`abax.engine.document.Document` (escape hatch)."""
        return self._doc

    @property
    def workbook(self):
        """The underlying core :class:`abax.core.workbook.Workbook` (escape hatch)."""
        return self._doc.workbook

    @property
    def path(self) -> "Path | None":
        """The file path this book was opened from / last saved to, or ``None``."""
        return self._doc.path

    # -- sheets ------------------------------------------------------------

    def _wrap(self, core_sheet: _CoreSheet) -> Sheet:
        key = id(core_sheet)
        wrapper = self._wrappers.get(key)
        if wrapper is None:
            wrapper = Sheet(core_sheet)
            self._wrappers[key] = wrapper
        return wrapper

    @property
    def sheets(self) -> list[str]:
        """The sheet names, in order."""
        return [s.name for s in self._doc.workbook.sheets]

    @property
    def active(self) -> Sheet:
        """The active sheet (the first one in a freshly created book)."""
        return self._wrap(self._doc.workbook.sheet)

    def __getitem__(self, name: str) -> Sheet:
        """``book["Sheet1"]`` → the named :class:`Sheet`; :class:`KeyError` if
        there is no such sheet (the message lists the names that do exist)."""
        core = self._doc.workbook.get_sheet(name)
        if core is None:
            raise KeyError(
                f"no sheet named {name!r}; available sheets: {self.sheets}")
        return self._wrap(core)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self._doc.workbook.get_sheet(name) is not None

    def __iter__(self) -> Iterator[Sheet]:
        """Iterate the sheets as :class:`Sheet` wrappers, in order."""
        return (self._wrap(s) for s in self._doc.workbook.sheets)

    def __len__(self) -> int:
        return len(self._doc.workbook.sheets)

    def add_sheet(self, name: str | None = None) -> Sheet:
        """Add a new sheet and return it.

        With no name, the engine picks the next ``"SheetN"``. A duplicate name
        raises :class:`ValueError` (propagated from the workbook).
        """
        return self._wrap(self._doc.workbook.add_sheet(name))

    # -- recalc / save -----------------------------------------------------

    def recalc(self) -> None:
        """Force a full recompute of every cell (the engine's F9).

        Not usually needed — reads already recompute lazily under the default
        automatic calculation (see the module docstring). Use it after a bulk
        edit, to refresh volatile functions, or when the underlying workbook is
        in manual-calc mode.
        """
        self._doc.workbook.recalculate()

    def save(self, path: "str | Path | None" = None) -> None:
        """Write the workbook to ``path`` (or the path it was opened from).

        The format is chosen from the extension. Saving with no ``path`` and no
        prior path raises :class:`ValueError` (propagated from the engine).

            >>> book.save("out.abax")   # native JSON
            >>> book.save("out.csv")    # the active sheet as CSV
        """
        self._doc.save(path)

    # -- context manager ---------------------------------------------------

    def __enter__(self) -> "Book":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        # Nothing to release — a Document holds no open OS handles. We do NOT
        # auto-save: persistence stays explicit via save(). Never suppress.
        return False

    def __repr__(self) -> str:
        where = f" {self._doc.path}" if self._doc.path else ""
        return f"<abax.Book{where} sheets={self.sheets}>"
