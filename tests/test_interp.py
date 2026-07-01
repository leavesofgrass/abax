"""Tests for :mod:`abax.core.science.interp` (stdlib-only 1-D interpolation)."""

from __future__ import annotations

import pytest

from abax.core.science.interp import (
    InterpError,
    cubic_spline,
    cubic_spline_coeffs,
    lagrange,
    linear,
    nearest,
    resample,
)

TOL = 1e-9


def test_linear_midpoint():
    assert linear(1.5, [1, 2, 3], [10, 20, 30]) == pytest.approx(15, abs=TOL)


def test_linear_clamp_below():
    assert linear(0, [1, 2, 3], [10, 20, 30]) == pytest.approx(10, abs=TOL)


def test_linear_clamp_above():
    assert linear(9, [1, 2, 3], [10, 20, 30]) == pytest.approx(30, abs=TOL)


def test_linear_on_node():
    assert linear(2, [1, 2, 3], [10, 20, 30]) == pytest.approx(20, abs=TOL)


def test_nearest_rounds_down():
    assert nearest(2.4, [1, 2, 3], [10, 20, 30]) == pytest.approx(20, abs=TOL)


def test_nearest_rounds_up():
    assert nearest(2.6, [1, 2, 3], [10, 20, 30]) == pytest.approx(30, abs=TOL)


def test_nearest_clamps():
    assert nearest(-5, [1, 2, 3], [10, 20, 30]) == pytest.approx(10, abs=TOL)
    assert nearest(100, [1, 2, 3], [10, 20, 30]) == pytest.approx(30, abs=TOL)


def test_lagrange_reproduces_nodes():
    xs, ys = [0, 1, 2], [0, 1, 4]  # y = x**2
    for x in (0, 1, 2):
        assert lagrange(x, xs, ys) == pytest.approx(x * x, abs=TOL)


def test_lagrange_extrapolates_polynomial():
    xs, ys = [0, 1, 2], [0, 1, 4]  # y = x**2
    assert lagrange(3, xs, ys) == pytest.approx(9, abs=TOL)


def test_cubic_spline_passes_through_nodes():
    cases = [
        ([0, 1, 2, 3], [0, 1, 8, 27]),
        ([1, 2, 4, 7, 9], [3, 1, 4, 1, 5]),
        ([0.0, 0.5, 1.5, 2.0], [-1.0, 2.0, 0.5, 3.0]),
    ]
    for xs, ys in cases:
        for i, xi in enumerate(xs):
            assert cubic_spline(xi, xs, ys) == pytest.approx(ys[i], abs=TOL)


def test_cubic_spline_monotone_between_nodes():
    xs, ys = [0, 1, 2, 3], [0, 1, 8, 27]
    samples = [cubic_spline(x / 10.0, xs, ys) for x in range(0, 31)]
    for prev, cur in zip(samples, samples[1:]):
        assert cur >= prev - TOL


def test_cubic_spline_coeffs_count():
    xs, ys = [0, 1, 2, 3], [0, 1, 8, 27]
    coeffs = cubic_spline_coeffs(xs, ys)
    assert len(coeffs) == len(xs) - 1


def test_cubic_spline_coeffs_natural_bc():
    # Natural BC: second derivative S''(x0) = 2*c0 = 0 at the left end, and
    # S''(x_last) = 0 at the right end. c == m/2, so m[0] == m[n] == 0.
    xs, ys = [0, 1, 2, 3], [0, 1, 8, 27]
    coeffs = cubic_spline_coeffs(xs, ys)
    # left end curvature contribution
    assert coeffs[0][2] == pytest.approx(0.0, abs=TOL)
    # right end: S''(x_last) = 2*c_last + 6*d_last*h_last
    a, b, c, d = coeffs[-1]
    h = xs[-1] - xs[-2]
    assert 2.0 * c + 6.0 * d * h == pytest.approx(0.0, abs=TOL)


def test_resample_linear():
    out = resample([1, 2, 3], [10, 20, 30], [1.5, 2.5])
    assert out[0] == pytest.approx(15, abs=TOL)
    assert out[1] == pytest.approx(25, abs=TOL)


def test_resample_spline_through_nodes():
    xs, ys = [0, 1, 2, 3], [0, 1, 8, 27]
    out = resample(xs, ys, xs, method="spline")
    for got, want in zip(out, ys):
        assert got == pytest.approx(want, abs=TOL)


def test_resample_nearest_and_lagrange():
    assert resample([1, 2, 3], [10, 20, 30], [2.6], method="nearest")[0] == pytest.approx(
        30, abs=TOL
    )
    assert resample([0, 1, 2], [0, 1, 4], [3], method="lagrange")[0] == pytest.approx(
        9, abs=TOL
    )


def test_resample_unknown_method():
    with pytest.raises(InterpError):
        resample([1, 2, 3], [10, 20, 30], [1.5], method="quadratic")


def test_bad_length_mismatch():
    with pytest.raises(InterpError):
        linear(1.0, [1, 2, 3], [10, 20])


def test_bad_too_few_points():
    with pytest.raises(InterpError):
        linear(1.0, [1], [10])


def test_bad_non_increasing():
    with pytest.raises(InterpError):
        linear(1.0, [1, 1, 2], [10, 20, 30])
    with pytest.raises(InterpError):
        cubic_spline(1.0, [3, 2, 1], [10, 20, 30])
