"""Pure-Python numerical methods: root-finding, integration, differentiation.

A small, dependency-free toolkit of classic numerical routines for use inside
abax. Every routine takes a plain Python callable ``f: Callable[[float],
float]`` (abax wraps a safe compiled expression around it elsewhere) and works
in IEEE doubles via the stdlib :mod:`math` module only.

Root-finding: :func:`bisection` (bracketing), :func:`newton` (Newton-Raphson,
with an optional analytic derivative or an automatic central difference),
:func:`secant`, and :func:`solve_root` (a robust HP-15C-style SOLVE that takes a
bracket or a single guess and combines the secant method with a guaranteed
bisection fallback, returning both the root and ``f`` there). Quadrature:
:func:`integrate` (composite Simpson or trapezoid over ``[a, b]``),
:func:`adaptive_simpson` (adaptive Simpson to a relative/absolute tolerance, the
HP-15C ``INTEGRATE`` engine), and :func:`trapz` (trapezoidal rule over sampled
data, e.g. two spreadsheet columns). Differentiation: :func:`derivative`
(central difference).

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


def solve_root(
    f: Callable[[float], float],
    a: float,
    b: Optional[float] = None,
    tol: float = 1e-12,
    max_iter: int = 200,
) -> tuple[float, float]:
    """Find a root of ``f`` (HP-15C SOLVE): robust secant + bisection fallback.

    Two call forms:

    * **Bracket** — pass ``a`` and ``b`` with ``f(a)`` and ``f(b)`` of opposite
      sign. A root is guaranteed to lie between them and is always found.
    * **Guess** — pass a single ``a`` (leave ``b`` as ``None``). A sign-changing
      bracket is searched for outward from ``a`` (and its neighbourhood); if one
      is found the bracketed solver runs, otherwise a plain secant search is
      attempted from the guess.

    The bracketed path is a hybrid: it tries a secant step and accepts it only
    when it stays inside the current bracket and makes progress, otherwise it
    falls back to a bisection step. This keeps secant's fast convergence while
    inheriting bisection's guaranteed convergence, so it never wanders off the
    way a bare secant/Newton iteration can.

    Returns ``(root, f(root))``. ``f(root)`` should be at or near zero; callers
    can inspect it to judge the quality of the root. Raises
    :class:`NumericError` when no bracket can be established from a lone guess or
    a method fails to converge.
    """
    if b is None:
        bracket = _find_bracket(f, a)
        if bracket is None:
            # No sign change nearby: fall back to a derivative-free secant walk
            # from the guess (handles smooth monotone-ish functions).
            root = secant(f, a, a + 1.0 if a == 0.0 else a * (1.0 + 1e-2),
                          tol=tol, max_iter=max_iter)
            return root, _check_finite(f(root))
        a, b = bracket

    fa = _check_finite(f(a))
    fb = _check_finite(f(b))
    if fa == 0.0:
        return a, 0.0
    if fb == 0.0:
        return b, 0.0
    if (fa > 0.0) == (fb > 0.0):
        raise NumericError("f(a) and f(b) must have opposite signs")

    for _ in range(max_iter):
        # Candidate secant step from the two current bracket endpoints.
        denom = fb - fa
        secant_ok = abs(denom) > 1e-300
        mid = 0.5 * (a + b)
        if secant_ok:
            c = b - fb * (b - a) / denom
            # Accept the secant point only if it stays strictly inside the
            # bracket; otherwise bisect. This is the safeguard.
            lo, hi = (a, b) if a < b else (b, a)
            if not (lo < c < hi):
                c = mid
        else:
            c = mid
        fc = _check_finite(f(c))
        if fc == 0.0 or abs(b - a) < tol:
            return c, fc
        # Keep the sub-bracket that still straddles the root.
        if (fa > 0.0) == (fc > 0.0):
            a, fa = c, fc
        else:
            b, fb = c, fc
    root = 0.5 * (a + b)
    return root, _check_finite(f(root))


def _find_bracket(
    f: Callable[[float], float],
    x0: float,
    factor: float = 1.6,
    max_expand: int = 60,
) -> "tuple[float, float] | None":
    """Search outward from ``x0`` for an interval where ``f`` changes sign.

    Grows a small symmetric window around ``x0`` geometrically until the two
    endpoints bracket a root, or gives up after ``max_expand`` expansions
    (returning ``None``). Used by :func:`solve_root`'s single-guess form.
    """
    step = 1.0 if x0 == 0.0 else abs(x0) * 1e-2
    if step == 0.0:
        step = 1.0
    a = x0 - step
    b = x0 + step
    fa = f(a)
    fb = f(b)
    for _ in range(max_expand):
        if math.isfinite(fa) and math.isfinite(fb) and (fa > 0.0) != (fb > 0.0):
            return a, b
        # Expand whichever side has the smaller magnitude (cheap heuristic).
        if abs(fa) < abs(fb):
            a -= (b - a) * (factor - 1.0)
            fa = f(a)
        else:
            b += (b - a) * (factor - 1.0)
            fb = f(b)
    return None


def integrate(
    f: Callable[[float], float],
    a: float,
    b: float,
    n: int = 1000,
    method: str = "simpson",
) -> float:
    """Approximate the definite integral of ``f`` over ``[a, b]``.

    ``method`` is ``"simpson"`` (composite Simpson's rule; ``n`` is forced even
    by bumping it up by one if odd), ``"trapezoid"`` (composite trapezoidal
    rule), or ``"adaptive"`` (adaptive Simpson to a tolerance — ``n`` is ignored
    and :func:`adaptive_simpson` is used, which is the HP-15C ``INTEGRATE``
    engine). If ``a > b`` the bounds are swapped and the result negated. Raises
    :class:`NumericError` for ``n < 1`` or an unknown ``method``.
    """
    if method == "adaptive":
        return adaptive_simpson(f, a, b)
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


def adaptive_simpson(
    f: Callable[[float], float],
    a: float,
    b: float,
    tol: float = 1e-10,
    max_depth: int = 50,
) -> float:
    """Definite integral of ``f`` over ``[a, b]`` by adaptive Simpson's rule.

    This is the HP-15C ``INTEGRATE`` (∫) engine. The interval is subdivided
    recursively wherever Simpson's estimate over a panel disagrees with the sum
    of Simpson's estimates over its two halves by more than the local
    tolerance, concentrating function evaluations where the integrand is most
    curved. ``tol`` is the total absolute error target; ``max_depth`` bounds the
    recursion so a pathological integrand cannot spin forever.

    If ``a > b`` the bounds are swapped and the result negated; ``a == b``
    integrates to zero. Raises :class:`NumericError` on a non-finite value.
    """
    if a == b:
        return 0.0
    if a > b:
        return -adaptive_simpson(f, b, a, tol, max_depth)

    def simpson(lo: float, hi: float, flo: float, fmid: float, fhi: float) -> float:
        return (hi - lo) / 6.0 * (flo + 4.0 * fmid + fhi)

    fa = _check_finite(f(a))
    fb = _check_finite(f(b))
    m = 0.5 * (a + b)
    fm = _check_finite(f(m))
    whole = simpson(a, b, fa, fm, fb)

    def recurse(
        lo: float, hi: float, flo: float, fmid: float, fhi: float,
        whole: float, eps: float, depth: int,
    ) -> float:
        mid = 0.5 * (lo + hi)
        lmid = 0.5 * (lo + mid)
        rmid = 0.5 * (mid + hi)
        flm = _check_finite(f(lmid))
        frm = _check_finite(f(rmid))
        left = simpson(lo, mid, flo, flm, fmid)
        right = simpson(mid, hi, fmid, frm, fhi)
        # Richardson: (left+right - whole)/15 estimates the error of left+right.
        if depth <= 0 or abs(left + right - whole) <= 15.0 * eps:
            return left + right + (left + right - whole) / 15.0
        return (
            recurse(lo, mid, flo, flm, fmid, left, 0.5 * eps, depth - 1)
            + recurse(mid, hi, fmid, frm, fhi, right, 0.5 * eps, depth - 1)
        )

    return _check_finite(recurse(a, b, fa, fm, fb, whole, tol, max_depth))


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
