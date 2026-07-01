"""Pure-Python 1-D interpolation: linear, nearest, Lagrange, natural cubic spline.

A small, dependency-free interpolation toolkit for use inside abax. Every
routine takes two parallel lists ``xs`` and ``ys`` with ``xs`` *strictly
increasing* and ``len(xs) == len(ys) >= 2``; otherwise :class:`InterpError` is
raised (validated once in :func:`_validate`). Everything works in IEEE doubles
via the stdlib :mod:`math` and :mod:`bisect` modules only.

Methods: :func:`linear` (piecewise-linear, clamped outside the data range),
:func:`nearest` (nearest-neighbour), :func:`lagrange` (the interpolating
polynomial through all nodes), and the natural cubic spline pair
:func:`cubic_spline_coeffs` / :func:`cubic_spline`. :func:`resample` maps ``ys``
onto a new set of abscissae using any of the named methods.
"""

from __future__ import annotations

import bisect


class InterpError(Exception):
    """Raised when an interpolation routine cannot produce a valid result."""


def _validate(xs: list[float], ys: list[float]) -> None:
    """Check the shared contract for ``xs``/``ys``.

    Both lists must have equal length of at least two, and ``xs`` must be
    strictly increasing; otherwise :class:`InterpError` is raised.
    """
    if len(xs) != len(ys):
        raise InterpError("xs and ys must have equal length")
    if len(xs) < 2:
        raise InterpError("need at least two points")
    for i in range(1, len(xs)):
        if xs[i] <= xs[i - 1]:
            raise InterpError("xs must be strictly increasing")


def linear(x: float, xs: list[float], ys: list[float]) -> float:
    """Piecewise-linear interpolation of ``ys`` at ``x``.

    For ``x`` outside ``[xs[0], xs[-1]]`` the nearest endpoint value is returned
    (clamping, not linear extrapolation).
    """
    _validate(xs, ys)
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect.bisect_right(xs, x) - 1
    if i >= len(xs) - 1:
        i = len(xs) - 2
    x0, x1 = xs[i], xs[i + 1]
    y0, y1 = ys[i], ys[i + 1]
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def nearest(x: float, xs: list[float], ys: list[float]) -> float:
    """Return the value of the nearest node to ``x`` (nearest-neighbour)."""
    _validate(xs, ys)
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect.bisect_right(xs, x) - 1
    x0, x1 = xs[i], xs[i + 1]
    return ys[i] if (x - x0) <= (x1 - x) else ys[i + 1]


def lagrange(x: float, xs: list[float], ys: list[float]) -> float:
    """Evaluate the Lagrange interpolating polynomial through all nodes at ``x``."""
    _validate(xs, ys)
    n = len(xs)
    total = 0.0
    for i in range(n):
        term = ys[i]
        xi = xs[i]
        for j in range(n):
            if j != i:
                term *= (x - xs[j]) / (xi - xs[j])
        total += term
    return total


def cubic_spline_coeffs(
    xs: list[float], ys: list[float]
) -> list[tuple[float, float, float, float]]:
    """Return natural-cubic-spline coefficients, one ``(a, b, c, d)`` per interval.

    For interval ``i`` on ``[xs[i], xs[i+1]]`` the spline is
    ``S_i(x) = a + b*(x-xs[i]) + c*(x-xs[i])**2 + d*(x-xs[i])**3``. The list has
    ``len(xs) - 1`` entries. Natural boundary conditions (second derivative zero
    at both ends) are imposed; the moments are found by a Thomas-algorithm solve
    of the tridiagonal system.
    """
    _validate(xs, ys)
    n = len(xs) - 1  # number of intervals

    h = [xs[i + 1] - xs[i] for i in range(n)]

    # Build the tridiagonal system for the second derivatives (moments) m[0..n].
    # Natural BCs fix m[0] = m[n] = 0, so solve for the interior moments.
    if n == 1:
        # Single interval: straight line, no curvature.
        m = [0.0, 0.0]
    else:
        # Interior unknowns m[1..n-1]; system size = n-1.
        size = n - 1
        sub = [0.0] * size   # sub-diagonal
        diag = [0.0] * size  # main diagonal
        sup = [0.0] * size   # super-diagonal
        rhs = [0.0] * size
        for k in range(1, n):
            idx = k - 1
            sub[idx] = h[k - 1]
            diag[idx] = 2.0 * (h[k - 1] + h[k])
            sup[idx] = h[k]
            rhs[idx] = 6.0 * (
                (ys[k + 1] - ys[k]) / h[k] - (ys[k] - ys[k - 1]) / h[k - 1]
            )

        # Thomas algorithm (forward elimination + back substitution).
        for idx in range(1, size):
            w = sub[idx] / diag[idx - 1]
            diag[idx] -= w * sup[idx - 1]
            rhs[idx] -= w * rhs[idx - 1]
        interior = [0.0] * size
        interior[size - 1] = rhs[size - 1] / diag[size - 1]
        for idx in range(size - 2, -1, -1):
            interior[idx] = (rhs[idx] - sup[idx] * interior[idx + 1]) / diag[idx]

        m = [0.0] + interior + [0.0]

    coeffs: list[tuple[float, float, float, float]] = []
    for i in range(n):
        a = ys[i]
        b = (ys[i + 1] - ys[i]) / h[i] - h[i] * (2.0 * m[i] + m[i + 1]) / 6.0
        c = m[i] / 2.0
        d = (m[i + 1] - m[i]) / (6.0 * h[i])
        coeffs.append((a, b, c, d))
    return coeffs


def cubic_spline(x: float, xs: list[float], ys: list[float]) -> float:
    """Evaluate the natural cubic spline at ``x`` (``x`` is clamped to the range)."""
    _validate(xs, ys)
    coeffs = cubic_spline_coeffs(xs, ys)
    return _eval_spline(x, xs, coeffs)


def _eval_spline(
    x: float,
    xs: list[float],
    coeffs: list[tuple[float, float, float, float]],
) -> float:
    """Evaluate precomputed spline ``coeffs`` at ``x``, clamping to ``[xs0, xs-1]``."""
    if x <= xs[0]:
        i = 0
        x = xs[0]
    elif x >= xs[-1]:
        i = len(xs) - 2
        x = xs[-1]
    else:
        i = bisect.bisect_right(xs, x) - 1
        if i >= len(xs) - 1:
            i = len(xs) - 2
    a, b, c, d = coeffs[i]
    dx = x - xs[i]
    return a + dx * (b + dx * (c + dx * d))


def resample(
    xs: list[float],
    ys: list[float],
    new_xs: list[float],
    method: str = "linear",
) -> list[float]:
    """Interpolate ``ys`` onto ``new_xs`` using ``method``.

    ``method`` is one of ``"linear"``, ``"nearest"``, ``"lagrange"`` or
    ``"spline"``; an unknown method raises :class:`InterpError`. For ``"spline"``
    the coefficients are computed once and reused across every output point.
    """
    _validate(xs, ys)
    if method == "linear":
        return [linear(x, xs, ys) for x in new_xs]
    if method == "nearest":
        return [nearest(x, xs, ys) for x in new_xs]
    if method == "lagrange":
        return [lagrange(x, xs, ys) for x in new_xs]
    if method == "spline":
        coeffs = cubic_spline_coeffs(xs, ys)
        return [_eval_spline(x, xs, coeffs) for x in new_xs]
    raise InterpError(f"unknown interpolation method: {method!r}")
