"""Export a sheet or workbook as a standalone HTML report.

Pure-stdlib (``html`` only): produces a complete ``<!DOCTYPE html>`` document
with an embedded stylesheet and one bordered ``<table>`` per sheet. Each table
shows a header row of column letters (A, B, ...), a leading row-number header
per row, and the *displayed* value of every cell (``sheet.display``), escaped.

Large sheets are bounded to ``max_rows`` x ``max_cols``; when a sheet exceeds
either bound a small note records how many rows/columns were omitted.
"""

from __future__ import annotations

import html

from ..reference import index_to_col

_STYLE = """\
body { font-family: system-ui, sans-serif; margin: 1.5em; color: #222; }
h2 { margin-top: 1.2em; }
table { border-collapse: collapse; margin-bottom: 0.5em; }
th, td { border: 1px solid #bbb; padding: 2px 6px; text-align: left; }
thead th, tbody th { background: #eee; font-weight: bold; }
tbody th { text-align: right; }
p.note { color: #666; font-style: italic; margin-top: 0; }\
"""


def _table_for_sheet(sheet, *, max_rows: int = 1000, max_cols: int = 100) -> str:
    """Render one sheet as ``<h2>`` + ``<table>`` (+ optional truncation note)."""
    nrows, ncols = sheet.used_bounds()
    rows = min(nrows, max_rows)
    cols = min(ncols, max_cols)

    parts = [f"<h2>{html.escape(sheet.name)}</h2>"]

    if rows == 0 or cols == 0:
        parts.append("<p class='note'>(empty sheet)</p>")
        return "\n".join(parts)

    header = "".join(f"<th>{index_to_col(c)}</th>" for c in range(cols))
    body_rows = []
    for r in range(rows):
        cells = "".join(
            f"<td>{html.escape(sheet.display(r, c))}</td>" for c in range(cols)
        )
        body_rows.append(f"<tr><th>{r + 1}</th>{cells}</tr>")

    parts.append(
        "<table>\n"
        f"<thead><tr><th></th>{header}</tr></thead>\n"
        "<tbody>\n" + "\n".join(body_rows) + "\n</tbody>\n"
        "</table>"
    )

    notes = []
    if nrows > rows:
        notes.append(f"{nrows - rows} more rows")
    if ncols > cols:
        notes.append(f"{ncols - cols} more columns")
    if notes:
        parts.append(f"<p class='note'>… {', '.join(notes)}</p>")

    return "\n".join(parts)


def _document(title: str, bodies: list[str]) -> str:
    """Wrap rendered sheet bodies in a complete HTML document."""
    esc_title = html.escape(title)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{esc_title}</title>\n"
        f"<style>\n{_STYLE}\n</style>\n"
        "</head>\n"
        "<body>\n" + "\n".join(bodies) + "\n</body>\n"
        "</html>\n"
    )


def sheet_to_html(
    sheet, *, title: str | None = None, max_rows: int = 1000, max_cols: int = 100
) -> str:
    """Return a standalone HTML document for a single ``sheet``.

    ``title`` defaults to the sheet name. The body is bounded to
    ``max_rows`` x ``max_cols``; excess is noted rather than rendered.
    """
    doc_title = title if title is not None else sheet.name
    body = _table_for_sheet(sheet, max_rows=max_rows, max_cols=max_cols)
    return _document(doc_title, [body])


def workbook_to_html(workbook, *, title: str | None = None, **kw) -> str:
    """Return one HTML document containing every sheet in ``workbook``.

    Each sheet is rendered as its own ``<h2>`` + ``<table>``. Bounding keywords
    (``max_rows`` / ``max_cols``) are forwarded to each sheet's rendering.
    """
    doc_title = title if title is not None else "Workbook"
    bodies = [_table_for_sheet(sheet, **kw) for sheet in workbook.sheets]
    return _document(doc_title, bodies)
