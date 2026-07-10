"""Tests for Excel-style structured references (``abax.core.tables``)."""

from __future__ import annotations

import pytest

from abax.core.tables import (
    StructuredRef,
    Table,
    TableError,
    TableRegistry,
    detect_table,
    parse_structured_ref,
    resolve_structured_ref,
    to_a1_range,
)

# --- fixtures --------------------------------------------------------------


def _sales_table() -> Table:
    """A ``Sales`` table on ``Sheet1`` occupying B2:D6 with a totals row.

        row 1 (idx1)  B  C  D    headers: Region, Amount, Qty
        rows 2..4                 data body
        row 5 (idx4)              totals row
    Columns: B=1, C=2, D=3.
    """
    return Table(
        name="Sales",
        sheet="Sheet1",
        header_row=1,
        first_data_row=2,
        last_data_row=4,
        first_col=1,
        last_col=3,
        headers=["Region", "Amount", "Qty"],
        totals_row=5,
    )


def _registry() -> TableRegistry:
    reg = TableRegistry()
    reg.add(_sales_table())
    return reg


# --- Table model -----------------------------------------------------------


def test_table_columns_property():
    t = _sales_table()
    assert t.columns == ["Region", "Amount", "Qty"]


def test_table_width_and_last_row():
    t = _sales_table()
    assert t.width == 3
    assert t.last_row == 5  # totals row
    t.totals_row = None
    assert t.last_row == 4  # falls back to last_data_row


def test_column_index_absolute_and_case_insensitive():
    t = _sales_table()
    assert t.column_index("Region") == 1
    assert t.column_index("amount") == 2
    assert t.column_index("QTY") == 3


def test_column_index_unknown_raises():
    t = _sales_table()
    with pytest.raises(TableError):
        t.column_index("Nope")


def test_has_column():
    t = _sales_table()
    assert t.has_column("amount")
    assert not t.has_column("profit")


def test_contains():
    t = _sales_table()
    assert t.contains(1, 1)  # header cell
    assert t.contains(3, 2)  # data cell
    assert t.contains(5, 3)  # totals cell
    assert not t.contains(0, 1)  # above header
    assert not t.contains(3, 4)  # right of last col
    assert not t.contains(6, 1)  # below totals


def test_table_round_trip_dict():
    t = _sales_table()
    t2 = Table.from_dict(t.to_dict())
    assert t2.to_dict() == t.to_dict()
    assert t2.column_index("Qty") == 3


# --- TableRegistry ---------------------------------------------------------


def test_registry_case_insensitive_lookup():
    reg = _registry()
    assert reg.get("sales") is not None
    assert reg.get("SALES").name == "Sales"
    assert reg.has("sAlEs")
    assert "SALES" in reg


def test_registry_get_missing_returns_none():
    reg = _registry()
    assert reg.get("ghost") is None
    assert not reg.has("ghost")


def test_registry_len_iter_names():
    reg = _registry()
    reg.add(Table("Costs", "Sheet1", 10, 11, 15, 0, 1, ["A", "B"]))
    assert len(reg) == 2
    assert reg.names() == ["Costs", "Sales"]
    assert {t.name for t in reg} == {"Costs", "Sales"}


def test_registry_remove():
    reg = _registry()
    reg.remove("SALES")
    assert not reg.has("Sales")
    with pytest.raises(TableError):
        reg.remove("Sales")


def test_registry_rename():
    reg = _registry()
    reg.rename("Sales", "Revenue")
    assert not reg.has("Sales")
    assert reg.get("revenue").name == "Revenue"


def test_registry_rename_collision_raises():
    reg = _registry()
    reg.add(Table("Costs", "Sheet1", 10, 11, 15, 0, 1, ["A", "B"]))
    with pytest.raises(TableError):
        reg.rename("Sales", "Costs")


def test_registry_version_bumps():
    reg = TableRegistry()
    v0 = reg.version
    reg.add(_sales_table())
    assert reg.version > v0


def test_registry_table_at():
    reg = _registry()
    assert reg.table_at("Sheet1", 3, 2).name == "Sales"
    assert reg.table_at("Sheet1", 0, 0) is None
    assert reg.table_at("Sheet2", 3, 2) is None


def test_registry_round_trip_dict():
    reg = _registry()
    reg2 = TableRegistry.from_dict(reg.to_dict())
    assert reg2.get("Sales").to_dict() == reg.get("Sales").to_dict()


# --- parse_structured_ref: every form --------------------------------------


def test_parse_simple_column():
    ref = parse_structured_ref("Sales[Amount]")
    assert ref == StructuredRef(table="Sales", column="Amount")
    assert not ref.this_row
    assert not ref.is_implicit


def test_parse_this_row_column():
    ref = parse_structured_ref("Sales[@Amount]")
    assert ref.table == "Sales"
    assert ref.column == "Amount"
    assert ref.this_row


def test_parse_this_row_bracketed_column():
    # Excel writes multi-word this-row refs as [@[Col Name]].
    ref = parse_structured_ref("Sales[@[Unit Price]]")
    assert ref.table == "Sales"
    assert ref.column == "Unit Price"
    assert ref.this_row


def test_parse_region_all():
    ref = parse_structured_ref("Sales[#All]")
    assert ref.region == "all"
    assert ref.column is None


def test_parse_region_data():
    assert parse_structured_ref("Sales[#Data]").region == "data"


def test_parse_region_headers():
    assert parse_structured_ref("Sales[#Headers]").region == "headers"


def test_parse_region_totals():
    assert parse_structured_ref("Sales[#Totals]").region == "totals"


def test_parse_region_and_column():
    ref = parse_structured_ref("Sales[[#Data],[Amount]]")
    assert ref.table == "Sales"
    assert ref.region == "data"
    assert ref.column == "Amount"


def test_parse_headers_and_column():
    ref = parse_structured_ref("Sales[[#Headers],[Amount]]")
    assert ref.region == "headers"
    assert ref.column == "Amount"


def test_parse_this_row_region_form():
    # [[#This Row],[Col]] is the long form of [@Col].
    ref = parse_structured_ref("Sales[[#This Row],[Amount]]")
    assert ref.this_row
    assert ref.column == "Amount"


def test_parse_column_span():
    ref = parse_structured_ref("Sales[[Region]:[Qty]]")
    assert ref.column == "Region"
    assert ref.column_end == "Qty"
    assert ref.is_span


def test_parse_region_and_span():
    ref = parse_structured_ref("Sales[[#Data],[Region]:[Qty]]")
    assert ref.region == "data"
    assert ref.column == "Region"
    assert ref.column_end == "Qty"


def test_parse_bare_column_is_implicit():
    ref = parse_structured_ref("[Amount]")
    assert ref.table is None
    assert ref.is_implicit
    assert ref.column == "Amount"


def test_parse_bare_this_row():
    ref = parse_structured_ref("[@Amount]")
    assert ref.is_implicit
    assert ref.this_row
    assert ref.column == "Amount"


def test_parse_multiword_column_with_spaces():
    ref = parse_structured_ref("Sales[[Unit Price]]")
    assert ref.column == "Unit Price"


def test_parse_escaped_special_chars_in_column():
    # A column literally named "Cost [USD]" escapes its brackets with '.
    ref = parse_structured_ref("Sales[[Cost '[USD']]]")
    assert ref.column == "Cost [USD]"


def test_parse_case_preserved_on_table_name():
    assert parse_structured_ref("SALES[Amount]").table == "SALES"


# --- parse_structured_ref: non-refs return None ----------------------------


def test_parse_plain_range_is_none():
    assert parse_structured_ref("A1:C3") is None
    assert parse_structured_ref("B7") is None


def test_parse_external_ref_is_none():
    # An external-workbook ref [Book.abax]Sheet1!A1 must not misfire.
    assert parse_structured_ref("[Book.abax]Sheet1!A1") is None


def test_parse_bare_name_is_none():
    assert parse_structured_ref("Table1") is None


def test_parse_unbalanced_is_none():
    assert parse_structured_ref("Sales[Amount") is None
    assert parse_structured_ref("Sales[[#Data],[Amount]") is None


def test_parse_empty_selector_is_none():
    assert parse_structured_ref("Sales[]") is None


def test_parse_unknown_region_is_none():
    assert parse_structured_ref("Sales[#Bogus]") is None


def test_parse_non_string_is_none():
    assert parse_structured_ref(None) is None
    assert parse_structured_ref(42) is None


# --- resolve_structured_ref ------------------------------------------------


def test_resolve_simple_column_data_body():
    reg = _registry()
    ref = parse_structured_ref("Sales[Amount]")
    assert resolve_structured_ref(ref, reg) == ("Sheet1", 2, 2, 4, 2)


def test_resolve_this_row_uses_current_row():
    reg = _registry()
    ref = parse_structured_ref("Sales[@Amount]")
    assert resolve_structured_ref(ref, reg, current_row=3) == ("Sheet1", 3, 2, 3, 2)


def test_resolve_this_row_without_current_row_raises():
    reg = _registry()
    ref = parse_structured_ref("Sales[@Amount]")
    with pytest.raises(TableError):
        resolve_structured_ref(ref, reg)


def test_resolve_headers_region():
    reg = _registry()
    ref = parse_structured_ref("Sales[#Headers]")
    # Header row 1, all columns B..D.
    assert resolve_structured_ref(ref, reg) == ("Sheet1", 1, 1, 1, 3)


def test_resolve_totals_region():
    reg = _registry()
    ref = parse_structured_ref("Sales[#Totals]")
    assert resolve_structured_ref(ref, reg) == ("Sheet1", 5, 1, 5, 3)


def test_resolve_totals_without_totals_row_raises():
    reg = TableRegistry()
    reg.add(
        Table("NoTot", "Sheet1", 0, 1, 3, 0, 1, ["A", "B"], totals_row=None)
    )
    ref = parse_structured_ref("NoTot[#Totals]")
    with pytest.raises(TableError):
        resolve_structured_ref(ref, reg)


def test_resolve_all_region_spans_header_to_totals():
    reg = _registry()
    ref = parse_structured_ref("Sales[#All]")
    assert resolve_structured_ref(ref, reg) == ("Sheet1", 1, 1, 5, 3)


def test_resolve_data_region_no_column():
    reg = _registry()
    ref = parse_structured_ref("Sales[#Data]")
    assert resolve_structured_ref(ref, reg) == ("Sheet1", 2, 1, 4, 3)


def test_resolve_headers_and_column():
    reg = _registry()
    ref = parse_structured_ref("Sales[[#Headers],[Qty]]")
    assert resolve_structured_ref(ref, reg) == ("Sheet1", 1, 3, 1, 3)


def test_resolve_column_span():
    reg = _registry()
    ref = parse_structured_ref("Sales[[Region]:[Qty]]")
    # Data body across columns B..D.
    assert resolve_structured_ref(ref, reg) == ("Sheet1", 2, 1, 4, 3)


def test_resolve_column_span_reversed_order_normalized():
    reg = _registry()
    ref = parse_structured_ref("Sales[[Qty]:[Region]]")
    assert resolve_structured_ref(ref, reg) == ("Sheet1", 2, 1, 4, 3)


def test_resolve_all_region_with_column():
    reg = _registry()
    ref = parse_structured_ref("Sales[[#All],[Amount]]")
    assert resolve_structured_ref(ref, reg) == ("Sheet1", 1, 2, 5, 2)


def test_resolve_case_insensitive_table_and_column():
    reg = _registry()
    ref = parse_structured_ref("sales[amount]")
    assert resolve_structured_ref(ref, reg) == ("Sheet1", 2, 2, 4, 2)


def test_resolve_unknown_table_raises():
    reg = _registry()
    ref = parse_structured_ref("Ghost[Amount]")
    with pytest.raises(TableError):
        resolve_structured_ref(ref, reg)


def test_resolve_unknown_column_raises():
    reg = _registry()
    ref = parse_structured_ref("Sales[Profit]")
    with pytest.raises(TableError):
        resolve_structured_ref(ref, reg)


def test_resolve_implicit_with_current_table_object():
    reg = _registry()
    ref = parse_structured_ref("[Amount]")
    assert resolve_structured_ref(
        ref, reg, current_table=reg.get("Sales")
    ) == ("Sheet1", 2, 2, 4, 2)


def test_resolve_implicit_with_current_table_name():
    reg = _registry()
    ref = parse_structured_ref("[@Amount]")
    got = resolve_structured_ref(ref, reg, current_table="Sales", current_row=3)
    assert got == ("Sheet1", 3, 2, 3, 2)


def test_resolve_implicit_without_context_raises():
    reg = _registry()
    ref = parse_structured_ref("[Amount]")
    with pytest.raises(TableError):
        resolve_structured_ref(ref, reg)


# --- detect_table ----------------------------------------------------------


def test_detect_table_basic():
    t = detect_table("Sheet1", 1, 1, 4, 3, "Sales", ["Region", "Amount", "Qty"])
    assert t.name == "Sales"
    assert t.sheet == "Sheet1"
    assert t.header_row == 1
    assert t.first_data_row == 2
    assert t.last_data_row == 4
    assert t.first_col == 1
    assert t.last_col == 3
    assert t.totals_row is None
    assert t.columns == ["Region", "Amount", "Qty"]
    assert t.column_index("Amount") == 2


def test_detect_table_with_totals():
    t = detect_table(
        "Sheet1", 1, 1, 5, 3, "Sales", ["Region", "Amount", "Qty"], has_totals=True
    )
    assert t.totals_row == 5
    assert t.last_data_row == 4


def test_detect_table_normalizes_corner_order():
    t = detect_table("S", 4, 3, 1, 1, "T", ["a", "b", "c"])
    assert t.header_row == 1
    assert t.last_data_row == 4
    assert t.first_col == 1
    assert t.last_col == 3


def test_detect_table_fills_and_dedupes_headers():
    # Two blanks and a duplicate over 4 columns.
    t = detect_table("S", 0, 0, 3, 3, "T", ["Name", "", "Name", ""])
    assert t.columns == ["Name", "Column2", "Name2", "Column4"]
    # De-duped labels stay individually addressable.
    assert t.column_index("Name") == 0
    assert t.column_index("Name2") == 2


def test_detect_table_resolves_after_registration():
    reg = TableRegistry()
    reg.add(detect_table("Sheet1", 1, 1, 4, 3, "Sales", ["Region", "Amount", "Qty"]))
    ref = parse_structured_ref("Sales[Amount]")
    assert resolve_structured_ref(ref, reg) == ("Sheet1", 2, 2, 4, 2)


# --- to_a1_range (splice-into-formula helper) ------------------------------


def test_to_a1_range_multi_cell():
    assert to_a1_range("Sheet1", 2, 2, 4, 2) == "Sheet1!C3:C5"


def test_to_a1_range_single_cell_collapses():
    assert to_a1_range("Sheet1", 3, 2, 3, 2) == "Sheet1!C4"


def test_to_a1_range_unqualified():
    assert to_a1_range("Sheet1", 2, 1, 4, 3, qualify=False) == "B3:D5"


def test_to_a1_range_quotes_sheet_with_spaces():
    assert to_a1_range("My Sheet", 0, 0, 0, 0) == "'My Sheet'!A1"


def test_to_a1_range_from_resolution_round_trip():
    reg = _registry()
    ref = parse_structured_ref("Sales[[Region]:[Qty]]")
    assert to_a1_range(*resolve_structured_ref(ref, reg)) == "Sheet1!B3:D5"
