"""Tests for the formula-precedent extraction engine."""

from __future__ import annotations

import pytest

from abax.core.precedents import (
    Precedent,
    PrecedentError,
    precedent_cells,
    precedents,
)


def test_two_cell_refs():
    result = precedents("=A1+B2")
    assert len(result) == 2
    assert result[0] == Precedent("cell", "A1", ((0, 0),))
    assert result[1] == Precedent("cell", "B2", ((1, 1),))


def test_range_precedent():
    result = precedents("=SUM(A1:A3)*2")
    assert len(result) == 1
    p = result[0]
    assert p.kind == "range"
    assert p.a1 == "A1:A3"
    assert p.cells == ((0, 0), (1, 0), (2, 0))


def test_absolute_markers_ignored():
    result = precedents("=$B$7")
    assert len(result) == 1
    assert result[0] == Precedent("cell", "B7", ((6, 1),))


def test_absolute_and_relative_dedupe():
    # $B$7 and B7 are the same precedent.
    result = precedents("=$B$7+B7")
    assert len(result) == 1
    assert result[0].a1 == "B7"


def test_non_formula_returns_empty():
    assert precedents("hello") == []


def test_literal_formula_has_no_precedents():
    assert precedents("=42") == []


def test_dedupe_repeated_cell():
    result = precedents("=A1+A1")
    assert len(result) == 1
    assert result[0] == Precedent("cell", "A1", ((0, 0),))


def test_precedent_cells_flat_set():
    cells = precedent_cells("=SUM(A1:B2)+C5")
    assert cells == {(0, 0), (0, 1), (1, 0), (1, 1), (4, 2)}


def test_precedent_cells_non_formula():
    assert precedent_cells("just text") == set()


def test_precedent_cells_empty_string():
    assert precedent_cells("") == set()


def test_malformed_formula_raises():
    with pytest.raises(PrecedentError):
        precedents("=SUM(")


def test_malformed_garbage_raises():
    with pytest.raises(PrecedentError):
        precedents("=@@@")


def test_precedent_is_frozen():
    p = Precedent("cell", "A1", ((0, 0),))
    with pytest.raises(AttributeError):       # frozen dataclass -> FrozenInstanceError
        p.kind = "range"  # type: ignore[misc]


def test_first_seen_order_preserved():
    result = precedents("=C3+A1+B2")
    assert [p.a1 for p in result] == ["C3", "A1", "B2"]


def test_mixed_cells_and_ranges():
    result = precedents("=A1+SUM(B1:B3)+A1")
    assert len(result) == 2
    assert result[0] == Precedent("cell", "A1", ((0, 0),))
    assert result[1].kind == "range"
    assert result[1].a1 == "B1:B3"


def test_nested_function_refs():
    result = precedents("=IF(A1>0,SUM(B1:B2),C1)")
    a1s = [p.a1 for p in result]
    assert a1s == ["A1", "B1:B2", "C1"]


def test_string_literal_not_a_ref():
    # A1-looking text inside a string must not become a precedent.
    result = precedents('=CONCAT("A1",B2)')
    assert len(result) == 1
    assert result[0].a1 == "B2"
