"""Pure-Python solvers for first-order systems of ordinary differential equations.

A small, dependency-free toolkit for integrating an initial-value problem
``dy/dt = f(t, y)`` where the state ``y`` is a vector (``list[float]``) and the
right-hand side ``f(t, y) -> list[float]`` returns its time-derivative. To keep
one consistent contract a scalar ODE is expressed as a 1-element list, and every
solver returns the state vector at each step.

Fixed-step methods: :func:`euler` (explicit Euler) and :func:`rk4` (classic
fourth-order Runge-Kutta), each over ``n`` equal steps from ``t0`` to ``t1``.
Adaptive method: :func:`rk45` (Runge-Kutta-Fehlberg with step-size control to a
tolerance, landing exactly on ``t1``). :func:`solve` dispatches by name.

All routines work in IEEE doubles via the stdlib :mod:`math` module only, and
raise :class:`ODEError` rather than returning a bogus result when given bad
arguments (``n < 1``, empty ``y0``, a wrong-length derivative) or when an
adaptive step cannot make progress (step underflow, too many steps).
"""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Tuple

# A right-hand side: f(t, y) -> dy/dt, both y and the result are state vectors.
RHS = Callable[[float, List[float]], List[float]]


class ODEError(Exception):
    """Raised when an ODE solver cannot produce a valid result."""


def _eval(f: RHS, t: float, y: List[float], n: int) -> List[float]:
    """Evaluate ``f(t, y)`` and verify it returns an ``n``-length vector."""
    d = f(t, y)
    if len(d) != n:
        raise ODEError(
            f"f returned a length-{len(d)} vector, expected length {n}"
        )
    return d


def _add(a: List[float], b: List[float]) -> List[float]:
    """Element-wise sum of two equal-length vectors."""
    return [ai + bi for ai, bi in zip(a, b)]


def _axpy(alpha: float, x: List[float], y: List[float]) -> List[float]:
    """Return ``alpha * x + y`` element-wise (BLAS-style fused multiply-add)."""
    return [alpha * xi + yi for xi, yi in zip(x, y)]


def _scale(alpha: float, x: List[float]) -> List[float]:
    """Element-wise scalar multiple ``alpha * x``."""
    return [alpha * xi for xi in x]


def euler(
    f: RHS,
    t0: float,
    y0: List[float],
    t1: float,
    n: int = 100,
) -> Tuple[List[float], List[List[float]]]:
    """Integrate ``dy/dt = f(t, y)`` by explicit Euler over ``n`` equal steps.

    Returns ``(ts, ys)``: ``ts`` has ``n + 1`` entries from ``t0`` to ``t1`` and
    ``ys`` is the matching list of state vectors (each ``len(y0)`` long).
    :class:`ODEError` if ``n < 1``, ``y0`` is empty, or ``f`` returns a
    wrong-length vector.
    """
    if n < 1:
        raise ODEError("n must be at least 1")
    if not y0:
        raise ODEError("y0 must be non-empty")

    dim = len(y0)
    h = (t1 - t0) / n
    ts = [t0]
    ys = [list(y0)]
    t = t0
    y = list(y0)
    for i in range(n):
        d = _eval(f, t, y, dim)
        y = _axpy(h, d, y)
        t = t0 + (i + 1) * h
        ts.append(t)
        ys.append(y)
    return ts, ys


def rk4(
    f: RHS,
    t0: float,
    y0: List[float],
    t1: float,
    n: int = 100,
) -> Tuple[List[float], List[List[float]]]:
    """Integrate ``dy/dt = f(t, y)`` by classic 4th-order Runge-Kutta.

    Uses ``n`` equal steps from ``t0`` to ``t1``; returns ``(ts, ys)`` with the
    same shape as :func:`euler`. :class:`ODEError` for the same bad arguments.
    """
    if n < 1:
        raise ODEError("n must be at least 1")
    if not y0:
        raise ODEError("y0 must be non-empty")

    dim = len(y0)
    h = (t1 - t0) / n
    ts = [t0]
    ys = [list(y0)]
    t = t0
    y = list(y0)
    for i in range(n):
        k1 = _eval(f, t, y, dim)
        k2 = _eval(f, t + 0.5 * h, _axpy(0.5 * h, k1, y), dim)
        k3 = _eval(f, t + 0.5 * h, _axpy(0.5 * h, k2, y), dim)
        k4 = _eval(f, t + h, _axpy(h, k3, y), dim)
        y = [
            yi + (h / 6.0) * (a + 2.0 * b + 2.0 * c + d)
            for yi, a, b, c, d in zip(y, k1, k2, k3, k4)
        ]
        t = t0 + (i + 1) * h
        ts.append(t)
        ys.append(y)
    return ts, ys


# Runge-Kutta-Fehlberg (RKF45) Butcher tableau coefficients.
_A = (
    (),
    (1.0 / 4.0,),
    (3.0 / 32.0, 9.0 / 32.0),
    (1932.0 / 2197.0, -7200.0 / 2197.0, 7296.0 / 2197.0),
    (439.0 / 216.0, -8.0, 3680.0 / 513.0, -845.0 / 4104.0),
    (-8.0 / 27.0, 2.0, -3544.0 / 2565.0, 1859.0 / 4104.0, -11.0 / 40.0),
)
_C = (0.0, 1.0 / 4.0, 3.0 / 8.0, 12.0 / 13.0, 1.0, 1.0 / 2.0)
# 4th-order solution weights.
_B4 = (25.0 / 216.0, 0.0, 1408.0 / 2565.0, 2197.0 / 4104.0, -1.0 / 5.0, 0.0)
# 5th-order solution weights.
_B5 = (
    16.0 / 135.0,
    0.0,
    6656.0 / 12825.0,
    28561.0 / 56430.0,
    -9.0 / 50.0,
    2.0 / 55.0,
)


def rk45(
    f: RHS,
    t0: float,
    y0: List[float],
    t1: float,
    tol: float = 1e-6,
    h0: Optional[float] = None,
    max_steps: int = 100000,
) -> Tuple[List[float], List[List[float]]]:
    """Integrate ``dy/dt = f(t, y)`` adaptively (Runge-Kutta-Fehlberg, RKF45).

    The step size is grown or shrunk to keep the estimated local error below
    ``tol`` (comparing the embedded 4th- and 5th-order solutions); the final
    step is clamped so the trajectory lands exactly on ``t1``. Returns the
    actually-taken, non-uniform ``(ts, ys)`` including both endpoints.

    Integrates backwards when ``t1 < t0``; returns the single initial point when
    ``t1 == t0``. :class:`ODEError` on step underflow (non-convergence) or when
    ``max_steps`` is exceeded.
    """
    if not y0:
        raise ODEError("y0 must be non-empty")

    dim = len(y0)
    ts = [t0]
    ys = [list(y0)]
    if t1 == t0:
        return ts, ys

    direction = 1.0 if t1 > t0 else -1.0
    span = abs(t1 - t0)
    if h0 is None:
        h = span / 100.0
    else:
        h = abs(h0)
    if h <= 0.0:
        h = span / 100.0
    min_h = span * 1e-14

    t = t0
    y = list(y0)
    steps = 0
    while (t1 - t) * direction > 0.0:
        if steps >= max_steps:
            raise ODEError("exceeded max_steps without reaching t1")
        steps += 1

        # Clamp the step so we don't overshoot the endpoint.
        if (t + direction * h - t1) * direction > 0.0:
            h = abs(t1 - t)
        dt = direction * h

        ks: List[List[float]] = []
        for i in range(6):
            yi = list(y)
            for j in range(i):
                yi = _axpy(dt * _A[i][j], ks[j], yi)
            ks.append(_eval(f, t + _C[i] * dt, yi, dim))

        y4 = list(y)
        y5 = list(y)
        for i in range(6):
            if _B4[i]:
                y4 = _axpy(dt * _B4[i], ks[i], y4)
            if _B5[i]:
                y5 = _axpy(dt * _B5[i], ks[i], y5)

        err = math.sqrt(sum((a - b) ** 2 for a, b in zip(y5, y4)))
        if not math.isfinite(err):
            raise ODEError("non-finite error estimate")

        if err <= tol or h <= min_h:
            t += dt
            y = y5
            ts.append(t)
            ys.append(y)

        # Adapt the step size for the next iteration.
        if err == 0.0:
            factor = 4.0
        else:
            factor = 0.84 * (tol / err) ** 0.25
            factor = min(max(factor, 0.1), 4.0)
        h *= factor
        if h <= min_h and (t1 - t) * direction > 0.0:
            # Allow the clamped final step even at the floor; otherwise underflow.
            if h < min_h * 0.5:
                raise ODEError("step size underflow; cannot converge")
            h = min_h

    return ts, ys


def solve(
    f: RHS,
    t_span: Tuple[float, float],
    y0: List[float],
    method: str = "rk4",
    n: int = 100,
    tol: float = 1e-6,
) -> Tuple[List[float], List[List[float]]]:
    """Solve ``dy/dt = f(t, y)`` over ``t_span = (t0, t1)`` by the named method.

    ``method`` is one of ``"euler"``, ``"rk4"`` (default), or ``"rk45"``. The
    fixed-step methods use ``n``; the adaptive ``rk45`` uses ``tol``. Returns
    ``(ts, ys)``. :class:`ODEError` for an unknown method.
    """
    t0, t1 = t_span
    if method == "euler":
        return euler(f, t0, y0, t1, n)
    if method == "rk4":
        return rk4(f, t0, y0, t1, n)
    if method == "rk45":
        return rk45(f, t0, y0, t1, tol)
    raise ODEError(f"unknown method: {method!r}")
