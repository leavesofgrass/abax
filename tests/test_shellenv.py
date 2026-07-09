"""Tests for :mod:`abax.core.shellenv` — the ``$ABAX_*`` selection-context vars."""

from __future__ import annotations

import json

from abax.core.shellenv import merged_env, selection_env
from abax.core.workbook import Workbook


def _grid_2x2() -> Workbook:
    """A workbook whose sheet holds a 2x2 block at A1:B2.

    ::

        1     hello
        2.5   world
    """
    wb = Workbook()
    sheet = wb.sheet
    sheet.set("A1", "1")
    sheet.set("B1", "hello")
    sheet.set("A2", "2.5")
    sheet.set("B2", "world")
    return wb


def test_active_cell_and_range() -> None:
    sheet = _grid_2x2().sheet
    env = selection_env(sheet, 0, 0, 1, 1)
    assert env["ABAX_ACTIVE_CELL"] == "A1"
    assert env["ABAX_SELECTION_RANGE"] == "A1:B2"


def test_single_cell_range_is_bare() -> None:
    sheet = _grid_2x2().sheet
    env = selection_env(sheet, 0, 0, 0, 0)
    assert env["ABAX_ACTIVE_CELL"] == "A1"
    assert env["ABAX_SELECTION_RANGE"] == "A1"


def test_corners_are_normalised() -> None:
    # Bottom-right passed first still yields a top-left active cell / range.
    sheet = _grid_2x2().sheet
    env = selection_env(sheet, 1, 1, 0, 0)
    assert env["ABAX_ACTIVE_CELL"] == "A1"
    assert env["ABAX_SELECTION_RANGE"] == "A1:B2"


def test_selection_json_roundtrips() -> None:
    sheet = _grid_2x2().sheet
    env = selection_env(sheet, 0, 0, 1, 1)
    parsed = json.loads(env["ABAX_SELECTION_JSON"])
    assert parsed == [[1, "hello"], [2.5, "world"]]


def test_selection_json_is_compact() -> None:
    sheet = _grid_2x2().sheet
    env = selection_env(sheet, 0, 0, 1, 1)
    # Compact separators: no spaces after ',' or ':'.
    assert ", " not in env["ABAX_SELECTION_JSON"]


def test_selection_tsv_tabs_and_newlines() -> None:
    sheet = _grid_2x2().sheet
    env = selection_env(sheet, 0, 0, 1, 1)
    assert env["ABAX_SELECTION_TSV"] == "1\thello\n2.5\tworld"
    lines = env["ABAX_SELECTION_TSV"].split("\n")
    assert len(lines) == 2
    assert lines[0].split("\t") == ["1", "hello"]


def test_not_truncated_for_small_selection() -> None:
    sheet = _grid_2x2().sheet
    env = selection_env(sheet, 0, 0, 1, 1)
    assert "ABAX_SELECTION_TRUNCATED" not in env


def test_merged_env_contains_base_and_abax_keys() -> None:
    sheet = _grid_2x2().sheet
    base = {"PATH": "/usr/bin", "HOME": "/home/tester"}
    env = merged_env(base, sheet, 0, 0, 1, 1)
    # Base keys survive.
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/tester"
    # ABAX_ keys are layered on top.
    assert env["ABAX_ACTIVE_CELL"] == "A1"
    assert env["ABAX_SELECTION_RANGE"] == "A1:B2"
    assert json.loads(env["ABAX_SELECTION_JSON"]) == [[1, "hello"], [2.5, "world"]]
    # The passed-in base is not mutated.
    assert "ABAX_ACTIVE_CELL" not in base


def test_merged_env_defaults_to_os_environ() -> None:
    sheet = _grid_2x2().sheet
    env = merged_env(None, sheet, 0, 0, 0, 0)
    assert env["ABAX_ACTIVE_CELL"] == "A1"
