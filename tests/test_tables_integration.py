"""End-to-end structured references: tokenizer → parser → sheet resolution.

Complements tests/test_tables.py (the pure parser/resolver unit tests) by
driving real workbook formulas through the whole engine, plus persistence,
structural shifts, and the TUI :table command.
"""

from __future__ import annotations

from abax.core.errors import CellError, is_error
from abax.core.tables import detect_table
from abax.core.tokenizer import tokenize
from abax.core.workbook import Workbook


def _sales_workbook() -> Workbook:
    wb = Workbook()
    s = wb.sheet
    rows = [["region", "sales"], ["East", "5"], ["West", "13"], ["North", "7"]]
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            s.set_cell(r, c, v)
    wb.tables.add(detect_table(s.name, 0, 0, 3, 1, "Sales", headers=["region", "sales"]))
    return wb


# --- tokenizer boundaries ---------------------------------------------------


def test_tokenizer_emits_structref():
    toks = tokenize("SUM(Sales[sales])")
    kinds = [t.kind for t in toks]
    assert "STRUCTREF" in kinds
    assert toks[kinds.index("STRUCTREF")].value == "Sales[sales]"


def test_tokenizer_nested_form():
    toks = tokenize("Sales[[#Data],[sales]]+1")
    assert toks[0].kind == "STRUCTREF"
    assert toks[0].value == "Sales[[#Data],[sales]]"


def test_tokenizer_leaves_external_refs_alone():
    toks = tokenize("[Book.abax]Sheet1!A1+1")
    assert toks[0].kind == "REF"
    assert toks[0].value == "[Book.abax]Sheet1!A1"


# --- formula evaluation ------------------------------------------------------


def test_sum_over_table_column():
    wb = _sales_workbook()
    wb.sheet.set_cell(5, 0, "=SUM(Sales[sales])")
    wb.recalculate()
    assert wb.sheet.get_value(5, 0) == 25.0


def test_this_row_qualified_form():
    wb = _sales_workbook()
    wb.sheet.set_cell(1, 3, "=Sales[@sales]*2")  # row 1 -> East, 5
    wb.recalculate()
    assert wb.sheet.get_value(1, 3) == 10.0


def test_headers_region():
    wb = _sales_workbook()
    wb.sheet.set_cell(5, 1, "=Sales[#Headers]")  # the header row as a range
    wb.recalculate()
    v = wb.sheet.get_value(5, 1)
    from abax.core.values import RangeValue

    assert isinstance(v, RangeValue)
    assert v.row(0) == ["region", "sales"]


def test_unknown_table_is_name_error():
    wb = _sales_workbook()
    wb.sheet.set_cell(5, 0, "=SUM(Nope[x])")
    wb.recalculate()
    v = wb.sheet.get_value(5, 0)
    assert is_error(v) and v.code == CellError.NAME


def test_bare_at_outside_table_is_name_error():
    wb = _sales_workbook()
    wb.sheet.set_cell(1, 3, "=[@sales]*2")  # col 3 is outside the table
    wb.recalculate()
    v = wb.sheet.get_value(1, 3)
    assert is_error(v) and v.code == CellError.NAME


def test_table_registry_edit_invalidates_resolution():
    wb = _sales_workbook()
    wb.sheet.set_cell(5, 0, "=SUM(Sales[sales])")
    wb.recalculate()
    assert wb.sheet.get_value(5, 0) == 25.0
    # Rename the table away -> the formula must degrade to #NAME? on recalc.
    wb.tables.remove("Sales")
    wb.recalculate()
    v = wb.sheet.get_value(5, 0)
    assert is_error(v) and v.code == CellError.NAME


# --- persistence -------------------------------------------------------------


def test_envelope_round_trip_preserves_tables():
    wb = _sales_workbook()
    wb.sheet.set_cell(5, 0, "=SUM(Sales[sales])")
    wb2 = Workbook.from_envelope(wb.to_envelope())
    assert wb2.tables.get("sales") is not None  # case-insensitive
    wb2.recalculate()
    assert wb2.sheet.get_value(5, 0) == 25.0


def test_empty_registry_omitted_from_envelope():
    wb = Workbook()
    assert "tables" not in wb.to_envelope()["data"]


# --- structural shifts ---------------------------------------------------------


def test_insert_row_inside_data_grows_table():
    wb = _sales_workbook()
    s = wb.sheet
    s.insert_rows(2, 1)
    s.set_cell(2, 0, "South")
    s.set_cell(2, 1, "100")
    t = wb.tables.get("Sales")
    assert (t.first_data_row, t.last_data_row) == (1, 4)
    s.set_cell(6, 0, "=SUM(Sales[sales])")
    wb.recalculate()
    assert s.get_value(6, 0) == 125.0


def test_delete_tail_data_row_shrinks_table():
    wb = _sales_workbook()
    wb.sheet.delete_rows(3, 1)  # drop North
    t = wb.tables.get("Sales")
    assert (t.first_data_row, t.last_data_row) == (1, 2)


def test_delete_header_row_dissolves_table():
    wb = _sales_workbook()
    wb.sheet.delete_rows(0, 1)
    assert wb.tables.get("Sales") is None


def test_delete_all_columns_dissolves_table():
    wb = _sales_workbook()
    wb.sheet.delete_cols(0, 2)
    assert wb.tables.get("Sales") is None


# --- TUI :table ----------------------------------------------------------------


def test_tui_table_command_registers_current_region():
    from abax.engine.document import Document
    from abax.tui.editor import TuiEditor

    doc = Document()
    s = doc.workbook.sheet
    rows = [["item", "qty"], ["a", "1"], ["b", "2"]]
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            s.set_cell(r, c, v)
    ed = TuiEditor(doc)
    ed.row, ed.col = 1, 0  # inside the region
    ed.command_buf = ":table Stock"
    ed.run_command()
    t = doc.workbook.tables.get("Stock")
    assert t is not None and t.columns == ["item", "qty"]
    assert "Stock" in ed.message
    # listing
    ed.command_buf = ":table"
    ed.run_command()
    assert "Stock" in ed.message
