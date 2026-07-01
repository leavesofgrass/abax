"""Implicit / stiff solvers for first-order systems of ODEs.

Companion to :mod:`abax.core.science.ode` (explicit Euler / RK4 / RKF45) for problems
that are *stiff*: where the time-scale of the fastest-decaying mode is far
smaller than the interval of interest, so an explicit method is forced to take
absurdly tiny steps to stay stable. Implicit methods absorb this by solving a
nonlinear system at every step instead of marching forward directly.

Same contract as :mod:`abax.core.science.ode`: the right-hand side
``f(t, y) -> list[float]`` maps a state vector ``y`` (always a ``list``, a
scalar problem is a 1-element list) to its time-derivative; every solver returns
``(ts, ys)`` over ``n`` equal steps, ``ts`` with ``n + 1`` entries and ``ys`` the
matching list of state vectors.

Methods:

* :func:`backward_euler` — implicit (backward) Euler, 1st order, L-stable.
* :func:`implicit_trapezoid` — Crank-Nicolson, 2nd order, A-stable.
* :func:`bdf2` — 2nd-order backward differentiation formula (first step
  bootstrapped with one backward-Euler step).
* :func:`solve_stiff` — dispatch by name.

Each step solves its nonlinear system by Newton iteration: the residual ``G(y)``
is driven to zero, its Jacobian ``J = dG/dy`` is approximated by forward finite
differences (:func:`_jacobian`), and the Newton correction ``J . delta = G`` is
solved by Gaussian elimination with partial pivoting (:func:`_solve_linear`).
Everything runs in IEEE doubles via the stdlib :mod:`math` module only and is
self-contained (no other abax module is imported). Bad arguments (``n < 1``,
empty ``y0``, a wrong-length derivative), a singular linear system, or Newton
non-convergence raise :class:`StiffODEError`.
"""

from __future__ import annotations

import math
from typing import Callable, List, Tuple

# A right-hand side: f(t, y) -> dy/dt, both y and the result are state vectors.
RHS = Callable[[float, List[float]], List[float]]


class StiffODEError(Exception):
    """Raised when a stiff/implicit ODE solver cannot produce a valid result."""


# --------------------------------------------------------------------------- #
# Small vector / linear-algebra helpers (stdlib-only, self-contained).
# --------------------------------------------------------------------------- #


def _eval(f: RHS, t: float, y: List[float], dim: int) -> List[float]:
    """Evaluate ``f(t, y)`` and verify it returns a ``dim``-length vector."""
    d = f(t, y)
    if len(d) != dim:
        raise StiffODEError(
            f"f returned a length-{len(d)} vector, expected length {dim}"
        )
    return d


def _add(a: List[float], b: List[float]) -> List[float]:
    """Element-wise sum of two equal-length vectors."""
    return [ai + bi for ai, bi in zip(a, b)]


def _sub(a: List[float], b: List[float]) -> List[float]:
    """Element-wise difference ``a - b`` of two equal-length vectors."""
    return [ai - bi for ai, bi in zip(a, b)]


def _scale(alpha: float, x: List[float]) -> List[float]:
    """Element-wise scalar multiple ``alpha * x``."""
    return [alpha * xi for xi in x]


def _jacobian(
    f: RHS, t: float, y: List[float], h_eps: float = 1e-7
) -> List[List[float]]:
    """Forward-difference approximation of ``df/dy`` at ``(t, y)``.

    Returns an ``m x m`` matrix ``J`` (``m = len(y)``) with
    ``J[i][j] ~= d f_i / d y_j``. The perturbation for column ``j`` is scaled by
    ``max(1, |y_j|)`` so it stays meaningful across magnitudes.
    """
    m = len(y)
    f0 = _eval(f, t, y, m)
    jac: List[List[float]] = [[0.0] * m for _ in range(m)]
    for j in range(m):
        step = h_eps * max(1.0, abs(y[j]))
        yp = list(y)
        yp[j] += step
        fp = _eval(f, t, yp, m)
        inv = 1.0 / step
        for i in range(m):
            jac[i][j] = (fp[i] - f0[i]) * inv
    return jac


def _solve_linear(A: List[List[float]], b: List[float]) -> List[float]:
    """Solve ``A x = b`` by Gaussian elimination with partial pivoting.

    ``A`` is a square matrix (list of rows) and ``b`` the right-hand side.
    Raises :class:`StiffODEError` if ``A`` is singular (or numerically so).
    The inputs are copied; the caller's matrix and vector are not mutated.
    """
    n = len(b)
    # Build an augmented [A | b] working copy.
    M = [list(A[i]) + [b[i]] for i in range(n)]

    for col in range(n):
        # Partial pivot: largest-magnitude entry in this column at or below row.
        pivot = col
        best = abs(M[col][col])
        for r in range(col + 1, n):
            v = abs(M[r][col])
            if v > best:
                best = v
                pivot = r
        if best == 0.0:
            raise StiffODEError("singular matrix in linear solve")
        if pivot != col:
            M[col], M[pivot] = M[pivot], M[col]

        piv = M[col][col]
        for r in range(col + 1, n):
            factor = M[r][col] / piv
            if factor == 0.0:
                continue
            row_r = M[r]
            row_c = M[col]
            for c in range(col, n + 1):
                row_r[c] -= factor * row_c[c]

    # Back-substitution.
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = M[i][n]
        for c in range(i + 1, n):
            s -= M[i][c] * x[c]
        diag = M[i][i]
        if diag == 0.0:
            raise StiffODEError("singular matrix in linear solve")
        x[i] = s / diag
    return x


def _newton(
    residual: Callable[[List[float]], List[float]],
    rhs_for_jac: RHS,
    t_eval: float,
    h_coeff: float,
    y_guess: List[float],
    newton_tol: float,
    newton_max: int,
) -> List[float]:
    """Solve ``residual(y) = 0`` by Newton iteration from ``y_guess``.

    The residual has the form ``G(y) = y - c - h_coeff * f(t_eval, y)``, so its
    Jacobian is ``I - h_coeff * df/dy`` with ``df/dy`` from :func:`_jacobian`.
    Iterates ``y <- y - J^-1 G(y)`` until ``max|delta| < newton_tol`` or
    ``newton_max`` iterations elapse (then :class:`StiffODEError`).
    """
    m = len(y_guess)
    y = list(y_guess)
    for _ in range(newton_max):
        g = residual(y)
        dfdy = _jacobian(rhs_for_jac, t_eval, y)
        # J = I - h_coeff * df/dy
        jac = [
            [(1.0 if i == j else 0.0) - h_coeff * dfdy[i][j] for j in range(m)]
            for i in range(m)
        ]
        delta = _solve_linear(jac, g)
        y = _sub(y, delta)
        err = max(abs(d) for d in delta)
        if not math.isfinite(err):
            raise StiffODEError("Newton iteration diverged (non-finite step)")
        if err < newton_tol:
            return y
    raise StiffODEError("Newton iteration failed to converge")


def _validate(n: int, y0: List[float]) -> None:
    """Common argument checks shared by every solver."""
    if n < 1:
        raise StiffODEError("n must be at least 1")
    if not y0:
        raise StiffODEError("y0 must be non-empty")


# --------------------------------------------------------------------------- #
# Solvers.
# --------------------------------------------------------------------------- #


def backward_euler(
    f: RHS,
    t0: float,
    y0: List[float],
    t1: float,
    n: int = 100,
    newton_tol: float = 1e-10,
    newton_max: int = 50,
) -> Tuple[List[float], List[List[float]]]:
    """Integrate ``dy/dt = f(t, y)`` by implicit (backward) Euler.

    Each step solves ``y_{k+1} = y_k + h f(t_{k+1}, y_{k+1})`` for ``y_{k+1}``
    via Newton iteration (residual ``G(y) = y - y_k - h f(t_{k+1}, y)``, Jacobian
    ``I - h df/dy`` by finite differences). Uses ``n`` equal steps; returns
    ``(ts, ys)`` with ``ts`` of length ``n + 1``. L-stable (1st order), so it
    stays bounded on stiff decay where explicit Euler blows up.

    :class:`StiffODEError` if ``n < 1``, ``y0`` is empty, ``f`` returns a
    wrong-length vector, the linear solve is singular, or Newton fails.
    """
    _validate(n, y0)
    dim = len(y0)
    h = (t1 - t0) / n
    ts = [t0]
    ys = [list(y0)]
    y = list(y0)
    for i in range(n):
        t_next = t0 + (i + 1) * h
        y_k = y

        def residual(yn: List[float], _yk: List[float] = y_k) -> List[float]:
            fn = _eval(f, t_next, yn, dim)
            return _sub(_sub(yn, _yk), _scale(h, fn))

        # Explicit-Euler predictor as the initial Newton guess.
        y = _newton(
            residual, f, t_next, h, _add(y_k, _scale(h, _eval(f, ts[-1], y_k, dim))),
            newton_tol, newton_max,
        )
        ts.append(t_next)
        ys.append(y)
    return ts, ys


def implicit_trapezoid(
    f: RHS,
    t0: float,
    y0: List[float],
    t1: float,
    n: int = 100,
    newton_tol: float = 1e-10,
    newton_max: int = 50,
) -> Tuple[List[float], List[List[float]]]:
    """Integrate ``dy/dt = f(t, y)`` by the implicit trapezoid (Crank-Nicolson).

    Each step solves ``y_{k+1} = y_k + h/2 (f(t_k, y_k) + f(t_{k+1}, y_{k+1}))``.
    2nd order and A-stable, so it is both more accurate than
    :func:`backward_euler` on smooth problems and stable on stiff ones. Uses
    ``n`` equal steps; returns ``(ts, ys)`` with the same shape as
    :func:`backward_euler`. Same :class:`StiffODEError` conditions.
    """
    _validate(n, y0)
    dim = len(y0)
    h = (t1 - t0) / n
    ts = [t0]
    ys = [list(y0)]
    y = list(y0)
    for i in range(n):
        t_cur = t0 + i * h
        t_next = t0 + (i + 1) * h
        y_k = y
        f_k = _eval(f, t_cur, y_k, dim)
        # Constant part: y_k + h/2 * f(t_k, y_k).
        const = _add(y_k, _scale(0.5 * h, f_k))

        def residual(yn: List[float], _c: List[float] = const) -> List[float]:
            fn = _eval(f, t_next, yn, dim)
            return _sub(_sub(yn, _c), _scale(0.5 * h, fn))

        # h_coeff for the Jacobian is h/2 here.
        y = _newton(
            residual, f, t_next, 0.5 * h, _add(y_k, _scale(h, f_k)),
            newton_tol, newton_max,
        )
        ts.append(t_next)
        ys.append(y)
    return ts, ys


def bdf2(
    f: RHS,
    t0: float,
    y0: List[float],
    t1: float,
    n: int = 100,
    newton_tol: float = 1e-10,
    newton_max: int = 50,
) -> Tuple[List[float], List[List[float]]]:
    """Integrate ``dy/dt = f(t, y)`` by the 2nd-order BDF (BDF2).

    The two-step formula ``y_{k+1} - 4/3 y_k + 1/3 y_{k-1} = 2/3 h
    f(t_{k+1}, y_{k+1})`` is solved each step by Newton iteration. The very first
    step (where ``y_{k-1}`` does not yet exist) is bootstrapped with a single
    :func:`backward_euler` step. 2nd order and stiffly stable. Uses ``n`` equal
    steps; returns ``(ts, ys)``. Same :class:`StiffODEError` conditions.
    """
    _validate(n, y0)
    dim = len(y0)
    h = (t1 - t0) / n
    ts = [t0]
    ys = [list(y0)]

    if n == 1:
        # Nothing to bootstrap past: a single backward-Euler step is BDF1 here.
        return backward_euler(f, t0, y0, t1, 1, newton_tol, newton_max)

    # Bootstrap step 1 with one backward-Euler step over [t0, t0 + h].
    t1_be, ys_be = backward_euler(f, t0, y0, t0 + h, 1, newton_tol, newton_max)
    y_prev = list(y0)          # y_{k-1}
    y_cur = list(ys_be[-1])    # y_k
    ts.append(t0 + h)
    ys.append(y_cur)

    for i in range(1, n):
        t_next = t0 + (i + 1) * h
        coeff = (2.0 / 3.0) * h
        # Constant part: 4/3 y_k - 1/3 y_{k-1}.
        const = _sub(_scale(4.0 / 3.0, y_cur), _scale(1.0 / 3.0, y_prev))

        def residual(yn: List[float], _c: List[float] = const) -> List[float]:
            fn = _eval(f, t_next, yn, dim)
            return _sub(_sub(yn, _c), _scale(coeff, fn))

        # Guess: linear extrapolation from the last two points.
        guess = _sub(_scale(2.0, y_cur), y_prev)
        y_next = _newton(
            residual, f, t_next, coeff, guess, newton_tol, newton_max
        )
        ts.append(t_next)
        ys.append(y_next)
        y_prev = y_cur
        y_cur = y_next
    return ts, ys


def solve_stiff(
    f: RHS,
    t_span: Tuple[float, float],
    y0: List[float],
    method: str = "bdf2",
    n: int = 100,
) -> Tuple[List[float], List[List[float]]]:
    """Solve ``dy/dt = f(t, y)`` over ``t_span = (t0, t1)`` by the named method.

    ``method`` is one of ``"backward_euler"``, ``"implicit_trapezoid"``, or
    ``"bdf2"`` (default), each over ``n`` equal steps. Returns ``(ts, ys)``.
    :class:`StiffODEError` for an unknown method.
    """
    t0, t1 = t_span
    if method == "backward_euler":
        return backward_euler(f, t0, y0, t1, n)
    if method == "implicit_trapezoid":
        return implicit_trapezoid(f, t0, y0, t1, n)
    if method == "bdf2":
        return bdf2(f, t0, y0, t1, n)
    raise StiffODEError(f"unknown method: {method!r}")
