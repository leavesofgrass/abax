from __future__ import annotations

from abax.core.io.html_report import sheet_to_html, workbook_to_html
from abax.core.sheet import Sheet


def _sample_sheet(name: str = "Data") -> Sheet:
    sheet = Sheet(name)
    sheet.set_cell(0, 0, "Name")
    sheet.set_cell(0, 1, "Qty")
    sheet.set_cell(1, 0, "Widget")
    sheet.set_cell(1, 1, "42")
    return sheet


def test_sheet_to_html_is_a_full_document():
    html_out = sheet_to_html(_sample_sheet())
    assert "<!DOCTYPE html>" in html_out
    assert "<table" in html_out
    assert "Data" in html_out  # sheet name in title and <h2>


def test_sheet_to_html_contains_displayed_cell_value():
    sheet = _sample_sheet()
    html_out = sheet_to_html(sheet)
    # A known displayed value.
    assert sheet.display(1, 0) == "Widget"
    assert "Widget" in html_out


def test_sheet_to_html_has_column_letter_headers():
    html_out = sheet_to_html(_sample_sheet())
    assert "<th>A</th>" in html_out
    assert "<th>B</th>" in html_out


def test_sheet_to_html_has_row_number_headers():
    html_out = sheet_to_html(_sample_sheet())
    assert "<th>1</th>" in html_out
    assert "<th>2</th>" in html_out


def test_sheet_to_html_escapes_script_content():
    sheet = Sheet("Evil")
    sheet.set_cell(0, 0, "<script>alert(1)</script>")
    html_out = sheet_to_html(sheet)
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_sheet_to_html_uses_custom_title():
    html_out = sheet_to_html(_sample_sheet(), title="My Report")
    assert "<title>My Report</title>" in html_out


def test_sheet_to_html_truncation_note_on_too_many_rows():
    sheet = Sheet("Big")
    for r in range(10):
        sheet.set_cell(r, 0, str(r))
    html_out = sheet_to_html(sheet, max_rows=3)
    assert "more rows" in html_out
    # 10 populated rows, 3 shown -> 7 omitted.
    assert "7 more rows" in html_out


def test_sheet_to_html_truncation_note_on_too_many_cols():
    sheet = Sheet("Wide")
    for c in range(8):
        sheet.set_cell(0, c, str(c))
    html_out = sheet_to_html(sheet, max_cols=2)
    assert "more columns" in html_out
    assert "6 more columns" in html_out


def test_sheet_to_html_no_note_when_within_bounds():
    html_out = sheet_to_html(_sample_sheet())
    assert "more rows" not in html_out
    assert "more columns" not in html_out


def test_workbook_to_html_includes_all_sheet_names():
    class FakeWorkbook:
        def __init__(self, sheets):
            self.sheets = sheets

    wb = FakeWorkbook([_sample_sheet("Alpha"), _sample_sheet("Beta")])
    html_out = workbook_to_html(wb)
    assert "<!DOCTYPE html>" in html_out
    assert "Alpha" in html_out
    assert "Beta" in html_out
    assert html_out.count("<table") == 2


def test_workbook_to_html_uses_real_workbook():
    # Prefer the real Workbook if available; skip gracefully otherwise.
    try:
        from abax.core.workbook import Workbook
    except Exception:
        return
    wb = Workbook()
    wb.sheets = [_sample_sheet("One"), _sample_sheet("Two")]
    html_out = workbook_to_html(wb, title="Book")
    assert "<title>Book</title>" in html_out
    assert "One" in html_out
    assert "Two" in html_out
