"""Tests for :mod:`abax.core.science.ode_implicit` (stiff / implicit ODE solvers)."""

from __future__ import annotations

import math

import pytest

from abax.core.science.ode_implicit import (
    StiffODEError,
    _jacobian,
    _solve_linear,
    backward_euler,
    bdf2,
    implicit_trapezoid,
    solve_stiff,
)

# --------------------------------------------------------------------------- #
# Stiff scalar: y' = -1000 y, y0 = 1, over [0, 0.1].
# Exact y(0.1) = exp(-100) ~= 3.7e-44, i.e. effectively zero.
# --------------------------------------------------------------------------- #


def test_backward_euler_stiff_stable():
    f = lambda t, y: [-1000.0 * y[0]]
    ts, ys = backward_euler(f, 0.0, [1.0], 0.1, n=50)

    assert len(ts) == 51
    assert len(ys) == 51

    # Every intermediate value stays bounded (no blow-up) and finite.
    for y in ys:
        assert math.isfinite(y[0])
        assert abs(y[0]) <= 1.0

    y_final = ys[-1][0]
    # Small, positive, effectively zero (within ~1e-2 of exp(-100) ~ 0).
    assert 0.0 <= y_final < 1e-3


def test_explicit_euler_would_be_unstable_here():
    # Demonstration only: explicit Euler amplification factor for this problem
    # with n=50 over [0,0.1] is 1 + h*(-1000) = 1 - 1000*0.002 = -1, magnitude 1
    # (borderline; non-decaying). Backward Euler's factor 1/(1+1000h) = 1/3
    # decays. Contrast the two amplification factors directly.
    h = 0.1 / 50.0
    explicit_factor = 1.0 + h * (-1000.0)
    implicit_factor = 1.0 / (1.0 - h * (-1000.0))
    assert abs(explicit_factor) >= 1.0          # does not decay
    assert abs(implicit_factor) < 1.0           # decays -> stable


# --------------------------------------------------------------------------- #
# Accuracy on a smooth problem: y' = y, y0 = 1, [0, 1]. Exact y(1) = e.
# --------------------------------------------------------------------------- #


def test_accuracy_smooth_growth():
    f = lambda t, y: [y[0]]
    e = math.e

    _, ys_be = backward_euler(f, 0.0, [1.0], 1.0, n=100)
    _, ys_tr = implicit_trapezoid(f, 0.0, [1.0], 1.0, n=100)
    _, ys_bdf = bdf2(f, 0.0, [1.0], 1.0, n=100)

    y_be = ys_be[-1][0]
    y_tr = ys_tr[-1][0]
    y_bdf = ys_bdf[-1][0]

    assert y_tr == pytest.approx(e, abs=1e-3)
    assert y_bdf == pytest.approx(e, abs=1e-3)

    # Trapezoid (2nd order) is more accurate than backward Euler (1st order).
    assert abs(y_tr - e) < abs(y_be - e)


# --------------------------------------------------------------------------- #
# Decay: y' = -2 y, y0 = 1, [0, 2]. Exact y(2) = exp(-4) ~= 0.0183.
# --------------------------------------------------------------------------- #


def test_decay_all_methods():
    f = lambda t, y: [-2.0 * y[0]]
    target = math.exp(-4.0)

    for solver in (backward_euler, implicit_trapezoid, bdf2):
        _, ys = solver(f, 0.0, [1.0], 2.0, n=100)
        assert ys[-1][0] == pytest.approx(target, abs=1e-2)


# --------------------------------------------------------------------------- #
# Classic stiff linear system:
#   y1' =  998 y1 + 1998 y2
#   y2' = -999 y1 - 1999 y2
# Just assert it stays bounded and finite over [0, 1] with bdf2.
# --------------------------------------------------------------------------- #


def test_stiff_system_bounded():
    def f(t, y):
        return [
            998.0 * y[0] + 1998.0 * y[1],
            -999.0 * y[0] - 1999.0 * y[1],
        ]

    ts, ys = bdf2(f, 0.0, [1.0, 0.0], 1.0, n=100)
    assert len(ts) == 101
    for y in ys:
        for comp in y:
            assert math.isfinite(comp)
            assert abs(comp) < 1e6


# --------------------------------------------------------------------------- #
# Dispatch.
# --------------------------------------------------------------------------- #


def test_solve_stiff_dispatch():
    f = lambda t, y: [-2.0 * y[0]]
    target = math.exp(-4.0)
    for method in ("backward_euler", "implicit_trapezoid", "bdf2"):
        _, ys = solve_stiff(f, (0.0, 2.0), [1.0], method=method, n=100)
        assert ys[-1][0] == pytest.approx(target, abs=1e-2)


def test_solve_stiff_unknown_method():
    f = lambda t, y: [y[0]]
    with pytest.raises(StiffODEError):
        solve_stiff(f, (0.0, 1.0), [1.0], method="nope")


# --------------------------------------------------------------------------- #
# Error paths.
# --------------------------------------------------------------------------- #


def test_n_too_small_raises():
    f = lambda t, y: [y[0]]
    for solver in (backward_euler, implicit_trapezoid, bdf2):
        with pytest.raises(StiffODEError):
            solver(f, 0.0, [1.0], 1.0, n=0)


def test_empty_y0_raises():
    f = lambda t, y: []
    for solver in (backward_euler, implicit_trapezoid, bdf2):
        with pytest.raises(StiffODEError):
            solver(f, 0.0, [], 1.0, n=10)


def test_wrong_length_derivative_raises():
    # f returns a 2-vector for a 1-dim state.
    f = lambda t, y: [y[0], 0.0]
    for solver in (backward_euler, implicit_trapezoid, bdf2):
        with pytest.raises(StiffODEError):
            solver(f, 0.0, [1.0], 1.0, n=10)


def test_solve_linear_singular_raises():
    A = [[1.0, 2.0], [2.0, 4.0]]   # second row is 2x the first -> singular
    b = [1.0, 2.0]
    with pytest.raises(StiffODEError):
        _solve_linear(A, b)


# --------------------------------------------------------------------------- #
# Helper sanity checks.
# --------------------------------------------------------------------------- #


def test_solve_linear_basic():
    A = [[2.0, 1.0], [1.0, 3.0]]
    b = [3.0, 5.0]
    x = _solve_linear(A, b)
    # 2x + y = 3 ; x + 3y = 5  ->  x = 0.8, y = 1.4
    assert x[0] == pytest.approx(0.8)
    assert x[1] == pytest.approx(1.4)


def test_jacobian_linear_system():
    # f(y) = A y  ->  Jacobian is A itself.
    A = [[1.0, 2.0], [3.0, 4.0]]

    def f(t, y):
        return [
            A[0][0] * y[0] + A[0][1] * y[1],
            A[1][0] * y[0] + A[1][1] * y[1],
        ]

    jac = _jacobian(f, 0.0, [1.0, 1.0])
    for i in range(2):
        for j in range(2):
            assert jac[i][j] == pytest.approx(A[i][j], abs=1e-4)
