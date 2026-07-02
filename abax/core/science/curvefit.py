"""Curve fitting — least-squares model fits over XY data, with R².

Pure standard library (``math`` only, no numpy). Builds on the least-squares
machinery in :mod:`abax.core.science.regression` (the same Gaussian-elimination
solver and Horner evaluation), adding:

* :func:`polyfit`      -> ``(coeffs, r2)`` polynomial of any degree; degree 1
  agrees exactly with the simple linear regression.
* :func:`expfit`       -> ``(a, b, r2)`` for ``y = a * exp(b * x)`` via
  log-linear regression on ``ln(y)`` (requires ``y > 0``).
* :func:`powerfit`     -> ``(a, b, r2)`` for ``y = a * x ** b`` via log-log
  regression (requires ``x > 0`` and ``y > 0``).

Every fit returns its coefficients together with R² computed on the ORIGINAL
``y`` values (not the transformed logs), so the reported goodness-of-fit is
comparable across models.

Pure stdlib → core.
"""

from __future__ import annotations

import math

from .regression import RegressionError, _solve, polyval

__all__ = [
    "RegressionError",
    "polyfit",
    "polyval",
    "expfit",
    "powerfit",
    "r_squared",
]


def _check_pair(xs: list[float], ys: list[float]) -> int:
    """Validate paired samples; return ``n``."""
    if len(xs) != len(ys):
        raise RegressionError("xs and ys must have the same length")
    n = len(xs)
    if n < 2:
        raise RegressionError("need at least two data points")
    return n


def r_squared(ys: list[float], preds: list[float]) -> float:
    """Coefficient of determination ``R²`` for predictions ``preds`` of ``ys``.

    ``R² = 1 - SS_res / SS_tot``. A perfect fit gives ``1.0``; when ``ys`` has
    zero variance (constant), ``R²`` is defined as ``1.0`` for a perfect match
    and ``0.0`` otherwise. Values are not clamped below 0 for poor fits.
    """
    n = len(ys)
    if n == 0:
        raise RegressionError("no data points")
    mean_y = math.fsum(ys) / n
    ss_tot = math.fsum((y - mean_y) ** 2 for y in ys)
    ss_res = math.fsum((y - p) ** 2 for y, p in zip(ys, preds))
    if ss_tot == 0.0:
        return 1.0 if ss_res == 0.0 else 0.0
    return 1.0 - ss_res / ss_tot


def polyfit(xs: list[float], ys: list[float], degree: int) -> tuple[list[float], float]:
    """Least-squares polynomial fit of the given ``degree``.

    Returns ``(coeffs, r2)`` where ``coeffs = [c0, c1, ..., c_degree]`` with
    ``c0`` the constant term, and ``r2`` is the coefficient of determination.
    Solves the ``(degree + 1)`` normal equations by Gaussian elimination with
    partial pivoting. The degree-1 case agrees with simple linear regression.

    Raises :class:`RegressionError` if the lengths differ, ``degree < 0``,
    ``n <= degree`` (under-determined) or the system is singular.
    """
    if len(xs) != len(ys):
        raise RegressionError("xs and ys must have the same length")
    if degree < 0:
        raise RegressionError("degree must be non-negative")
    n = len(xs)
    if n <= degree:
        raise RegressionError("need more data points than the polynomial degree")

    cols = degree + 1
    # Power sums S_k = sum(x**k) for k in 0..2*degree, and T_k = sum(y*x**k).
    power_sums = [math.fsum(x ** k for x in xs) for k in range(2 * degree + 1)]
    rhs = [math.fsum(y * (x ** k) for x, y in zip(xs, ys)) for k in range(cols)]

    A = [[power_sums[i + j] for j in range(cols)] for i in range(cols)]
    coeffs = _solve(A, rhs)

    preds = [polyval(coeffs, x) for x in xs]
    return coeffs, r_squared(ys, preds)


def expfit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Fit ``y = a * exp(b * x)`` by log-linear regression on ``ln(y)``.

    Requires every ``y > 0`` (raises :class:`RegressionError` otherwise). The
    linear fit ``ln(y) = ln(a) + b * x`` recovers ``b`` (the slope) and
    ``a = exp(intercept)``. ``R²`` is computed on the ORIGINAL ``y`` values,
    not the logs.

    Returns ``(a, b, r2)``.
    """
    _check_pair(xs, ys)
    if any(y <= 0.0 for y in ys):
        raise RegressionError("exponential fit requires all y > 0")

    log_ys = [math.log(y) for y in ys]
    (intercept, slope), _r2_log = polyfit(list(xs), log_ys, 1)
    a = math.exp(intercept)
    b = slope

    preds = [a * math.exp(b * x) for x in xs]
    return a, b, r_squared(ys, preds)


def powerfit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Fit ``y = a * x ** b`` by log-log regression.

    Requires every ``x > 0`` and ``y > 0`` (raises :class:`RegressionError`
    otherwise). The linear fit ``ln(y) = ln(a) + b * ln(x)`` recovers ``b`` and
    ``a = exp(intercept)``. ``R²`` is computed on the ORIGINAL ``y`` values.

    Returns ``(a, b, r2)``.
    """
    _check_pair(xs, ys)
    if any(x <= 0.0 for x in xs):
        raise RegressionError("power fit requires all x > 0")
    if any(y <= 0.0 for y in ys):
        raise RegressionError("power fit requires all y > 0")

    log_xs = [math.log(x) for x in xs]
    log_ys = [math.log(y) for y in ys]
    (intercept, slope), _r2_log = polyfit(log_xs, log_ys, 1)
    a = math.exp(intercept)
    b = slope

    preds = [a * (x ** b) for x in xs]
    return a, b, r_squared(ys, preds)
