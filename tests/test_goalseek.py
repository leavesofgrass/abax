"""Tests for sheet-aware Goal Seek (``abax/core/goalseek.py``)."""

from __future__ import annotations

import pytest

from abax.core.goalseek import GoalSeekError, goal_seek
from abax.core.sheet import Sheet


def test_quadratic_goal_seek() -> None:
    # B1 = A1*A1; drive B1 to 9 by changing A1 over [0, 10] -> A1 ~= 3.
    sheet = Sheet()
    sheet.set("A1", "1")
    sheet.set("B1", "=A1*A1")
    x = goal_seek(sheet, "B1", 9, "A1", lo=0, hi=10)
    assert x == pytest.approx(3, abs=1e-6)
    assert sheet.get("A1") == pytest.approx(3, abs=1e-6)
    assert sheet.get("B1") == pytest.approx(9, abs=1e-6)


def test_linear_goal_seek() -> None:
    # B1 = 2*A1 + 1; target 11 -> A1 = 5.
    sheet = Sheet()
    sheet.set("A1", "0")
    sheet.set("B1", "=2*A1+1")
    x = goal_seek(sheet, "B1", 11, "A1", lo=-100, hi=100)
    assert x == pytest.approx(5, abs=1e-9)
    assert sheet.get("B1") == pytest.approx(11, abs=1e-9)


def test_no_solution_raises_and_restores() -> None:
    # B1 = A1*A1 + 1 is always >= 1, so target 0 has no real solution.
    sheet = Sheet()
    sheet.set("A1", "7")
    sheet.set("B1", "=A1*A1+1")
    with pytest.raises(GoalSeekError):
        goal_seek(sheet, "B1", 0, "A1", lo=-10, hi=10)
    # The changing cell's raw text is left exactly as it was.
    assert sheet.get_raw(0, 0) == "7"


def test_non_numeric_target_raises_and_restores() -> None:
    sheet = Sheet()
    sheet.set("A1", "3")
    sheet.set("B1", "=\"text\"")
    with pytest.raises(GoalSeekError):
        goal_seek(sheet, "B1", 1, "A1", lo=0, hi=10)
    assert sheet.get_raw(0, 0) == "3"
