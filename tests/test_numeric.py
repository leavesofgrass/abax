"""Tests for :mod:`abax.core.science.numeric` (root-finding, integration, derivatives)."""

from __future__ import annotations

import math

import pytest

from abax.core.science.numeric import (
    NumericError,
    bisection,
    derivative,
    integrate,
    newton,
    secant,
    trapz,
)

TOL = 1e-6


# --- bisection ------------------------------------------------------------

def test_bisection_sqrt2():
    assert bisection(lambda x: x * x - 2, 0, 2) == pytest.approx(math.sqrt(2), abs=TOL)


def test_bisection_no_sign_change_raises():
    with pytest.raises(NumericError):
        bisection(lambda x: x * x - 2, 0, 1)


def test_bisection_exact_endpoint():
    assert bisection(lambda x: x - 1, 1, 5) == pytest.approx(1.0, abs=TOL)


# --- newton ---------------------------------------------------------------

def test_newton_sqrt2():
    assert newton(lambda x: x * x - 2, 1.0) == pytest.approx(math.sqrt(2), abs=TOL)


def test_newton_with_analytic_derivative():
    root = newton(lambda x: x * x - 2, 1.0, fprime=lambda x: 2 * x)
    assert root == pytest.approx(math.sqrt(2), abs=TOL)


def test_newton_no_real_root_raises():
    with pytest.raises(NumericError):
        newton(lambda x: x * x + 1, 1.0)


# --- secant ---------------------------------------------------------------

def test_secant_cubic_root():
    root = secant(lambda x: x ** 3 - x - 2, 1, 2)
    assert root == pytest.approx(1.5213797, abs=TOL)
    assert root ** 3 - root - 2 == pytest.approx(0.0, abs=TOL)


def test_secant_zero_denominator_raises():
    with pytest.raises(NumericError):
        secant(lambda x: 5.0, 0.0, 1.0)


# --- integrate ------------------------------------------------------------

def test_integrate_sin_simpson():
    assert integrate(math.sin, 0, math.pi) == pytest.approx(2.0, abs=TOL)


def test_integrate_sin_trapezoid():
    assert integrate(math.sin, 0, math.pi, method="trapezoid") == pytest.approx(
        2.0, abs=1e-5
    )


def test_integrate_xsquared():
    assert integrate(lambda x: x * x, 0, 1) == pytest.approx(1.0 / 3.0, abs=TOL)


def test_integrate_reversed_bounds_negates():
    forward = integrate(lambda x: x * x, 0, 1)
    assert integrate(lambda x: x * x, 1, 0) == pytest.approx(-forward, abs=TOL)


def test_integrate_simpson_odd_n_forced_even():
    assert integrate(lambda x: x * x, 0, 1, n=11) == pytest.approx(1.0 / 3.0, abs=TOL)


def test_integrate_unknown_method_raises():
    with pytest.raises(NumericError):
        integrate(math.sin, 0, 1, method="romberg")


def test_integrate_bad_n_raises():
    with pytest.raises(NumericError):
        integrate(math.sin, 0, 1, n=0)


# --- derivative -----------------------------------------------------------

def test_derivative_quadratic():
    assert derivative(lambda x: x * x, 3) == pytest.approx(6.0, abs=TOL)


def test_derivative_sin():
    assert derivative(math.sin, 0) == pytest.approx(1.0, abs=TOL)


# --- trapz ----------------------------------------------------------------

def test_trapz_sampled():
    # Trapezoidal sum of unit-spaced (0,1,4,9):
    # 0.5*(0+1) + 0.5*(1+4) + 0.5*(4+9) = 0.5 + 2.5 + 6.5 = 9.5
    assert trapz([0, 1, 2, 3], [0, 1, 4, 9]) == pytest.approx(9.5, abs=TOL)


def test_trapz_length_mismatch_raises():
    with pytest.raises(NumericError):
        trapz([0, 1, 2], [0, 1])


def test_trapz_too_short_raises():
    with pytest.raises(NumericError):
        trapz([0], [0])


def test_trapz_non_increasing_raises():
    with pytest.raises(NumericError):
        trapz([0, 2, 1], [0, 1, 2])
