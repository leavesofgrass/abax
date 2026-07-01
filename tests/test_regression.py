"""Least-squares regression (linregress / polyfit / trend / forecast)."""

from __future__ import annotations

import pytest

from abax.core.science.regression import (
    RegressionError,
    correl,
    forecast,
    intercept,
    linregress,
    polyfit,
    polyval,
    rsq,
    slope,
    trend,
)


def test_perfect_line():
    xs = [0.0, 1.0, 2.0, 3.0, 4.0]
    ys = [2.0 * x + 1.0 for x in xs]
    fit = linregress(xs, ys)
    assert fit["slope"] == pytest.approx(2.0)
    assert fit["intercept"] == pytest.approx(1.0)
    assert fit["r2"] == pytest.approx(1.0)
    assert fit["r"] == pytest.approx(1.0)
    assert fit["n"] == 5
    assert fit["stderr"] == pytest.approx(0.0, abs=1e-9)


def test_helper_functions_agree():
    xs = [0.0, 1.0, 2.0, 3.0, 4.0]
    ys = [2.0 * x + 1.0 for x in xs]
    assert slope(xs, ys) == pytest.approx(2.0)
    assert intercept(xs, ys) == pytest.approx(1.0)
    assert rsq(xs, ys) == pytest.approx(1.0)
    assert correl(xs, ys) == pytest.approx(1.0)


def test_forecast_matches_line():
    xs = [0.0, 1.0, 2.0, 3.0, 4.0]
    ys = [2.0 * x + 1.0 for x in xs]
    assert forecast(10.0, xs, ys) == pytest.approx(21.0)
    assert forecast(-5.0, xs, ys) == pytest.approx(-9.0)


def test_noisy_set_sensible():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    ys = [2.1, 3.9, 6.2, 7.8, 10.3, 11.9]  # roughly y = 2x
    fit = linregress(xs, ys)
    assert fit["slope"] == pytest.approx(2.0, abs=0.2)
    assert 0.0 < fit["r2"] < 1.0
    assert fit["stderr"] > 0.0


def test_correl_perfect_and_anti():
    xs = [1.0, 2.0, 3.0, 4.0]
    assert correl(xs, [2.0, 4.0, 6.0, 8.0]) == pytest.approx(1.0)
    assert correl(xs, [8.0, 6.0, 4.0, 2.0]) == pytest.approx(-1.0)


def test_polyfit_quadratic():
    xs = [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0]
    ys = [x * x for x in xs]
    coeffs = polyfit(xs, ys, 2)
    assert coeffs[0] == pytest.approx(0.0, abs=1e-9)
    assert coeffs[1] == pytest.approx(0.0, abs=1e-9)
    assert coeffs[2] == pytest.approx(1.0)
    for x, y in zip(xs, ys):
        assert polyval(coeffs, x) == pytest.approx(y)


def test_polyfit_degree1_matches_linregress():
    xs = [1.0, 2.0, 4.0, 7.0, 9.0]
    ys = [2.3, 4.1, 7.9, 14.2, 18.6]
    coeffs = polyfit(xs, ys, 1)
    fit = linregress(xs, ys)
    assert coeffs[0] == pytest.approx(fit["intercept"])
    assert coeffs[1] == pytest.approx(fit["slope"])


def test_polyval_basic():
    # 1 + 2x + 3x^2 at x=2 -> 1 + 4 + 12 = 17
    assert polyval([1.0, 2.0, 3.0], 2.0) == pytest.approx(17.0)
    assert polyval([5.0], 99.0) == pytest.approx(5.0)


def test_trend_extrapolates():
    xs = [0.0, 1.0, 2.0]
    ys = [1.0, 3.0, 5.0]  # y = 2x + 1
    assert trend(xs, ys, [3.0, 4.0, 10.0]) == pytest.approx([7.0, 9.0, 21.0])


def test_errors_mismatched_lengths():
    with pytest.raises(RegressionError):
        linregress([1.0, 2.0], [1.0])
    with pytest.raises(RegressionError):
        polyfit([1.0, 2.0], [1.0], 1)


def test_errors_too_few_points():
    with pytest.raises(RegressionError):
        linregress([1.0], [2.0])


def test_errors_zero_variance_x():
    with pytest.raises(RegressionError):
        linregress([3.0, 3.0, 3.0], [1.0, 2.0, 3.0])


def test_errors_over_degree():
    with pytest.raises(RegressionError):
        polyfit([1.0, 2.0], [1.0, 2.0], 5)


def test_errors_singular_polyfit():
    # All x equal -> normal-equations matrix is singular for degree >= 1.
    with pytest.raises(RegressionError):
        polyfit([2.0, 2.0, 2.0, 2.0], [1.0, 2.0, 3.0, 4.0], 1)
