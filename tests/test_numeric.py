"""Tests for :mod:`abax.core.science.numeric` (root-finding, integration, derivatives)."""

from __future__ import annotations

import math

import pytest

from abax.core.science.numeric import (
    NumericError,
    adaptive_simpson,
    bisection,
    derivative,
    integrate,
    newton,
    secant,
    solve_root,
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


# --- solve_root (HP-15C SOLVE) --------------------------------------------

def test_solve_root_sqrt2_bracket():
    root, froot = solve_root(lambda x: x * x - 2, 0, 2)
    assert root == pytest.approx(1.41421356, abs=TOL)
    assert froot == pytest.approx(0.0, abs=TOL)


def test_solve_root_cos_minus_x():
    # cos(x) - x = 0 -> Dottie number ~0.7390851.
    root, froot = solve_root(lambda x: math.cos(x) - x, 0, 1)
    assert root == pytest.approx(0.7390851, abs=TOL)
    assert froot == pytest.approx(0.0, abs=TOL)


def test_solve_root_returns_tuple_with_fvalue():
    result = solve_root(lambda x: x - 3, 0, 10)
    assert isinstance(result, tuple) and len(result) == 2
    root, froot = result
    assert root == pytest.approx(3.0, abs=TOL)
    assert froot == pytest.approx(0.0, abs=TOL)


def test_solve_root_exact_endpoint():
    root, froot = solve_root(lambda x: x - 2, 2, 5)
    assert root == pytest.approx(2.0, abs=TOL)
    assert froot == 0.0


def test_solve_root_single_guess_finds_bracket():
    # Only a guess given; solver must bracket outward and converge.
    root, froot = solve_root(lambda x: x * x - 2, 1.0)
    assert root == pytest.approx(math.sqrt(2), abs=TOL)
    assert froot == pytest.approx(0.0, abs=TOL)


def test_solve_root_single_guess_linear():
    root, froot = solve_root(lambda x: 3 * x - 6, 0.0)
    assert root == pytest.approx(2.0, abs=TOL)
    assert froot == pytest.approx(0.0, abs=TOL)


def test_solve_root_no_sign_change_bracket_raises():
    with pytest.raises(NumericError):
        solve_root(lambda x: x * x + 1, -1, 1)


# --- adaptive_simpson (HP-15C INTEGRATE / ∫) ------------------------------

def test_adaptive_simpson_sin():
    # ∫₀^π sin x dx = 2.
    assert adaptive_simpson(math.sin, 0, math.pi) == pytest.approx(2.0, abs=TOL)


def test_adaptive_simpson_xsquared():
    # ∫₀^1 x² dx = 1/3.
    assert adaptive_simpson(lambda x: x * x, 0, 1) == pytest.approx(1.0 / 3.0, abs=TOL)


def test_adaptive_simpson_exp():
    # ∫₀^1 eˣ dx = e - 1.
    assert adaptive_simpson(math.exp, 0, 1) == pytest.approx(math.e - 1.0, abs=TOL)


def test_adaptive_simpson_reversed_bounds_negates():
    forward = adaptive_simpson(lambda x: x * x, 0, 1)
    assert adaptive_simpson(lambda x: x * x, 1, 0) == pytest.approx(-forward, abs=TOL)


def test_adaptive_simpson_equal_bounds_zero():
    assert adaptive_simpson(math.sin, 1.0, 1.0) == 0.0


def test_integrate_adaptive_method():
    # The adaptive method is reachable through integrate(..., method="adaptive").
    assert integrate(math.sin, 0, math.pi, method="adaptive") == pytest.approx(
        2.0, abs=TOL
    )
    assert integrate(math.exp, 0, 1, method="adaptive") == pytest.approx(
        math.e - 1.0, abs=TOL
    )


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
