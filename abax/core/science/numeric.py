"""Pure-Python numerical methods: root-finding, integration, differentiation.

A small, dependency-free toolkit of classic numerical routines for use inside
abax. Every routine takes a plain Python callable ``f: Callable[[float],
float]`` (abax wraps a safe compiled expression around it elsewhere) and works
in IEEE doubles via the stdlib :mod:`math` module only.

Root-finding: :func:`bisection` (bracketing), :func:`newton` (Newton-Raphson,
with an optional analytic derivative or an automatic central difference), and
:func:`secant`. Quadrature: :func:`integrate` (composite Simpson or trapezoid
over ``[a, b]``) and :func:`trapz` (trapezoidal rule over sampled data, e.g. two
spreadsheet columns). Differentiation: :func:`derivative` (central difference).

All routines guard divisions, watch for non-finite intermediates with
:func:`math.isfinite`, and raise :class:`NumericError` rather than returning a
bogus result when a method cannot make progress (zero derivative, lost bracket,
non-convergence, bad arguments).
"""

from __future__ import annotations

import math
from typing import Callable, Optional


class NumericError(Exception):
    """Raised when a numerical routine cannot produce a valid result."""


def _check_finite(value: float) -> float:
    """Return ``value`` if finite, else raise :class:`NumericError`."""
    if not math.isfinite(value):
        raise NumericError("non-finite value encountered")
    return value


def bisection(
    f: Callable[[float], float],
    a: float,
    b: float,
    tol: float = 1e-12,
    max_iter: int = 200,
) -> float:
    """Find a root of ``f`` in ``[a, b]`` by bisection.

    ``f(a)`` and ``f(b)`` must have opposite signs (a sign-changing bracket);
    otherwise :class:`NumericError` is raised. The bracket is halved until its
    width is below ``tol`` or a midpoint evaluates to exactly zero.
    """
    fa = _check_finite(f(a))
    fb = _check_finite(f(b))
    if fa == 0.0:
        return a
    if fb == 0.0:
        return b
    if (fa > 0.0) == (fb > 0.0):
        raise NumericError("f(a) and f(b) must have opposite signs")

    for _ in range(max_iter):
        mid = 0.5 * (a + b)
        fmid = _check_finite(f(mid))
        if fmid == 0.0 or abs(b - a) < tol:
            return mid
        if (fa > 0.0) == (fmid > 0.0):
            a, fa = mid, fmid
        else:
            b, fb = mid, fmid
    return 0.5 * (a + b)


def newton(
    f: Callable[[float], float],
    x0: float,
    fprime: Optional[Callable[[float], float]] = None,
    tol: float = 1e-12,
    max_iter: int = 100,
) -> float:
    """Find a root of ``f`` near ``x0`` by the Newton-Raphson method.

    If ``fprime`` is ``None`` the derivative is approximated by a central
    difference. Raises :class:`NumericError` on a (near-)zero derivative, a
    non-finite iterate, or failure to converge within ``max_iter`` steps.
    """
    x = x0
    for _ in range(max_iter):
        fx = _check_finite(f(x))
        dfx = fprime(x) if fprime is not None else derivative(f, x)
        dfx = _check_finite(dfx)
        if abs(dfx) < 1e-300:
            raise NumericError("derivative too close to zero")
        step = fx / dfx
        x = _check_finite(x - step)
        if abs(step) < tol:
            return x
    raise NumericError("newton did not converge")


def secant(
    f: Callable[[float], float],
    x0: float,
    x1: float,
    tol: float = 1e-12,
    max_iter: int = 100,
) -> float:
    """Find a root of ``f`` by the secant method using seeds ``x0`` and ``x1``.

    Raises :class:`NumericError` on a (near-)zero denominator, a non-finite
    iterate, or failure to converge within ``max_iter`` steps.
    """
    f0 = _check_finite(f(x0))
    f1 = _check_finite(f(x1))
    for _ in range(max_iter):
        denom = f1 - f0
        if abs(denom) < 1e-300:
            raise NumericError("secant denominator too close to zero")
        step = f1 * (x1 - x0) / denom
        x2 = _check_finite(x1 - step)
        if abs(step) < tol:
            return x2
        x0, f0 = x1, f1
        x1 = x2
        f1 = _check_finite(f(x1))
    raise NumericError("secant did not converge")


def integrate(
    f: Callable[[float], float],
    a: float,
    b: float,
    n: int = 1000,
    method: str = "simpson",
) -> float:
    """Approximate the definite integral of ``f`` over ``[a, b]``.

    ``method`` is ``"simpson"`` (composite Simpson's rule; ``n`` is forced even
    by bumping it up by one if odd) or ``"trapezoid"`` (composite trapezoidal
    rule). If ``a > b`` the bounds are swapped and the result negated. Raises
    :class:`NumericError` for ``n < 1`` or an unknown ``method``.
    """
    if n < 1:
        raise NumericError("n must be at least 1")
    if a == b:
        return 0.0
    if a > b:
        return -integrate(f, b, a, n, method)

    if method == "trapezoid":
        h = (b - a) / n
        total = 0.5 * (_check_finite(f(a)) + _check_finite(f(b)))
        for i in range(1, n):
            total += _check_finite(f(a + i * h))
        return _check_finite(total * h)

    if method == "simpson":
        if n % 2 == 1:
            n += 1
        h = (b - a) / n
        total = _check_finite(f(a)) + _check_finite(f(b))
        for i in range(1, n):
            coeff = 4.0 if i % 2 == 1 else 2.0
            total += coeff * _check_finite(f(a + i * h))
        return _check_finite(total * h / 3.0)

    raise NumericError(f"unknown integration method: {method!r}")


def derivative(f: Callable[[float], float], x: float, h: float = 1e-6) -> float:
    """Approximate ``f'(x)`` by the central-difference formula."""
    if h == 0.0:
        raise NumericError("step h must be non-zero")
    result = (_check_finite(f(x + h)) - _check_finite(f(x - h))) / (2.0 * h)
    return _check_finite(result)


def trapz(xs: list[float], ys: list[float]) -> float:
    """Integrate sampled data ``(xs, ys)`` by the trapezoidal rule.

    ``xs`` must be strictly increasing and the same length as ``ys``, with at
    least two points; otherwise :class:`NumericError` is raised. Intended for
    integrating two spreadsheet columns.
    """
    if len(xs) != len(ys):
        raise NumericError("xs and ys must have equal length")
    if len(xs) < 2:
        raise NumericError("need at least two sample points")
    total = 0.0
    for i in range(1, len(xs)):
        dx = xs[i] - xs[i - 1]
        if dx <= 0.0:
            raise NumericError("xs must be strictly increasing")
        total += 0.5 * dx * (ys[i] + ys[i - 1])
    return _check_finite(total)
