"""refscan — the tolerant live-reference scan behind formula-edit highlighting.

The scan must work on *incomplete* formulas (typed live), skip string contents
and function names, honour sheet qualifiers and ``$`` markers, and assign each
distinct reference a stable colour index in first-appearance order.
"""

from __future__ import annotations

from abax.core.refscan import refs_for_sheet, scan_refs


def test_non_formula_returns_nothing():
    assert scan_refs("A1+B2") == []
    assert scan_refs("hello") == []
    assert scan_refs("") == []


def test_single_refs_get_distinct_colors():
    spans = scan_refs("=A1+B2")
    assert [(s.r1, s.c1, s.r2, s.c2, s.color) for s in spans] == [
        (0, 0, 0, 0, 0),
        (1, 1, 1, 1, 1),
    ]


def test_duplicate_ref_shares_one_span():
    spans = scan_refs("=A1+A1*A1")
    assert len(spans) == 1
    assert spans[0].color == 0


def test_range_is_one_span():
    (s,) = scan_refs("=SUM(A1:B3)")
    assert (s.r1, s.c1, s.r2, s.c2) == (0, 0, 2, 1)


def test_dollar_markers_normalize_and_dedupe():
    spans = scan_refs("=$A$1:$B$2 + A1:B2")
    assert len(spans) == 1                      # same rectangle after $ strip


def test_sheet_qualifiers():
    spans = scan_refs("=Sheet2!A1 + 'My Sheet'!B2:C3")
    assert spans[0].sheet == "Sheet2"
    assert spans[1].sheet == "My Sheet"
    assert (spans[1].r1, spans[1].c1, spans[1].r2, spans[1].c2) == (1, 1, 2, 2)


def test_refs_inside_strings_are_ignored():
    (s,) = scan_refs('=COUNTIF(A1:A5,"B2")')
    assert (s.r1, s.c1, s.r2, s.c2) == (0, 0, 4, 0)


def test_function_names_are_not_refs():
    assert scan_refs("=LOG10(5)") == []         # LOG10( is a call, not a cell
    assert scan_refs("=SUM(1,2)") == []


def test_partial_formula_while_typing():
    # Mid-typing "=SUM(A1:A" the complete ref so far is A1 alone.
    (s,) = scan_refs("=SUM(A1:A")
    assert (s.r1, s.c1, s.r2, s.c2) == (0, 0, 0, 0)


def test_colors_cycle_over_palette():
    spans = scan_refs("=A1+B1+C1+D1+E1+F1", palette_size=5)
    assert [s.color for s in spans] == [0, 1, 2, 3, 4, 0]


def test_refs_for_sheet_filters_but_keeps_colors():
    spans = refs_for_sheet("=Sheet2!A1 + B2", "Sheet1")
    # Only the unqualified B2 lands on Sheet1, and it keeps colour 1 (the
    # cross-sheet ref consumed colour 0).
    assert len(spans) == 1
    assert (spans[0].r1, spans[0].c1) == (1, 1)
    assert spans[0].color == 1
    # Case-insensitive match for qualified refs.
    spans = refs_for_sheet("=SHEET2!A1", "sheet2")
    assert len(spans) == 1
