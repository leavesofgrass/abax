"""Tests for abax.core.profile — data profiling and formula-recalc profiling."""

from __future__ import annotations

import statistics

from abax.core.profile import (
    CellTiming,
    dependency_svg,
    format_report,
    profile_column,
    profile_recalc,
    profile_sheet,
    slowest,
)
from abax.core.sheet import Sheet
from abax.core.workbook import Workbook


def test_numeric_column_stats():
    values = [10, 20, 30, 40, 50]
    prof = profile_column(values)

    assert prof["dtype"] == "int"
    assert prof["count"] == 5
    assert prof["missing"] == 0
    assert prof["unique"] == 5
    assert prof["min"] == 10
    assert prof["max"] == 50
    assert prof["mean"] == 30
    assert prof["median"] == 30
    assert prof["std"] == statistics.pstdev([10, 20, 30, 40, 50])
    q1, _q2, q3 = statistics.quantiles([10, 20, 30, 40, 50], n=4)
    assert prof["q1"] == q1
    assert prof["q3"] == q3


def test_float_column_is_float():
    prof = profile_column([1.5, 2.5, "3.5", None])
    assert prof["dtype"] == "float"
    assert prof["count"] == 3
    assert prof["missing"] == 1
    assert prof["min"] == 1.5
    assert prof["max"] == 3.5
    assert prof["mean"] == statistics.mean([1.5, 2.5, 3.5])


def test_single_value_numeric_std_and_quartiles():
    prof = profile_column([42])
    assert prof["dtype"] == "int"
    assert prof["std"] == 0.0
    assert prof["q1"] == 42
    assert prof["q3"] == 42


def test_text_column_top_and_max_len():
    values = ["apple", "banana", "apple", "cherry", "banana", "apple", "fig"]
    prof = profile_column(values)

    assert prof["dtype"] == "text"
    assert prof["count"] == 7
    assert prof["unique"] == 4
    assert prof["max_len"] == len("banana")
    # apple x3 (first seen), banana x2 (second seen), then singletons.
    assert prof["top"][0] == ("apple", 3)
    assert prof["top"][1] == ("banana", 2)
    assert len(prof["top"]) == 4


def test_top_capped_at_five():
    values = ["a", "b", "c", "d", "e", "f", "g"]
    prof = profile_column(values)
    assert len(prof["top"]) == 5


def test_missing_counts_none_and_empty_string():
    values = [1, None, 2, "", 3, None]
    prof = profile_column(values)
    assert prof["count"] == 3
    assert prof["missing"] == 3
    assert prof["dtype"] == "int"


def test_mixed_int_and_text_is_text():
    prof = profile_column([1, 2, "hello", 4])
    assert prof["dtype"] == "text"
    assert "top" in prof
    assert "mean" not in prof


def test_bool_column_is_bool():
    prof = profile_column([True, False, True, True])
    assert prof["dtype"] == "bool"
    assert prof["count"] == 4
    # numeric stats computed over 1/0 encoding
    assert prof["mean"] == statistics.mean([1.0, 0.0, 1.0, 1.0])
    assert prof["min"] == 0.0
    assert prof["max"] == 1.0


def test_empty_column():
    prof = profile_column([None, "", None])
    assert prof["dtype"] == "empty"
    assert prof["count"] == 0
    assert prof["missing"] == 3
    assert prof["unique"] == 0


def test_profile_sheet_with_header_row():
    sheet = Sheet(name="Data")
    headers = ["Name", "Age", "Score"]
    for col, h in enumerate(headers):
        sheet.set_cell(0, col, h)
    rows = [
        ["Alice", "30", "9.5"],
        ["Bob", "25", "8.0"],
        ["Carol", "35", "7.5"],
    ]
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            sheet.set_cell(r, c, val)

    profs = profile_sheet(sheet, header_row=True)

    assert len(profs) == 3
    assert [p["name"] for p in profs] == ["Name", "Age", "Score"]

    name_col, age_col, score_col = profs
    assert name_col["dtype"] == "text"
    assert name_col["count"] == 3  # header not counted as data

    assert age_col["dtype"] == "int"
    assert age_col["count"] == 3
    assert age_col["min"] == 25
    assert age_col["max"] == 35

    assert score_col["dtype"] == "float"
    assert score_col["count"] == 3


def test_profile_sheet_without_header_uses_column_letters():
    sheet = Sheet(name="Raw")
    sheet.set_cell(0, 0, "10")
    sheet.set_cell(1, 0, "20")
    sheet.set_cell(0, 1, "x")
    sheet.set_cell(1, 1, "y")

    profs = profile_sheet(sheet, header_row=False)

    assert len(profs) == 2
    assert [p["name"] for p in profs] == ["A", "B"]
    assert profs[0]["dtype"] == "int"
    assert profs[0]["count"] == 2  # first row IS data here
    assert profs[1]["dtype"] == "text"


# --- recalc profiling -------------------------------------------------------


def _chain_workbook() -> Workbook:
    """A1=1, A2=A1+1, … A5=A4+1, plus an independent slow-ish formula in C1."""
    wb = Workbook()
    sheet = wb.sheet
    sheet.set("A1", "1")
    for i in range(2, 6):
        sheet.set(f"A{i}", f"=A{i - 1}+1")
    # An independent formula that does more work than a single add.
    sheet.set("C1", "=SUM(A1:A5)*SQRT(2)+SUMPRODUCT(A1:A5,A1:A5)")
    return wb


def test_profile_recalc_covers_every_formula_cell():
    wb = _chain_workbook()
    timings = profile_recalc(wb)

    # A2..A5 (4) + C1 (1) are formulas; A1 is a literal and excluded.
    a1s = {t.a1 for t in timings}
    assert a1s == {"A2", "A3", "A4", "A5", "C1"}
    assert len(timings) == 5

    for t in timings:
        assert isinstance(t, CellTiming)
        assert t.a1 and t.formula.startswith("=")   # a1 + formula populated
        assert t.seconds >= 0.0                      # non-negative
        assert t.sheet == "Sheet1"


def test_profile_recalc_sorted_descending():
    wb = _chain_workbook()
    timings = profile_recalc(wb)
    secs = [t.seconds for t in timings]
    assert secs == sorted(secs, reverse=True)


def test_profile_recalc_repeat_averages():
    wb = _chain_workbook()
    timings = profile_recalc(wb, repeat=3)
    assert len(timings) == 5
    assert all(t.seconds >= 0.0 for t in timings)


def test_profile_recalc_sheet_selector():
    wb = _chain_workbook()
    by_name = profile_recalc(wb, sheet="Sheet1")
    by_obj = profile_recalc(wb, sheet=wb.sheet)
    assert {t.a1 for t in by_name} == {"A2", "A3", "A4", "A5", "C1"}
    assert {t.a1 for t in by_obj} == {"A2", "A3", "A4", "A5", "C1"}
    # An unknown sheet name profiles nothing.
    assert profile_recalc(wb, sheet="Nope") == []


def test_slowest_limits_count():
    wb = _chain_workbook()
    top = slowest(wb, n=3)
    assert len(top) == 3
    # It is a prefix of a full, descending profile (compare within one run —
    # absolute timings are noisy across separate runs).
    full = profile_recalc(wb)
    assert [t.seconds for t in full] == sorted((t.seconds for t in full), reverse=True)
    assert len(full) == 5


def test_format_report_contains_refs_and_ms():
    wb = _chain_workbook()
    report = format_report(profile_recalc(wb))
    assert "ms" in report
    for ref in ("A2", "A5", "C1"):
        assert ref in report
    # Rank column and a formula snippet are present.
    assert "Formula" in report


def test_dependency_svg_precedents_of_a5():
    wb = _chain_workbook()
    svg = dependency_svg(wb.sheet, *_a1("A5"), direction="precedents")
    assert "<svg" in svg
    # The whole chain A1..A5 shows up as node labels.
    for ref in ("A1", "A2", "A3", "A4", "A5"):
        assert ref in svg
    # Boxes and edges are drawn.
    assert "<line" in svg
    assert "<rect" in svg


def test_dependency_svg_dependents_direction():
    wb = _chain_workbook()
    svg = dependency_svg(wb.sheet, *_a1("A1"), direction="dependents")
    assert "<svg" in svg
    # A1 feeds A2 and C1 (directly).
    assert "A2" in svg and "C1" in svg


def test_dependency_svg_bad_direction_raises():
    wb = _chain_workbook()
    try:
        dependency_svg(wb.sheet, *_a1("A5"), direction="sideways")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for a bad direction")


def test_empty_sheet_profiles_and_svg():
    wb = Workbook()  # a single blank Sheet1
    assert profile_recalc(wb) == []
    assert slowest(wb, n=5) == []
    # format_report tolerates an empty timing list.
    assert isinstance(format_report([]), str)
    # A dependency SVG on a blank cell is still valid SVG.
    svg = dependency_svg(wb.sheet, *_a1("A1"))
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")


def _a1(ref: str) -> tuple[int, int]:
    from abax.core.reference import parse_a1

    return parse_a1(ref)
