"""Tests for conditional formatting (``abax.core.format.condformat``)."""

from __future__ import annotations

from abax.core.format.condformat import (
    CondRule,
    _lerp_color,
    _parse_hex,
    color_at,
    evaluate,
    scale_context,
)
from abax.core.sheet import Sheet


def _col(rule: CondRule, sheet: Sheet) -> dict[tuple[int, int], str]:
    return evaluate(sheet, [rule])


def test_color_at_matches_evaluate() -> None:
    """The per-cell entry point must agree with the full-range evaluate()."""
    sheet = Sheet()
    for i, v in enumerate([3, 8, 12, 20]):
        sheet.set(f"A{i + 1}", str(v))
    sheet.set("B2", "hello")
    rules = [
        CondRule(range="A1:A4", kind=">", value=10, color="#ff0000"),
        CondRule(range="B1:B4", kind="contains", value="ell", color="#00ff00"),
        CondRule(range="A1:A4", kind="colorscale", value="#000000", value2="#ffffff"),
    ]
    full = evaluate(sheet, rules)
    ctx = scale_context(sheet, rules)
    for r in range(4):
        for c in range(2):
            assert color_at(sheet, rules, r, c, ctx) == full.get((r, c))
    # a cell outside every rule range is None
    assert color_at(sheet, rules, 50, 50, ctx) is None


def test_greater_than_colors_right_cells() -> None:
    sheet = Sheet()
    sheet.set("A1", "5")
    sheet.set("A2", "10")
    sheet.set("A3", "15")
    sheet.set("A4", "20")
    rule = CondRule(range="A1:A4", kind=">", value=12, color="#FF0000")
    result = _col(rule, sheet)
    # A3 (row 2) and A4 (row 3) are > 12, col 0.
    assert result == {(2, 0): "#ff0000", (3, 0): "#ff0000"}


def test_between() -> None:
    sheet = Sheet()
    for i, v in enumerate([1, 5, 10, 15]):
        sheet.set(f"A{i + 1}", str(v))
    rule = CondRule(range="A1:A4", kind="between", value=5, value2=10, color="#00ff00")
    result = _col(rule, sheet)
    assert result == {(1, 0): "#00ff00", (2, 0): "#00ff00"}


def test_contains_case_insensitive() -> None:
    sheet = Sheet()
    sheet.set("A1", "Hello World")
    sheet.set("A2", "goodbye")
    sheet.set("A3", "WORLDLY")
    rule = CondRule(range="A1:A3", kind="contains", value="world", color="#abcdef")
    result = _col(rule, sheet)
    assert result == {(0, 0): "#abcdef", (2, 0): "#abcdef"}


def test_blank() -> None:
    sheet = Sheet()
    sheet.set("A1", "x")
    # A2 left empty
    sheet.set("A3", "y")
    rule = CondRule(range="A1:A3", kind="blank", value=None, color="#111111")
    result = _col(rule, sheet)
    assert result == {(1, 0): "#111111"}


def test_notblank() -> None:
    sheet = Sheet()
    sheet.set("A1", "x")
    sheet.set("A3", "y")
    rule = CondRule(range="A1:A3", kind="notblank", color="#222222")
    result = _col(rule, sheet)
    assert result == {(0, 0): "#222222", (2, 0): "#222222"}


def test_colorscale_endpoints_and_midpoint() -> None:
    sheet = Sheet()
    sheet.set("A1", "0")
    sheet.set("A2", "5")
    sheet.set("A3", "10")
    rule = CondRule(
        range="A1:A3",
        kind="colorscale",
        value="#000000",
        value2="#ffffff",
    )
    result = _col(rule, sheet)
    assert result[(0, 0)] == "#000000"  # min -> value
    assert result[(2, 0)] == "#ffffff"  # max -> value2
    # midpoint t=0.5 -> round(127.5)=128 -> 0x80
    mid = result[(1, 0)]
    r = int(mid[1:3], 16)
    assert abs(r - 128) <= 1


def test_colorscale_equal_values() -> None:
    sheet = Sheet()
    sheet.set("A1", "7")
    sheet.set("A2", "7")
    rule = CondRule(
        range="A1:A2", kind="colorscale", value="#000000", value2="#ffffff"
    )
    result = _col(rule, sheet)
    # span == 0 -> t = 0.0 -> min color for both
    assert result == {(0, 0): "#000000", (1, 0): "#000000"}


def test_to_dict_from_dict_roundtrip() -> None:
    rule = CondRule(
        range="B2:D5",
        kind="between",
        value=1.5,
        value2=9,
        color="#a6e3a1",
    )
    d = rule.to_dict()
    again = CondRule.from_dict(d)
    assert again == rule
    assert again.to_dict() == d


def test_later_rule_overrides_earlier() -> None:
    sheet = Sheet()
    sheet.set("A1", "100")
    first = CondRule(range="A1", kind=">", value=0, color="#aaaaaa")
    second = CondRule(range="A1", kind=">", value=0, color="#bbbbbb")
    result = evaluate(sheet, [first, second])
    assert result == {(0, 0): "#bbbbbb"}


def test_error_and_none_cells_skipped() -> None:
    sheet = Sheet()
    sheet.set("A1", "=1/0")  # CellError
    # A2 empty -> None
    sheet.set("A3", "50")
    rule = CondRule(range="A1:A3", kind=">", value=10, color="#cccccc")
    result = _col(rule, sheet)
    assert result == {(2, 0): "#cccccc"}


def test_bool_not_treated_as_number() -> None:
    sheet = Sheet()
    sheet.set("A1", "=1=1")  # TRUE (bool)
    rule = CondRule(range="A1", kind=">", value=0, color="#dddddd")
    result = _col(rule, sheet)
    assert result == {}


def test_equality_text_case_insensitive() -> None:
    sheet = Sheet()
    sheet.set("A1", "Apple")
    sheet.set("A2", "banana")
    rule = CondRule(range="A1:A2", kind="==", value="APPLE", color="#eeeeee")
    result = _col(rule, sheet)
    assert result == {(0, 0): "#eeeeee"}


def test_helpers() -> None:
    assert _parse_hex("#ff8000") == (255, 128, 0)
    assert _parse_hex("00ff00") == (0, 255, 0)
    assert _lerp_color((0, 0, 0), (255, 255, 255), 0.0) == "#000000"
    assert _lerp_color((0, 0, 0), (255, 255, 255), 1.0) == "#ffffff"


# --- richer rule kinds (0.1.13) ----------------------------------------------


def _num_sheet() -> Sheet:
    sheet = Sheet()
    for i, v in enumerate([5, 20, 8, 20, 3, 50]):  # rows A1..A6
        sheet.set(f"A{i + 1}", str(v))
    return sheet


def _text_sheet() -> Sheet:
    sheet = Sheet()
    for i, w in enumerate(["apple", "Banana", "apple", "cherry"]):  # B1..B4
        sheet.set(f"B{i + 1}", w)
    return sheet


def test_top_n_includes_boundary_ties() -> None:
    # top 2 of [5,20,8,20,3,50]: threshold is the 2nd-largest (20), so both 20s
    # and the 50 all qualify — Excel-style tie inclusion.
    sheet = _num_sheet()
    rule = CondRule(range="A1:A6", kind="top_n", value=2, color="#ff0000")
    assert set(_col(rule, sheet)) == {(1, 0), (3, 0), (5, 0)}


def test_bottom_n() -> None:
    sheet = _num_sheet()
    rule = CondRule(range="A1:A6", kind="bottom_n", value=1, color="#00ff00")
    assert set(_col(rule, sheet)) == {(4, 0)}  # the 3


def test_top_pct() -> None:
    sheet = _num_sheet()  # 6 values; top 50% = 3 largest (50, 20, 20)
    rule = CondRule(range="A1:A6", kind="top_pct", value=50, color="#123456")
    assert set(_col(rule, sheet)) == {(1, 0), (3, 0), (5, 0)}


def test_above_and_below_average() -> None:
    sheet = _num_sheet()  # mean = 106/6 = 17.67
    above = CondRule(range="A1:A6", kind="above_avg", color="#aa0000")
    below = CondRule(range="A1:A6", kind="below_avg", color="#0000aa")
    assert set(_col(above, sheet)) == {(1, 0), (3, 0), (5, 0)}      # 20,20,50
    assert set(_col(below, sheet)) == {(0, 0), (2, 0), (4, 0)}      # 5,8,3


def test_duplicate_and_unique() -> None:
    sheet = _text_sheet()  # apple (x2, case-insensitive), Banana, cherry
    dup = CondRule(range="B1:B4", kind="duplicate", color="#abc123")
    uniq = CondRule(range="B1:B4", kind="unique", color="#321cba")
    assert set(_col(dup, sheet)) == {(0, 1), (2, 1)}
    assert set(_col(uniq, sheet)) == {(1, 1), (3, 1)}


def test_beginswith_endswith_case_insensitive() -> None:
    sheet = _text_sheet()
    begins = CondRule(range="B1:B4", kind="beginswith", value="BA", color="#111111")
    ends = CondRule(range="B1:B4", kind="endswith", value="RY", color="#222222")
    assert set(_col(begins, sheet)) == {(1, 1)}   # Banana
    assert set(_col(ends, sheet)) == {(3, 1)}     # cherry


def test_colorscale3_endpoints_and_midpoint() -> None:
    sheet = Sheet()
    for i, v in enumerate([0, 5, 10]):
        sheet.set(f"A{i + 1}", str(v))
    rule = CondRule(range="A1:A3", kind="colorscale3",
                    value="#000000", value2="#ffffff", color="#ff0000")
    result = _col(rule, sheet)
    assert result[(0, 0)] == "#000000"   # min -> value (low)
    assert result[(2, 0)] == "#ffffff"   # max -> value2 (high)
    assert result[(1, 0)] == "#ff0000"   # midpoint -> the mid colour


def test_color_at_parity_for_range_kinds() -> None:
    """color_at (viewport) must agree with evaluate() for the range-aware kinds."""
    sheet = _num_sheet()
    rules = [
        CondRule(range="A1:A6", kind="above_avg", color="#0000ff"),
        CondRule(range="A1:A6", kind="top_n", value=2, color="#ff0000"),
    ]
    full = evaluate(sheet, rules)
    ctx = scale_context(sheet, rules)
    for r in range(6):
        assert color_at(sheet, rules, r, 0, ctx) == full.get((r, 0))


def test_top_n_roundtrip() -> None:
    rule = CondRule(range="A1:A6", kind="top_n", value=10, color="#a6e3a1")
    assert CondRule.from_dict(rule.to_dict()) == rule
