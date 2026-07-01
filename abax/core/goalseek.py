"""One-variable root / goal solver (find ``x`` such that ``f(x) == target``).

The public entry point is :func:`goal_seek`. It first tries the secant method,
seeded from two nearby points, because it converges fast on smooth functions
and needs no bracket. When the seed points bracket a sign change -- or a short
expanding search can find such a bracket -- it falls back to bisection, which
cannot diverge and so gives robustness on awkward or poorly-seeded problems.

Pure stdlib (only :mod:`math`) -> lives in ``core``.
"""

from __future__ import annotations

import math
from collections.abc import Callable


class GoalSeekError(Exception):
    """Raised when the solver cannot find a value satisfying the goal.

    Covers convergence failure, a NaN/inf result, and any exception raised by
    the user-supplied function while it is being evaluated.
    """


def _finite(value: float) -> float:
    """Return ``value`` as a float, rejecting NaN and infinities."""
    result = float(value)
    if not math.isfinite(result):
        raise GoalSeekError("function produced a non-finite value")
    return result


def goal_seek(
    f: Callable[[float], float],
    target: float,
    x0: float,
    *,
    x1: float | None = None,
    tol: float = 1e-9,
    max_iter: int = 100,
) -> float:
    """Return ``x`` such that ``f(x)`` is approximately ``target``.

    Define ``g(x) = f(x) - target`` and search for a root of ``g``.

    The secant method is tried first, seeded from ``x0`` and ``x1``. When
    ``x1`` is ``None`` it defaults to ``x0 + 1`` (if ``x0 == 0``) or ``x0 * 1.1``
    otherwise. If the seed points bracket a sign change, or an expanding search
    around them finds a bracket, bisection is used for robustness.

    Convergence is reached when ``abs(g(x)) <= tol`` or the update step falls
    below ``tol``.

    :raises GoalSeekError: if ``f`` raises, yields a NaN/inf value, or the
        method fails to converge within ``max_iter`` iterations.
    """
    if tol <= 0:
        raise GoalSeekError("tol must be positive")
    if max_iter <= 0:
        raise GoalSeekError("max_iter must be positive")

    def g(x: float) -> float:
        try:
            value = f(x)
        except GoalSeekError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface any callable failure
            raise GoalSeekError(f"function raised at x={x!r}: {exc!r}") from exc
        return _finite(value) - target

    if x1 is None:
        x1 = x0 + 1.0 if x0 == 0 else x0 * 1.1

    a = float(x0)
    b = float(x1)
    ga = g(a)
    if abs(ga) <= tol:
        return a
    gb = g(b)
    if abs(gb) <= tol:
        return b

    # If we already bracket a root, go straight to the robust method.
    if ga * gb < 0:
        return _bisect(g, a, b, ga, gb, tol, max_iter)

    # Otherwise try the fast secant iteration first.
    try:
        return _secant(g, a, b, ga, gb, tol, max_iter)
    except GoalSeekError:
        # Secant stalled or diverged: look for a bracket, then bisect.
        bracket = _find_bracket(g, a, b, max_iter)
        if bracket is None:
            raise
        lo, hi, glo, ghi = bracket
        return _bisect(g, lo, hi, glo, ghi, tol, max_iter)


def _secant(
    g: Callable[[float], float],
    a: float,
    b: float,
    ga: float,
    gb: float,
    tol: float,
    max_iter: int,
) -> float:
    """Run the secant iteration, raising ``GoalSeekError`` on stall/divergence."""
    for _ in range(max_iter):
        denom = gb - ga
        if denom == 0.0:
            raise GoalSeekError("secant step stalled (flat secant)")
        x = b - gb * (b - a) / denom
        if not math.isfinite(x):
            raise GoalSeekError("secant produced a non-finite iterate")
        gx = g(x)
        if abs(gx) <= tol or abs(x - b) <= tol:
            return x
        a, ga = b, gb
        b, gb = x, gx
    raise GoalSeekError(f"secant failed to converge within {max_iter} iterations")


def _bisect(
    g: Callable[[float], float],
    lo: float,
    hi: float,
    glo: float,
    ghi: float,
    tol: float,
    max_iter: int,
) -> float:
    """Bisect a sign-changing bracket ``[lo, hi]`` down to ``tol``."""
    if glo * ghi > 0:
        raise GoalSeekError("bisection requires a sign-changing bracket")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        gmid = g(mid)
        if abs(gmid) <= tol or 0.5 * abs(hi - lo) <= tol:
            return mid
        if glo * gmid < 0:
            hi, ghi = mid, gmid
        else:
            lo, glo = mid, gmid
    raise GoalSeekError(f"bisection failed to converge within {max_iter} iterations")


def _find_bracket(
    g: Callable[[float], float],
    a: float,
    b: float,
    max_iter: int,
) -> tuple[float, float, float, float] | None:
    """Expand outward from ``[a, b]`` searching for a sign change.

    Returns ``(lo, hi, g(lo), g(hi))`` when found, else ``None``.
    """
    if a == b:
        b = a + 1.0
    lo, hi = (a, b) if a < b else (b, a)
    glo = g(lo)
    ghi = g(hi)
    if glo * ghi < 0:
        return lo, hi, glo, ghi
    width = hi - lo
    if width == 0.0:
        width = 1.0
    for _ in range(max_iter):
        width *= 2.0
        lo -= width
        hi += width
        glo = g(lo)
        ghi = g(hi)
        if glo * ghi < 0:
            return lo, hi, glo, ghi
    return None
