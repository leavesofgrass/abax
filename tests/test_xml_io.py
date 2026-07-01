"""Excel 2003 XML Spreadsheet (SpreadsheetML) import/export."""

from __future__ import annotations

from abax.core import Sheet
from abax.core.io.xml_io import from_spreadsheetml, to_spreadsheetml
from abax.core.workbook import Workbook


def _wb(rows, name="Sheet1"):
    wb = Workbook.__new__(Workbook)
    s = Sheet(name)
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if v != "":
                s.set_cell(r, c, str(v))
    wb.sheets = [s]
    wb.active = 0
    return wb


def test_export_has_spreadsheetml_skeleton():
    xml = to_spreadsheetml(_wb([["a", "b"], ["1", "2"]]))
    assert 'xmlns="urn:schemas-microsoft-com:office:spreadsheet"' in xml
    assert "<Worksheet" in xml and "<Table>" in xml
    assert 'mso-application progid="Excel.Sheet"' in xml


def test_formula_stored_as_r1c1():
    wb = _wb([["10", "=A1*2"]])
    xml = to_spreadsheetml(wb)
    assert 'ss:Formula="=RC[-1]*2"' in xml


def test_roundtrip_values_and_formulas():
    wb = _wb([["Item", "Qty", "Total"], ["x", "3", "=B2*2"], ["y", "5", "=B3*2"]])
    xml = to_spreadsheetml(wb)
    wb2 = from_spreadsheetml(xml)
    s = wb2.sheet
    assert s.get("A1") == "Item"
    assert s.get("B2") == 3
    assert s.get_raw(1, 2) == "=B2*2"  # formula restored to A1
    assert s.get("C2") == 6
    assert s.get("C3") == 10


def test_sparse_cells_use_index():
    s = Sheet("S")
    s.set("A1", "1")
    s.set("D1", "4")  # gap -> ss:Index on the later cell
    wb = Workbook.__new__(Workbook)
    wb.sheets = [s]
    wb.active = 0
    xml = to_spreadsheetml(wb)
    assert 'ss:Index="4"' in xml
    wb2 = from_spreadsheetml(xml)
    assert wb2.sheet.get("A1") == 1
    assert wb2.sheet.get("D1") == 4
    assert wb2.sheet.get("B1") is None


def test_multiple_sheets_roundtrip():
    wb = Workbook()
    wb.sheet.set("A1", "first")
    wb.add_sheet("Second")
    wb.get_sheet("Second").set("A1", "second")
    xml = to_spreadsheetml(wb)
    wb2 = from_spreadsheetml(xml)
    assert [s.name for s in wb2.sheets] == ["Sheet1", "Second"]
    assert wb2.get_sheet("Second").get("A1") == "second"


def test_boolean_type():
    wb = _wb([["=1=1"]])
    xml = to_spreadsheetml(wb)
    assert 'ss:Type="Boolean"' in xml
    wb2 = from_spreadsheetml(xml)
    assert wb2.sheet.get("A1") in ("TRUE", True)
