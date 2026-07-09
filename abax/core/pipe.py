"""Stream text (from a pipe) into cell coordinates.

The ``abax pipe`` command lets a shell pipeline dump tabular text straight
into a sheet: ``cat data.tsv | abax pipe Sheet1!B2 book.abax``. This module
does the pure, side-effect-light work — parse the target anchor, shape the
stream into a 2-D grid, and lay each cell down via :meth:`Sheet.set_cell`.

It reuses :mod:`abax.core.reference` for A1 math (``parse_a1`` / ``parse_range``)
rather than reinventing the column-letter arithmetic, and speaks only in
zero-based ``(row, col)`` coordinates like the rest of the core engine.
"""

from __future__ import annotations

from .errors import FormulaError
from .reference import parse_range


class PipeError(ValueError):
    """A pipe target could not be parsed (bad sheet ref or A1 coordinate)."""


def parse_target(target: str) -> "tuple[str | None, int, int]":
    """Split ``"Sheet1!A1"`` / ``"A1"`` into ``(sheet_name_or_None, row, col)``.

    ``row``/``col`` are the zero-based coordinates of the anchor (top-left) cell.
    A range like ``"Sheet1!A1:C9"`` anchors at its top-left ``A1`` — the stream's
    own shape, not the range, decides how far the write extends, so only the
    anchor matters here. The sheet name (or ``None`` for a bare ref) is returned
    unresolved so the CLI can select the sheet; this function never touches a
    workbook.

    Raises :class:`PipeError` on an empty or malformed target.
    """
    if target is None:
        raise PipeError("empty pipe target")
    raw = target.strip()
    if not raw:
        raise PipeError("empty pipe target")
    # Split on the LAST '!' so a sheet name may itself contain one; the cell part
    # is what follows. An empty cell part (e.g. "Sheet1!") is malformed.
    sheet: "str | None" = None
    cell = raw
    if "!" in raw:
        sheet, cell = raw.rsplit("!", 1)
        sheet = sheet.strip()
        cell = cell.strip()
        if not sheet:
            raise PipeError(f"missing sheet name in target: {target!r}")
        # A sheet ref may be quoted ('My Sheet'!A1) — strip a surrounding pair.
        if len(sheet) >= 2 and sheet[0] == "'" and sheet[-1] == "'":
            sheet = sheet[1:-1]
        if not sheet:
            raise PipeError(f"missing sheet name in target: {target!r}")
    if not cell:
        raise PipeError(f"missing cell reference in target: {target!r}")
    # parse_range accepts both a bare cell ("A1") and a range ("A1:C9"), returning
    # a normalized (r1, c1, r2, c2); the top-left (r1, c1) is our anchor. It raises
    # FormulaError on anything that is not valid A1 — translate that to PipeError.
    try:
        r1, c1, _r2, _c2 = parse_range(cell)
    except FormulaError as exc:
        raise PipeError(f"bad cell reference in target: {target!r}") from exc
    return sheet, r1, c1


def _strip_csv_quotes(field: str) -> str:
    """Strip a single surrounding pair of double quotes from a CSV-style field.

    Only an exact wrapping pair is removed (``"abc"`` -> ``abc``); a lone or
    interior quote is left as-is, since the point is to undo Excel/CSV quoting of
    a whole field, not to run a full RFC-4180 parse.
    """
    if len(field) >= 2 and field[0] == '"' and field[-1] == '"':
        return field[1:-1]
    return field


def split_stream(text: str, *, delimiter: "str | None" = None) -> "list[list[str]]":
    """Turn piped text into a 2-D grid of cell strings.

    Rows split on any newline flavour (``\\r\\n``, ``\\r``, ``\\n``); a single
    trailing empty line (the newline most tools end a file with) is dropped so we
    don't write a phantom blank row. Empty input yields ``[]``.

    Within a row, the column delimiter is chosen as follows, and this auto-detect
    is the crux of the helper: if the caller passes ``delimiter`` we honour it
    verbatim; otherwise we look at the whole payload and pick TAB if *any* tab is
    present, else COMMA if *any* comma is present, else treat each line as a
    single cell. Rationale: pasted spreadsheet selections and ``.tsv`` are
    tab-delimited, ``.csv`` is comma-delimited, and free-form log/text lines have
    neither — sniffing once over the full text (not per line) keeps a ragged file
    from flipping delimiters mid-stream. Tab wins over comma because a genuine TSV
    cell may legitimately contain commas, but a CSV cell containing a raw tab is
    vanishingly rare.

    CSV-style fields keep their surrounding double-quote pair stripped. Rows may
    differ in length (a ragged grid is fine — the caller writes what it gets).
    """
    if not text:
        return []
    # Normalise line endings, then split. rstrip only ONE trailing newline's worth
    # by splitting and dropping a final empty element.
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalised.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # drop the single trailing empty line
    if not lines:
        return []

    if delimiter is None:
        # Sniff once over the entire payload so the choice is stable per stream.
        if "\t" in normalised:
            delimiter = "\t"
        elif "," in normalised:
            delimiter = ","
        else:
            delimiter = None  # single-column fallback

    grid: "list[list[str]]" = []
    for line in lines:
        if delimiter is None:
            grid.append([line])
        else:
            grid.append([_strip_csv_quotes(f) for f in line.split(delimiter)])
    return grid


def apply_stream(sheet, target: str, text: str, *,
                 delimiter: "str | None" = None) -> "tuple[int, int]":
    """Parse ``target``, split ``text``, and lay each cell into ``sheet``.

    Writes ``value`` to ``(anchor_row + i, anchor_col + j)`` for every cell in the
    split grid, via :meth:`Sheet.set_cell`. The target's sheet-name part is
    ignored for the write — the caller has already selected ``sheet``; it survives
    only through :func:`parse_target` so the CLI can pick that sheet. Empty text
    writes nothing.

    Returns ``(rows_written, cells_written)``.
    """
    _sheet_name, anchor_row, anchor_col = parse_target(target)
    grid = split_stream(text, delimiter=delimiter)
    cells_written = 0
    for i, row in enumerate(grid):
        for j, value in enumerate(row):
            sheet.set_cell(anchor_row + i, anchor_col + j, value)
            cells_written += 1
    return len(grid), cells_written
