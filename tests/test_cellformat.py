"""Per-cell number formats and their persistence."""

from __future__ import annotations

import json

from abax.core.errors import CellError
from abax.core.format.cellformat import format_cell
from abax.core.workbook import Workbook


def test_format_specs():
    assert format_cell(1234.5, "general") == "1234.5"
    assert format_cell(1234.5, "int") == "1234" or format_cell(1234.5, "int") == "1235"
    assert format_cell(1234.5, "fixed2") == "1234.50"
    assert format_cell(1234567, "comma") == "1,234,567"
    assert format_cell(12.5, "currency") == "$12.50"
    assert format_cell(-12.5, "currency") == "-$12.50"
    assert format_cell(0.125, "percent") == "12.5%"
    assert format_cell(1234.5, "fixed:3") == "1234.500"


def test_format_passthrough():
    assert format_cell("hello", "currency") == "hello"  # text unaffected
    assert format_cell(None, "currency") == ""
    assert format_cell(CellError(CellError.DIV0), "percent") == "#DIV/0!"
    assert format_cell(42, "text") == "42"


def test_display_uses_cell_format():
    wb = Workbook()
    wb.sheet.set("A1", "0.25")
    wb.sheet.cell_formats[(0, 0)] = "percent"
    assert wb.sheet.display(0, 0) == "25%"


def test_formats_persist():
    wb = Workbook()
    wb.sheet.set("A1", "1234.5")
    wb.sheet.cell_formats[(0, 0)] = "currency"
    env = json.loads(json.dumps(wb.to_envelope()))
    assert env["data"]["sheets"][0]["formats"] == {"A1": "currency"}
    wb2 = Workbook.from_envelope(env)
    assert wb2.sheet.cell_formats[(0, 0)] == "currency"
    assert wb2.sheet.display(0, 0) == "$1,234.50"
