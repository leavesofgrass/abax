"""Tests for :mod:`abax.core.science.ode` ODE solvers."""

from __future__ import annotations

import math

import pytest

from abax.core.science.ode import ODEError, euler, rk4, rk45, solve


def _exp_growth(t, y):
    # dy/dt = y  ->  y(t) = y0 * e^t
    return [y[0]]


def _decay(t, y):
    # dy/dt = -2y  ->  y(t) = y0 * e^(-2t)
    return [-2.0 * y[0]]


def _harmonic(t, y):
    # y1' = y2, y2' = -y1  ->  (sin t, cos t) for y0 = (0, 1)
    return [y[1], -y[0]]


def test_rk4_exponential_growth():
    ts, ys = rk4(_exp_growth, 0.0, [1.0], 1.0, n=100)
    assert ys[-1][0] == pytest.approx(math.e, abs=1e-5)
    assert len(ts) == len(ys) == 101


def test_euler_exponential_ballpark():
    ts, ys = euler(_exp_growth, 0.0, [1.0], 1.0, n=1000)
    assert ys[-1][0] == pytest.approx(math.e, abs=1e-2)
    assert ys[-1][0] == pytest.approx(2.70, abs=2e-2)


def test_rk45_exponential_growth():
    tol = 1e-6
    ts, ys = rk45(_exp_growth, 0.0, [1.0], 1.0, tol=tol)
    assert ts[-1] == pytest.approx(1.0)
    assert ys[-1][0] == pytest.approx(math.e, abs=tol)
    assert len(ts) == len(ys)


def test_rk4_decay():
    ts, ys = rk4(_decay, 0.0, [1.0], 2.0, n=100)
    assert ys[-1][0] == pytest.approx(math.exp(-4.0), abs=1e-5)


def test_rk4_harmonic_system():
    ts, ys = rk4(_harmonic, 0.0, [0.0, 1.0], math.pi / 2.0, n=200)
    assert ys[-1][0] == pytest.approx(1.0, abs=1e-4)
    assert ys[-1][1] == pytest.approx(0.0, abs=1e-4)
    assert len(ts) == len(ys)
    for state in ys:
        assert len(state) == 2


def test_solve_dispatch_rk4():
    a = solve(_exp_growth, (0.0, 1.0), [1.0], method="rk4", n=100)
    b = rk4(_exp_growth, 0.0, [1.0], 1.0, n=100)
    assert a == b


def test_solve_dispatch_euler():
    a = solve(_exp_growth, (0.0, 1.0), [1.0], method="euler", n=50)
    b = euler(_exp_growth, 0.0, [1.0], 1.0, n=50)
    assert a == b


def test_solve_dispatch_rk45():
    a = solve(_exp_growth, (0.0, 1.0), [1.0], method="rk45", tol=1e-6)
    b = rk45(_exp_growth, 0.0, [1.0], 1.0, tol=1e-6)
    assert a == b


def test_solve_unknown_method():
    with pytest.raises(ODEError):
        solve(_exp_growth, (0.0, 1.0), [1.0], method="bogus")


def test_euler_bad_n():
    with pytest.raises(ODEError):
        euler(_exp_growth, 0.0, [1.0], 1.0, n=0)


def test_rk4_bad_n():
    with pytest.raises(ODEError):
        rk4(_exp_growth, 0.0, [1.0], 1.0, n=0)


def test_empty_y0():
    with pytest.raises(ODEError):
        euler(_exp_growth, 0.0, [], 1.0, n=10)
    with pytest.raises(ODEError):
        rk4(_exp_growth, 0.0, [], 1.0, n=10)
    with pytest.raises(ODEError):
        rk45(_exp_growth, 0.0, [], 1.0)


def test_wrong_length_derivative():
    def bad(t, y):
        return [y[0], 0.0]  # returns length 2 for a length-1 state

    with pytest.raises(ODEError):
        euler(bad, 0.0, [1.0], 1.0, n=10)
    with pytest.raises(ODEError):
        rk4(bad, 0.0, [1.0], 1.0, n=10)
    with pytest.raises(ODEError):
        rk45(bad, 0.0, [1.0], 1.0)


def test_rk45_endpoint_and_backwards():
    # Forwards lands exactly on t1.
    ts, ys = rk45(_decay, 0.0, [1.0], 2.0, tol=1e-7)
    assert ts[-1] == pytest.approx(2.0)
    assert ys[-1][0] == pytest.approx(math.exp(-4.0), abs=1e-5)
    # Backwards integration is allowed (t1 < t0).
    ts, ys = rk45(_exp_growth, 1.0, [math.e], 0.0, tol=1e-7)
    assert ts[-1] == pytest.approx(0.0)
    assert ys[-1][0] == pytest.approx(1.0, abs=1e-5)


def test_zero_interval_single_point():
    ts, ys = rk45(_exp_growth, 0.0, [1.0], 0.0)
    assert ts == [0.0]
    assert ys == [[1.0]]
