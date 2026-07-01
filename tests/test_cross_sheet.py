"""Cross-sheet references: Sheet2!A1, ranges, recalc, cycles, persistence."""

from __future__ import annotations

from abax.core import ast_nodes as A
from abax.core.errors import CellError
from abax.core.parser import parse
from abax.core.workbook import Workbook

# --- parsing ---------------------------------------------------------------


def test_parse_qualified_ref():
    node = parse("Sheet2!B3")
    assert isinstance(node, A.Ref)
    assert node.sheet == "Sheet2"
    assert node.text == "B3"


def test_parse_quoted_sheet_name():
    node = parse("'My Sheet'!A1")
    assert node.sheet == "My Sheet"
    assert node.text == "A1"


def test_parse_qualified_range():
    node = parse("Data!A1:C3")
    assert isinstance(node, A.Range)
    assert node.sheet == "Data"
    assert node.text == "A1:C3"


# --- evaluation ------------------------------------------------------------


def _two_sheet_wb():
    wb = Workbook()
    wb.sheet.name = "Sheet1"
    data = wb.add_sheet("Data")
    data.set("A1", "10")
    data.set("A2", "20")
    data.set("A3", "30")
    return wb


def test_cross_sheet_single_ref():
    wb = _two_sheet_wb()
    wb.sheet.set("A1", "=Data!A2")
    assert wb.sheet.get("A1") == 20


def test_cross_sheet_range_aggregate():
    wb = _two_sheet_wb()
    wb.sheet.set("A1", "=SUM(Data!A1:A3)")
    assert wb.sheet.get("A1") == 60


def test_cross_sheet_arithmetic():
    wb = _two_sheet_wb()
    wb.sheet.set("A1", "=Data!A1 + Data!A3")
    assert wb.sheet.get("A1") == 40


def test_quoted_sheet_with_space():
    wb = Workbook()
    s2 = wb.add_sheet("My Data")
    s2.set("A1", "7")
    wb.sheet.set("A1", "='My Data'!A1*2")
    assert wb.sheet.get("A1") == 14


def test_edit_source_updates_cross_sheet_dependent():
    wb = _two_sheet_wb()
    wb.sheet.set("A1", "=Data!A1")
    assert wb.sheet.get("A1") == 10
    wb.get_sheet("Data").set("A1", "99")  # editing other sheet must invalidate
    assert wb.sheet.get("A1") == 99


def test_missing_sheet_is_ref_error():
    wb = Workbook()
    wb.sheet.set("A1", "=Nope!A1")
    assert wb.sheet.get("A1") == CellError(CellError.REF)


def test_standalone_sheet_cross_ref_is_ref_error():
    # A Sheet with no workbook can't resolve cross-sheet refs.
    from abax.core import Sheet

    s = Sheet()
    s.set("A1", "=Other!A1")
    assert s.get("A1") == CellError(CellError.REF)


def test_cross_sheet_circular_is_circ():
    wb = Workbook()
    a = wb.sheet
    a.name = "A"
    b = wb.add_sheet("B")
    a.set("A1", "=B!A1")
    b.set("A1", "=A!A1")
    assert a.get("A1") == CellError(CellError.CIRC)


def test_chained_cross_sheet():
    wb = Workbook()
    wb.sheet.name = "S1"
    s2 = wb.add_sheet("S2")
    s3 = wb.add_sheet("S3")
    s3.set("A1", "5")
    s2.set("A1", "=S3!A1*2")
    wb.sheet.set("A1", "=S2!A1+1")
    assert wb.sheet.get("A1") == 11


# --- persistence + transforms ---------------------------------------------


def test_cross_sheet_survives_json_roundtrip(tmp_path):
    wb = _two_sheet_wb()
    wb.sheet.set("A1", "=SUM(Data!A1:A3)")
    path = tmp_path / "wb.abax"
    wb.save_json(path)
    wb2 = Workbook.load_json(path)
    assert wb2.sheet.get("A1") == 60  # resolves after reload (sheets linked)


def test_fill_preserves_sheet_qualifier():
    from abax.core.fill import fill_down

    wb = _two_sheet_wb()
    wb.sheet.set("A1", "=Data!A1")
    fill_down(wb.sheet, "A1:A3")
    assert wb.sheet.get_raw(1, 0) == "=Data!A2"  # row shifts, sheet stays
    assert wb.sheet.get_raw(2, 0) == "=Data!A3"
    assert wb.sheet.get("A3") == 30


def test_xml_roundtrip_cross_sheet():
    from abax.core.io.xml_io import from_spreadsheetml, to_spreadsheetml

    wb = _two_sheet_wb()
    wb.sheet.set("A1", "=Data!A2")
    xml = to_spreadsheetml(wb)
    wb2 = from_spreadsheetml(xml)
    assert wb2.get_sheet("Sheet1").get("A1") == 20
