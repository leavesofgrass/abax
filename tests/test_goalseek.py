"""Tests for the one-variable goal solver (``abax/core/goalseek.py``)."""

from __future__ import annotations

import math

import pytest

from abax.core.goalseek import GoalSeekError, goal_seek


def test_quadratic_secant() -> None:
    # f(x) = x**2, target 9, seeded at x0=2 -> converges to 3 via secant.
    root = goal_seek(lambda x: x**2, 9, 2)
    assert root == pytest.approx(3, abs=1e-6)


def test_linear_exact() -> None:
    # f(x) = 2x + 1, target 7 -> x = 3. Secant nails a linear g in one step.
    root = goal_seek(lambda x: 2 * x + 1, 7, 0)
    assert root == pytest.approx(3, abs=1e-9)


def test_requires_expanding_bracket() -> None:
    # Poor seeds on the same side; secant on this cubic stalls, so the solver
    # must expand outward to find a bracket and bisect. Root of x**3 = 8 is 2.
    root = goal_seek(lambda x: x**3, 8, 100, x1=101)
    assert root == pytest.approx(2, abs=1e-6)


def test_monotonic_from_poor_seed() -> None:
    # Monotonic exp curve seeded far away. e**x = e**2 -> x = 2.
    root = goal_seek(math.exp, math.e**2, -50)
    assert root == pytest.approx(2, abs=1e-6)


def test_no_solution_raises() -> None:
    # f(x) = x**2 + 1 is never <= 0; target 0 has no real solution.
    with pytest.raises(GoalSeekError):
        goal_seek(lambda x: x**2 + 1, 0, 0)


def test_function_that_raises() -> None:
    def boom(_x: float) -> float:
        raise ValueError("kaboom")

    with pytest.raises(GoalSeekError):
        goal_seek(boom, 1, 0)


def test_nan_result_raises() -> None:
    with pytest.raises(GoalSeekError):
        goal_seek(lambda _x: math.nan, 0, 1)
