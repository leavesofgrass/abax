"""Least-squares regression — the spreadsheet trend/forecast/linest family.

Everything is implemented by hand with the standard library only (``math``,
no numpy): simple linear regression solves the closed-form normal equations,
and polynomial regression solves the ``(degree+1)`` normal equations with
Gaussian elimination and partial pivoting. Intended for spreadsheet-scale
data — numerically reasonable but kept simple.

Public surface mirrors familiar spreadsheet functions:

* :func:`linregress`  -> slope, intercept, r, r2, stderr, n
* :func:`slope` / :func:`intercept` / :func:`rsq` / :func:`correl`
* :func:`forecast` / :func:`trend`  -> linear prediction at new x values
* :func:`polyfit` / :func:`polyval` -> polynomial fit and evaluation

Pure stdlib → core.
"""

from __future__ import annotations

import math


class RegressionError(Exception):
    """Raised when a regression cannot be computed (bad input or singular)."""


def _check_pair(xs: list[float], ys: list[float]) -> int:
    """Validate paired samples; return ``n``."""
    if len(xs) != len(ys):
        raise RegressionError("xs and ys must have the same length")
    n = len(xs)
    if n < 2:
        raise RegressionError("need at least two data points")
    return n


def _solve(A: list[list[float]], b: list[float]) -> list[float]:
    """Solve the ``n x n`` system ``A x = b`` by Gaussian elimination.

    Uses partial pivoting for stability. Raises :class:`RegressionError` if the
    matrix is (near-)singular, i.e. the best pivot is ~0.
    """
    n = len(b)
    # Work on copies so the caller's data is untouched.
    m = [list(row) + [b[i]] for i, row in enumerate(A)]

    for col in range(n):
        # Partial pivot: pick the row with the largest magnitude in this column.
        pivot_row = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot_row][col]) < 1e-12:
            raise RegressionError("singular matrix")
        m[col], m[pivot_row] = m[pivot_row], m[col]

        pivot = m[col][col]
        for r in range(col + 1, n):
            factor = m[r][col] / pivot
            if factor == 0.0:
                continue
            for c in range(col, n + 1):
                m[r][c] -= factor * m[col][c]

    # Back-substitution.
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        total = m[i][n]
        for c in range(i + 1, n):
            total -= m[i][c] * x[c]
        x[i] = total / m[i][i]
    return x


def linregress(xs: list[float], ys: list[float]) -> dict:
    """Simple linear regression ``y = intercept + slope * x`` by least squares.

    Returns a dict with ``slope``, ``intercept``, ``r`` (Pearson correlation),
    ``r2``, ``stderr`` (standard error of the slope) and ``n``.

    Raises :class:`RegressionError` if the lengths differ, ``n < 2`` or ``x``
    has zero variance (a vertical line has no slope).
    """
    n = _check_pair(xs, ys)

    mean_x = math.fsum(xs) / n
    mean_y = math.fsum(ys) / n

    sxx = math.fsum((x - mean_x) ** 2 for x in xs)
    syy = math.fsum((y - mean_y) ** 2 for y in ys)
    sxy = math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))

    if sxx == 0.0:
        raise RegressionError("x has zero variance")

    b = sxy / sxx
    a = mean_y - b * mean_x

    # Pearson r; r2 from it. Guard a constant y (then r is defined as 0).
    if syy == 0.0:
        r = 0.0
    else:
        r = sxy / math.sqrt(sxx * syy)
        r = max(-1.0, min(1.0, r))
    r2 = r * r

    # Standard error of the slope: sqrt( (SSE / (n - 2)) / Sxx ).
    if n > 2:
        sse = max(0.0, syy - b * sxy)
        stderr = math.sqrt((sse / (n - 2)) / sxx)
    else:
        stderr = 0.0

    return {
        "slope": b,
        "intercept": a,
        "r": r,
        "r2": r2,
        "stderr": stderr,
        "n": n,
    }


def slope(xs: list[float], ys: list[float]) -> float:
    """Slope ``b`` of the least-squares line."""
    return linregress(xs, ys)["slope"]


def intercept(xs: list[float], ys: list[float]) -> float:
    """Intercept ``a`` of the least-squares line."""
    return linregress(xs, ys)["intercept"]


def rsq(xs: list[float], ys: list[float]) -> float:
    """Coefficient of determination ``r**2``."""
    return linregress(xs, ys)["r2"]


def correl(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient ``r``."""
    return linregress(xs, ys)["r"]


def forecast(x: float, xs: list[float], ys: list[float]) -> float:
    """Predicted ``y`` at ``x`` from the simple linear fit."""
    fit = linregress(xs, ys)
    return fit["intercept"] + fit["slope"] * x


def trend(xs: list[float], ys: list[float], new_xs: list[float]) -> list[float]:
    """Linear forecast for each value in ``new_xs``."""
    fit = linregress(xs, ys)
    a, b = fit["intercept"], fit["slope"]
    return [a + b * x for x in new_xs]


def polyfit(xs: list[float], ys: list[float], degree: int) -> list[float]:
    """Least-squares polynomial fit of the given ``degree``.

    Returns coefficients ``[c0, c1, ..., c_degree]`` with ``c0`` the constant
    term, solving the ``(degree + 1)`` normal equations via Gaussian
    elimination with partial pivoting.

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
    # Precompute the power sums S_k = sum(x**k) for k in 0..2*degree.
    power_sums = [math.fsum(x ** k for x in xs) for k in range(2 * degree + 1)]
    # Right-hand side: T_k = sum(y * x**k) for k in 0..degree.
    rhs = [math.fsum(y * (x ** k) for x, y in zip(xs, ys)) for k in range(cols)]

    A = [[power_sums[i + j] for j in range(cols)] for i in range(cols)]
    return _solve(A, rhs)


def polyval(coeffs: list[float], x: float) -> float:
    """Evaluate the polynomial ``c0 + c1*x + ... + cn*x**n`` at ``x``."""
    # Horner's method, ascending coefficients -> iterate high to low.
    result = 0.0
    for c in reversed(coeffs):
        result = result * x + c
    return result
