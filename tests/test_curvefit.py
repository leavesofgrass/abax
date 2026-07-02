"""Curve fitting — polynomial / exponential / power least-squares fits with R²."""

from __future__ import annotations

import math

import pytest

from abax.core.science.curvefit import (
    RegressionError,
    expfit,
    polyfit,
    polyval,
    powerfit,
    r_squared,
)
from abax.core.science.regression import linregress

TOL = 1e-6


def test_polyfit_line():
    coeffs, r2 = polyfit([0, 1, 2, 3], [1, 3, 5, 7], 1)
    # coeffs are [intercept, slope]
    assert coeffs[0] == pytest.approx(1.0, abs=TOL)  # intercept
    assert coeffs[1] == pytest.approx(2.0, abs=TOL)  # slope
    assert r2 == pytest.approx(1.0, abs=TOL)


def test_polyfit_quadratic():
    coeffs, r2 = polyfit([-2, -1, 0, 1, 2], [4, 1, 0, 1, 4], 2)
    assert coeffs[0] == pytest.approx(0.0, abs=TOL)
    assert coeffs[1] == pytest.approx(0.0, abs=TOL)
    assert coeffs[2] == pytest.approx(1.0, abs=TOL)
    assert r2 == pytest.approx(1.0, abs=TOL)


def test_polyfit_degree1_agrees_with_linregress():
    xs = [1.0, 2.0, 4.0, 7.0, 9.0]
    ys = [2.3, 4.1, 7.9, 14.2, 18.6]
    coeffs, r2 = polyfit(xs, ys, 1)
    fit = linregress(xs, ys)
    assert coeffs[0] == pytest.approx(fit["intercept"], abs=TOL)
    assert coeffs[1] == pytest.approx(fit["slope"], abs=TOL)
    assert r2 == pytest.approx(fit["r2"], abs=TOL)


def test_polyval_reconstructs():
    coeffs, _ = polyfit([-2, -1, 0, 1, 2], [4, 1, 0, 1, 4], 2)
    for x, y in zip([-2, -1, 0, 1, 2], [4, 1, 0, 1, 4]):
        assert polyval(coeffs, x) == pytest.approx(y, abs=1e-5)


def test_expfit_recovers_exact_model():
    xs = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [3.0 * math.exp(0.5 * x) for x in xs]
    a, b, r2 = expfit(xs, ys)
    assert a == pytest.approx(3.0, abs=TOL)
    assert b == pytest.approx(0.5, abs=TOL)
    assert r2 == pytest.approx(1.0, abs=TOL)


def test_expfit_r2_on_original_y():
    # R² is computed on the ORIGINAL y, not the logs: perfect model -> 1.0.
    xs = [0.0, 1.0, 2.0, 3.0]
    ys = [2.0 * math.exp(-0.3 * x) for x in xs]
    _a, _b, r2 = expfit(xs, ys)
    assert r2 == pytest.approx(1.0, abs=TOL)


def test_expfit_requires_positive_y():
    with pytest.raises(RegressionError):
        expfit([0.0, 1.0, 2.0], [1.0, -2.0, 3.0])
    with pytest.raises(RegressionError):
        expfit([0.0, 1.0, 2.0], [1.0, 0.0, 3.0])


def test_powerfit_recovers_exact_model():
    a_true, b_true = 2.5, 1.75
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [a_true * (x ** b_true) for x in xs]
    a, b, r2 = powerfit(xs, ys)
    assert a == pytest.approx(a_true, abs=TOL)
    assert b == pytest.approx(b_true, abs=TOL)
    assert r2 == pytest.approx(1.0, abs=TOL)


def test_powerfit_requires_positive_x_and_y():
    with pytest.raises(RegressionError):
        powerfit([0.0, 1.0, 2.0], [1.0, 2.0, 3.0])   # x has a zero
    with pytest.raises(RegressionError):
        powerfit([1.0, 2.0, 3.0], [-1.0, 2.0, 3.0])  # y has a negative


def test_r_squared_helper():
    assert r_squared([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)
    # constant y with perfect match -> 1.0
    assert r_squared([5.0, 5.0], [5.0, 5.0]) == pytest.approx(1.0)
    assert r_squared([5.0, 5.0], [4.0, 6.0]) == pytest.approx(0.0)


def test_errors_mismatched_and_short():
    with pytest.raises(RegressionError):
        polyfit([1.0, 2.0], [1.0], 1)
    with pytest.raises(RegressionError):
        polyfit([1.0, 2.0], [1.0, 2.0], 5)
    with pytest.raises(RegressionError):
        expfit([1.0], [2.0])
