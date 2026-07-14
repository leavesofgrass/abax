"""Document façade: open/save dispatch by extension; Excel when available.

Also home to the .xlsx formatting-fidelity round-trips (excel_io): number
formats, styles, borders, layout, merges, and conditional formats each get a
save → load → compare test. Those all `importorskip("openpyxl")` so the thin
CI environment (no openpyxl) skips them cleanly.
"""

from __future__ import annotations

import pytest

from abax.core.workbook import Workbook
from abax.engine import HAS_OPENPYXL
from abax.engine.document import Document


def test_open_csv_and_save_json(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("1,2,=A1+B1\n")
    doc = Document.open(src)
    assert doc.workbook.sheet.get("C1") == 3
    out = tmp_path / "out.abax"
    doc.save(out)
    assert out.exists()
    reopened = Document.open(out)
    assert reopened.workbook.sheet.get("C1") == 3


def test_unsupported_extension(tmp_path):
    p = tmp_path / "x.foo"
    p.write_text("nope")
    with pytest.raises(ValueError):
        Document.open(p)


@pytest.mark.skipif(not HAS_OPENPYXL, reason="openpyxl not installed")
def test_xlsx_roundtrip(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("5,10,=A1+B1\n")
    doc = Document.open(src)
    xlsx = tmp_path / "book.xlsx"
    doc.save(xlsx)
    assert xlsx.exists()
    reopened = Document.open(xlsx)
    # Formula survives the round-trip and re-evaluates.
    assert reopened.workbook.sheet.get("C1") == 15


@pytest.mark.skipif(HAS_OPENPYXL, reason="openpyxl IS installed")
def test_xlsx_without_openpyxl_raises(tmp_path):
    from abax.engine.excel_io import load_xlsx

    with pytest.raises(RuntimeError):
        load_xlsx(tmp_path / "missing.xlsx")


# --- .xlsx formatting fidelity (save -> load -> compare, per feature) --------


def _xlsx_roundtrip(wb, tmp_path):
    from abax.engine.excel_io import load_xlsx, save_xlsx

    p = tmp_path / "fidelity.xlsx"
    save_xlsx(wb, p)
    return load_xlsx(p).sheet


def test_xlsx_number_formats_roundtrip(tmp_path):
    pytest.importorskip("openpyxl")
    wb = Workbook()
    s = wb.sheet
    s.set("A1", "1234.5")
    for key, spec in {(0, 0): "comma", (1, 0): "fixed3", (2, 0): "int",
                      (3, 0): "currency", (4, 0): "percent", (5, 0): "sci",
                      (6, 0): "text"}.items():
        s.cell_formats[key] = spec
    s.cell_formats[(0, 5)] = "percent"  # on an empty cell beyond the data
    s2 = _xlsx_roundtrip(wb, tmp_path)
    assert s2.cell_formats == s.cell_formats


def test_xlsx_foreign_number_formats_map_best_effort(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from abax.engine.excel_io import load_xlsx

    wb_x = openpyxl.Workbook()
    ws = wb_x.active
    for row, (value, code) in enumerate([
            (1.5, "0.00"),                        # -> fixed2
            (2.5, "$#,##0.00_);($#,##0.00)"),      # -> currency
            (3.5, "#,##0"),                        # -> comma
            (4.5, "yyyy-mm-dd"),                   # no counterpart -> dropped
    ], start=1):
        c = ws.cell(row=row, column=1, value=value)
        c.number_format = code
    p = tmp_path / "foreign.xlsx"
    wb_x.save(p)
    s = load_xlsx(p).sheet
    assert s.cell_formats[(0, 0)] == "fixed2"
    assert s.cell_formats[(1, 0)] == "currency"
    assert s.cell_formats[(2, 0)] == "comma"
    assert (3, 0) not in s.cell_formats  # dates degrade to general, not junk


def test_xlsx_cell_styles_roundtrip(tmp_path):
    pytest.importorskip("openpyxl")
    from abax.core.format.cellstyle import CellStyle

    wb = Workbook()
    s = wb.sheet
    s.set("A1", "x")
    s.cell_styles[(0, 0)] = CellStyle(bold=True, italic=True, underline=True,
                                      align="center", text_color="#112233",
                                      bg_color="#ffee00")
    s.cell_styles[(1, 1)] = CellStyle(align="right")   # single-field style
    s.cell_styles[(2, 0)] = CellStyle(bg_color="#a6e3a1")
    s2 = _xlsx_roundtrip(wb, tmp_path)
    assert s2.cell_styles == s.cell_styles


def test_xlsx_borders_roundtrip(tmp_path):
    pytest.importorskip("openpyxl")
    wb = Workbook()
    s = wb.sheet
    s.set("A1", "x")
    s.set_cell_border(0, 0, {"top": "thin", "bottom": "thick", "left": "medium"})
    s.set_cell_border(3, 2, {"right": "thin"})  # border on an empty cell
    s2 = _xlsx_roundtrip(wb, tmp_path)
    assert s2.cell_borders == s.cell_borders


def test_xlsx_foreign_border_styles_fold_to_weights(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from openpyxl.styles import Border, Side

    from abax.engine.excel_io import load_xlsx

    wb_x = openpyxl.Workbook()
    ws = wb_x.active
    ws.cell(row=1, column=1, value="x").border = Border(
        top=Side(style="hair"), bottom=Side(style="double"),
        left=Side(style="dashed"))
    p = tmp_path / "foreign.xlsx"
    wb_x.save(p)
    s = load_xlsx(p).sheet
    assert s.cell_border(0, 0) == {"top": "thin", "bottom": "medium", "left": "thin"}


def test_xlsx_col_widths_row_heights_roundtrip(tmp_path):
    pytest.importorskip("openpyxl")
    wb = Workbook()
    s = wb.sheet
    s.set("A1", "x")
    s.set_col_width(0, 140)
    s.set_col_width(3, 61)
    s.set_row_height(1, 30)
    s.set_row_height(5, 44)
    s2 = _xlsx_roundtrip(wb, tmp_path)
    # px -> Excel units -> px inverts exactly after round()
    assert s2.col_widths == {0: 140, 3: 61}
    assert s2.row_heights == {1: 30, 5: 44}


def test_xlsx_frozen_panes_roundtrip(tmp_path):
    pytest.importorskip("openpyxl")
    wb = Workbook()
    s = wb.sheet
    s.set("A1", "x")
    s.set_frozen(1, 2)
    s2 = _xlsx_roundtrip(wb, tmp_path)
    assert (s2.frozen_rows, s2.frozen_cols) == (1, 2)

    wb.sheet.set_frozen(3, 0)  # rows only
    s3 = _xlsx_roundtrip(wb, tmp_path)
    assert (s3.frozen_rows, s3.frozen_cols) == (3, 0)


def test_xlsx_merges_roundtrip(tmp_path):
    pytest.importorskip("openpyxl")
    wb = Workbook()
    s = wb.sheet
    s.set("A1", "anchor")
    s.merge_cells(0, 0, 1, 1)
    s.merge_cells(3, 2, 3, 4)
    s2 = _xlsx_roundtrip(wb, tmp_path)
    assert sorted(s2.merges) == [(0, 0, 1, 1), (3, 2, 3, 4)]
    assert s2.get_raw(0, 0) == "anchor"


def test_xlsx_condformat_roundtrip(tmp_path):
    pytest.importorskip("openpyxl")
    from abax.core.format.condformat import CondRule

    wb = Workbook()
    s = wb.sheet
    s.set("A1", "7")
    s.cond_rules = [
        CondRule(range="A1:A9", kind=">", value=5, color="#cc0000"),
        CondRule(range="B1:B9", kind="between", value=2, value2=5.5),
        CondRule(range="C1:C9", kind="colorscale", value="#0000ff", value2="#00ff00"),
        CondRule(range="D1:D9", kind="colorscale3", value="#0000ff",
                 value2="#00ff00", color="#ffffff"),
        CondRule(range="E1:E9", kind="contains", value="foo"),
        CondRule(range="F1:F9", kind="blank"),
        CondRule(range="G1:G9", kind="above_avg"),
        CondRule(range="H1:H9", kind="top_n", value=3),
        CondRule(range="I1:I9", kind="bottom_pct", value=10),
        CondRule(range="J1:J9", kind="unique"),
        CondRule(range="K1:K9", kind="==", value="foo"),
    ]
    s2 = _xlsx_roundtrip(wb, tmp_path)
    by_range = {r.range: r for r in s2.cond_rules}
    assert by_range["A1:A9"].kind == ">" and by_range["A1:A9"].value == 5
    assert by_range["A1:A9"].color == "#cc0000"
    assert (by_range["B1:B9"].value, by_range["B1:B9"].value2) == (2, 5.5)
    assert by_range["C1:C9"].kind == "colorscale"
    assert (by_range["C1:C9"].value, by_range["C1:C9"].value2) == ("#0000ff", "#00ff00")
    assert by_range["D1:D9"].kind == "colorscale3"
    assert by_range["D1:D9"].color == "#ffffff"
    assert by_range["E1:E9"].kind == "contains" and by_range["E1:E9"].value == "foo"
    assert by_range["F1:F9"].kind == "blank"
    assert by_range["G1:G9"].kind == "above_avg"
    assert by_range["H1:H9"].kind == "top_n" and by_range["H1:H9"].value == 3
    assert by_range["I1:I9"].kind == "bottom_pct" and by_range["I1:I9"].value == 10
    assert by_range["J1:J9"].kind == "unique"
    assert by_range["K1:K9"].kind == "==" and by_range["K1:K9"].value == "foo"


def test_xlsx_condformat_css_and_regex(tmp_path):
    pytest.importorskip("openpyxl")
    from abax.core.format.condformat import CondRule, parse_css

    wb = Workbook()
    s = wb.sheet
    s.set("A1", "7")
    s.cond_rules = [
        CondRule(range="A1:A9", kind="!=", value=7,
                 css="color: white; background: #c00; font-weight: bold"),
        CondRule(range="B1:B9", kind="regex", value="a.c"),  # no Excel counterpart
    ]
    s2 = _xlsx_roundtrip(wb, tmp_path)
    assert [r.kind for r in s2.cond_rules] == ["!="]  # regex skipped, not mangled
    # The css survives as an equivalent declaration (colours normalised to hex).
    assert parse_css(s2.cond_rules[0].css) == parse_css(s.cond_rules[0].css)


def test_xlsx_unstyled_workbook_roundtrips_clean(tmp_path):
    pytest.importorskip("openpyxl")
    wb = Workbook()
    s = wb.sheet
    s.set("A1", "5")
    s.set("B1", "=A1*2")
    s2 = _xlsx_roundtrip(wb, tmp_path)
    assert s2.get_raw(0, 1) == "=A1*2"
    assert s2.cell_formats == {} and s2.cell_styles == {} and s2.cell_borders == {}
    assert s2.col_widths == {} and s2.row_heights == {} and s2.merges == []
    assert (s2.frozen_rows, s2.frozen_cols) == (0, 0)
    assert s2.cond_rules == []


def test_xlsx_values_mode_still_carries_formatting(tmp_path):
    pytest.importorskip("openpyxl")
    from abax.engine.excel_io import load_xlsx, save_xlsx

    wb = Workbook()
    s = wb.sheet
    s.set("A1", "2")
    s.set("B1", "=A1*3")
    s.cell_formats[(0, 1)] = "fixed2"
    s.set_frozen(1, 0)
    p = tmp_path / "values.xlsx"
    save_xlsx(wb, p, values=True)
    s2 = load_xlsx(p).sheet
    assert s2.get_raw(0, 1) == "6"          # computed value, not the formula
    assert s2.cell_formats[(0, 1)] == "fixed2"
    assert (s2.frozen_rows, s2.frozen_cols) == (1, 0)
