"""Tests for keyboard-navigation helpers (``abax.core.navigation``)."""

from __future__ import annotations

import pytest

from abax.core.navigation import (
    NavError,
    current_region,
    jump_edge,
    parse_target,
)

# --- parse_target ---------------------------------------------------------

def test_parse_target_single_cell():
    assert parse_target("B3") == (2, 1)


def test_parse_target_range_lowercase():
    assert parse_target("a1:c2") == (0, 0, 1, 2)


def test_parse_target_absolute_markers():
    assert parse_target("$A$1") == (0, 0)


def test_parse_target_range_normalised():
    assert parse_target("C3:A1") == (0, 0, 2, 2)


def test_parse_target_surrounding_spaces():
    assert parse_target("  B3  ") == (2, 1)
    assert parse_target("  a1 : c2 ".replace(" ", "")) == (0, 0, 1, 2)


def test_parse_target_bad_raises():
    with pytest.raises(NavError):
        parse_target("zzz")


def test_parse_target_empty_raises():
    with pytest.raises(NavError):
        parse_target("")
    with pytest.raises(NavError):
        parse_target("   ")


# --- jump_edge ------------------------------------------------------------

def test_jump_edge_end_of_run_down():
    # A1:A5 populated (rows 0..4, col 0).
    populated = {(r, 0) for r in range(5)}
    assert jump_edge(populated, 0, 0, 1, 0, 100, 100) == (4, 0)


def test_jump_edge_from_end_clamps_to_max_row():
    populated = {(r, 0) for r in range(5)}
    # From (4,0) going down with nothing below -> grid edge (clamp to max_row).
    assert jump_edge(populated, 4, 0, 1, 0, 9, 9) == (9, 0)


def test_jump_edge_end_of_first_run_then_jump_gap():
    # Rows 0, 1 populated, then a gap, then row 5 populated.
    populated = {(0, 0), (1, 0), (5, 0)}
    # From (0,0) going down -> end of first run (1,0).
    assert jump_edge(populated, 0, 0, 1, 0, 100, 100) == (1, 0)
    # From (1,0) going down -> jump across gap to next populated (5,0).
    assert jump_edge(populated, 1, 0, 1, 0, 100, 100) == (5, 0)


def test_jump_edge_from_blank_to_next_populated():
    populated = {(5, 0)}
    # From blank (1,0) going down -> next populated (5,0).
    assert jump_edge(populated, 1, 0, 1, 0, 100, 100) == (5, 0)


def test_jump_edge_from_blank_no_populated_clamps():
    populated: set[tuple[int, int]] = set()
    assert jump_edge(populated, 1, 0, 1, 0, 9, 9) == (9, 0)


def test_jump_edge_up_and_horizontal():
    # Horizontal run A1:E1 (col 0..4, row 0).
    populated = {(0, c) for c in range(5)}
    assert jump_edge(populated, 0, 0, 0, 1, 100, 100) == (0, 4)
    assert jump_edge(populated, 0, 4, 0, -1, 100, 100) == (0, 0)
    # Up from a run anchored at the top edge.
    col = {(r, 0) for r in range(5)}
    assert jump_edge(col, 4, 0, -1, 0, 100, 100) == (0, 0)


def test_jump_edge_never_off_grid():
    populated = {(0, 0)}
    # Going up/left from the corner stays clamped at 0.
    assert jump_edge(populated, 0, 0, -1, 0, 9, 9) == (0, 0)
    assert jump_edge(populated, 0, 0, 0, -1, 9, 9) == (0, 0)


# --- current_region -------------------------------------------------------

def test_current_region_rectangle():
    # 2x2 block at rows 1..2, cols 1..2.
    populated = {(1, 1), (1, 2), (2, 1), (2, 2)}
    assert current_region(populated, 1, 1) == (1, 1, 2, 2)
    assert current_region(populated, 2, 2) == (1, 1, 2, 2)


def test_current_region_l_shape():
    # L shape: column (0,0),(1,0),(2,0) plus (2,1),(2,2).
    populated = {(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)}
    assert current_region(populated, 0, 0) == (0, 0, 2, 2)


def test_current_region_isolated_cell():
    populated = {(3, 3)}
    assert current_region(populated, 3, 3) == (3, 3, 3, 3)


def test_current_region_blank_seed():
    populated = {(1, 1), (1, 2)}
    assert current_region(populated, 5, 5) == (5, 5, 5, 5)


def test_current_region_ignores_disconnected_block():
    # Two separate blocks; seeding one must not include the other.
    populated = {(0, 0), (0, 1), (5, 5), (5, 6)}
    assert current_region(populated, 0, 0) == (0, 0, 0, 1)
    assert current_region(populated, 5, 5) == (5, 5, 5, 6)
