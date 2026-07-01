"""Excel 2003 XML Spreadsheet (SpreadsheetML) import/export — stdlib only.

A single ``.xml`` file holding ``<Worksheet>/<Table>/<Row>/<Cell>/<Data>``.
Formulas are stored in R1C1 in the ``ss:Formula`` attribute (converted to/from
A1 via :mod:`abax.core.r1c1`). Sparse rows/cells use ``ss:Index``. This is the
"XML spreadsheet" gnumeric and Excel both read/write. Pure stdlib → core.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from ..errors import CellError
from ..r1c1 import formula_a1_to_r1c1, formula_r1c1_to_a1
from ..sheet import Sheet
from ..workbook import Workbook

_NS = "urn:schemas-microsoft-com:office:spreadsheet"
_SS = "{" + _NS + "}"


# --- export ----------------------------------------------------------------


def to_spreadsheetml(workbook: Workbook) -> str:
    parts = [
        '<?xml version="1.0"?>',
        '<?mso-application progid="Excel.Sheet"?>',
        f'<Workbook xmlns="{_NS}" xmlns:ss="{_NS}">',
    ]
    for sheet in workbook.sheets:
        parts.append(f" <Worksheet ss:Name={quoteattr(sheet.name)}>")
        parts.append("  <Table>")
        parts.extend(_rows_xml(sheet))
        parts.append("  </Table>")
        parts.append(" </Worksheet>")
    parts.append("</Workbook>")
    return "\n".join(parts) + "\n"


def _rows_xml(sheet: Sheet) -> list[str]:
    n_rows, n_cols = sheet.used_bounds()
    out: list[str] = []
    expected_row = 0
    for r in range(n_rows):
        cells = [(c, cell) for c in range(n_cols) if (cell := sheet.get_cell(r, c))]
        if not cells:
            continue
        attr = "" if r == expected_row else f' ss:Index="{r + 1}"'
        out.append(f"   <Row{attr}>")
        expected_col = 0
        for c, cell in cells:
            out.append(_cell_xml(sheet, r, c, cell, c == expected_col))
            expected_col = c + 1
        out.append("   </Row>")
        expected_row = r + 1
    return out


def _cell_xml(sheet: Sheet, r: int, c: int, cell, dense: bool) -> str:
    idx = "" if dense else f' ss:Index="{c + 1}"'
    formula = ""
    if cell.is_formula:
        formula = f" ss:Formula={quoteattr(formula_a1_to_r1c1(cell.raw, r, c))}"
    value = sheet.get_value(r, c)
    dtype, dtext = _data(value)
    if dtext is None:
        return f"    <Cell{idx}{formula}/>"
    return f'    <Cell{idx}{formula}><Data ss:Type="{dtype}">{escape(dtext)}</Data></Cell>'


def _data(value) -> tuple[str, str | None]:
    if value is None or value == "":
        return "String", None
    if isinstance(value, bool):
        return "Boolean", "1" if value else "0"
    if isinstance(value, CellError):
        return "String", str(value)
    if isinstance(value, (int, float)):
        return "Number", str(int(value)) if float(value).is_integer() else repr(value)
    return "String", str(value)


# --- import ----------------------------------------------------------------


def from_spreadsheetml(text: str) -> Workbook:
    root = ET.fromstring(text)
    wb = Workbook.__new__(Workbook)
    wb.sheets = []
    wb.active = 0
    for ws in root.findall(f"{_SS}Worksheet"):
        name = ws.get(f"{_SS}Name", f"Sheet{len(wb.sheets) + 1}")
        sheet = Sheet(name)
        table = ws.find(f"{_SS}Table")
        if table is not None:
            _read_table(sheet, table)
        wb.sheets.append(sheet)
    wb._add_default_if_empty()
    return wb


def _read_table(sheet: Sheet, table: ET.Element) -> None:
    row_i = 0
    for row in table.findall(f"{_SS}Row"):
        idx = row.get(f"{_SS}Index")
        if idx is not None:
            row_i = int(idx) - 1
        col_i = 0
        for cell in row.findall(f"{_SS}Cell"):
            cidx = cell.get(f"{_SS}Index")
            if cidx is not None:
                col_i = int(cidx) - 1
            raw = _cell_raw(cell, row_i, col_i)
            if raw != "":
                sheet.set_cell(row_i, col_i, raw)
            col_i += 1
        row_i += 1


def _cell_raw(cell: ET.Element, row: int, col: int) -> str:
    formula = cell.get(f"{_SS}Formula")
    if formula:
        return formula_r1c1_to_a1(formula, row, col)
    data = cell.find(f"{_SS}Data")
    if data is None or data.text is None:
        return ""
    dtype = data.get(f"{_SS}Type", "String")
    text = data.text
    if dtype == "Boolean":
        return "TRUE" if text.strip() in ("1", "True", "true") else "FALSE"
    return text


def save_spreadsheetml(workbook: Workbook, path: str | Path) -> None:
    Path(path).write_text(to_spreadsheetml(workbook), encoding="utf-8")


def load_spreadsheetml(path: str | Path) -> Workbook:
    return from_spreadsheetml(Path(path).read_text(encoding="utf-8"))
