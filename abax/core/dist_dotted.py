"""Wave I — the modern dotted distribution family and hypothesis tests.

Excel 2010 renamed its statistical functions to dotted names and, for the t, F
and chi-square families, split each into left-tail (``…DIST``), right-tail
(``…DIST.RT``) and two-tail (``T.DIST.2T``) forms with matching inverses. The
legacy names abax already ships (``TDIST``/``TINV``/``FDIST``/``CHIDIST``…)
are the *right-tail* halves; this pack adds the left-tail/density halves and
their inverses, plus the hypothesis tests (``T.TEST`` with tails and paired /
pooled / Welch types, ``Z.TEST``, ``F.TEST``, ``CHISQ.TEST``) and
``CONFIDENCE.T``.

All the numerics reuse the incomplete-gamma/beta backbone from
:mod:`abax.core.stats_dist` via the pdf/cdf helpers in
:mod:`abax.core.gnumeric_fns` — no new machinery. Registered by
:func:`register` alongside the other parity packs.
"""

from __future__ import annotations

import math
from typing import Any, Callable

from .errors import CellError
from .gnumeric_fns import (
    _bisect,
    _chisq_cdf,
    _chisq_pdf,
    _f_cdf,
    _f_pdf,
    _norm_pdf,
    _t_cdf,
    _t_pdf,
)
from .stats_dist import _phi, _try_num
from .values import RangeValue


def _arg(args: list, i: int, default: Any = None) -> Any:
    return args[i] if i < len(args) else default


def _num(v: Any) -> "float | None":
    return _try_num(v)


def _cumulative(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1")
    return bool(v)


def _flat(v: Any) -> list:
    if isinstance(v, RangeValue):
        return v.flat()
    if isinstance(v, list):
        out: list = []
        for item in v:
            out.extend(_flat(item))
        return out
    return [v]


def _numbers(v: Any) -> list:
    return [float(x) for x in _flat(v)
            if isinstance(x, (int, float)) and not isinstance(x, bool)]


def _mean_var(xs: list) -> "tuple[float, float]":
    n = len(xs)
    m = sum(xs) / n
    return m, sum((x - m) ** 2 for x in xs) / (n - 1)


# --- normal ------------------------------------------------------------------


def _norm_s_dist(args: list) -> Any:
    """NORM.S.DIST(z, cumulative) — standard normal CDF or density."""
    z = _num(_arg(args, 0))
    if z is None:
        return CellError(CellError.VALUE)
    return _phi(z) if _cumulative(_arg(args, 1, True)) else _norm_pdf(z, 0.0, 1.0)


# --- Student t ---------------------------------------------------------------


def _t_args(args: list) -> "tuple[float, float] | CellError":
    x = _num(_arg(args, 0))
    df = _num(_arg(args, 1))
    if x is None or df is None:
        return CellError(CellError.VALUE)
    if df < 1:
        return CellError(CellError.NUM)
    return x, df


def _t_dist(args: list) -> Any:
    """T.DIST(x, df, cumulative) — left-tail CDF or density."""
    got = _t_args(args)
    if isinstance(got, CellError):
        return got
    x, df = got
    return _t_cdf(x, df) if _cumulative(_arg(args, 2, True)) else _t_pdf(x, df)


def _t_dist_rt(args: list) -> Any:
    """T.DIST.RT(x, df) — right-tail probability."""
    got = _t_args(args)
    return got if isinstance(got, CellError) else 1.0 - _t_cdf(*got)


def _t_dist_2t(args: list) -> Any:
    """T.DIST.2T(x, df) — two-tailed probability (x must be >= 0)."""
    got = _t_args(args)
    if isinstance(got, CellError):
        return got
    x, df = got
    if x < 0:
        return CellError(CellError.NUM)
    return 2.0 * (1.0 - _t_cdf(x, df))


def _t_ppf(p: float, df: float) -> float:
    return _bisect(lambda t: _t_cdf(t, df), p, -1e10, 1e10)


def _t_inv(args: list) -> Any:
    """T.INV(p, df) — left-tail inverse."""
    p = _num(_arg(args, 0))
    df = _num(_arg(args, 1))
    if p is None or df is None:
        return CellError(CellError.VALUE)
    if not (0.0 < p < 1.0) or df < 1:
        return CellError(CellError.NUM)
    return _t_ppf(p, df)


def _t_inv_2t(args: list) -> Any:
    """T.INV.2T(p, df) — two-tailed inverse (the legacy TINV)."""
    p = _num(_arg(args, 0))
    df = _num(_arg(args, 1))
    if p is None or df is None:
        return CellError(CellError.VALUE)
    if not (0.0 < p <= 1.0) or df < 1:
        return CellError(CellError.NUM)
    return _t_ppf(1.0 - p / 2.0, df)


# --- chi-square ---------------------------------------------------------------


def _chisq_dist(args: list) -> Any:
    """CHISQ.DIST(x, df, cumulative) — left-tail CDF or density."""
    x = _num(_arg(args, 0))
    df = _num(_arg(args, 1))
    if x is None or df is None:
        return CellError(CellError.VALUE)
    if df < 1 or x < 0:
        return CellError(CellError.NUM)
    return _chisq_cdf(x, df) if _cumulative(_arg(args, 2, True)) else _chisq_pdf(x, df)


def _chisq_inv(args: list) -> Any:
    """CHISQ.INV(p, df) — left-tail inverse."""
    p = _num(_arg(args, 0))
    df = _num(_arg(args, 1))
    if p is None or df is None:
        return CellError(CellError.VALUE)
    if not (0.0 <= p < 1.0) or df < 1:
        return CellError(CellError.NUM)
    if p == 0.0:
        return 0.0
    return _bisect(lambda x: _chisq_cdf(x, df), p, 0.0, max(4.0 * df, 16.0))


# --- F -------------------------------------------------------------------------


def _f_dist(args: list) -> Any:
    """F.DIST(x, df1, df2, cumulative) — left-tail CDF or density."""
    x = _num(_arg(args, 0))
    d1 = _num(_arg(args, 1))
    d2 = _num(_arg(args, 2))
    if x is None or d1 is None or d2 is None:
        return CellError(CellError.VALUE)
    if x < 0 or d1 < 1 or d2 < 1:
        return CellError(CellError.NUM)
    return _f_cdf(x, d1, d2) if _cumulative(_arg(args, 3, True)) else _f_pdf(x, d1, d2)


def _f_inv(args: list) -> Any:
    """F.INV(p, df1, df2) — left-tail inverse."""
    p = _num(_arg(args, 0))
    d1 = _num(_arg(args, 1))
    d2 = _num(_arg(args, 2))
    if p is None or d1 is None or d2 is None:
        return CellError(CellError.VALUE)
    if not (0.0 <= p < 1.0) or d1 < 1 or d2 < 1:
        return CellError(CellError.NUM)
    if p == 0.0:
        return 0.0
    return _bisect(lambda x: _f_cdf(x, d1, d2), p, 0.0, 16.0)


# --- confidence interval -------------------------------------------------------


def _confidence_t(args: list) -> Any:
    """CONFIDENCE.T(alpha, sd, n) — t-based confidence half-width."""
    alpha = _num(_arg(args, 0))
    sd = _num(_arg(args, 1))
    n = _num(_arg(args, 2))
    if alpha is None or sd is None or n is None:
        return CellError(CellError.VALUE)
    if not (0.0 < alpha < 1.0) or sd <= 0 or n < 1:
        return CellError(CellError.NUM)
    n = int(n)
    if n == 1:
        return CellError(CellError.DIV0)
    return _t_ppf(1.0 - alpha / 2.0, n - 1) * sd / math.sqrt(n)


# --- hypothesis tests ----------------------------------------------------------


def _t_test(args: list) -> Any:
    """T.TEST(array1, array2, tails, type) — 1 paired, 2 pooled, 3 Welch."""
    a = _numbers(_arg(args, 0))
    b = _numbers(_arg(args, 1))
    tails = _num(_arg(args, 2, 1))
    kind = _num(_arg(args, 3, 2))
    if tails is None or kind is None:
        return CellError(CellError.VALUE)
    tails, kind = int(tails), int(kind)
    if tails not in (1, 2) or kind not in (1, 2, 3):
        return CellError(CellError.NUM)
    if len(a) < 2 or len(b) < 2:
        return CellError(CellError.DIV0)
    try:
        if kind == 1:  # paired
            if len(a) != len(b):
                return CellError(CellError.NA)
            diffs = [x - y for x, y in zip(a, b)]
            m, var = _mean_var(diffs)
            if var == 0:
                return CellError(CellError.DIV0)
            t = m / math.sqrt(var / len(diffs))
            df = float(len(diffs) - 1)
        else:
            ma, va = _mean_var(a)
            mb, vb = _mean_var(b)
            na, nb = len(a), len(b)
            if kind == 2:  # pooled (equal variance)
                sp = ((na - 1) * va + (nb - 1) * vb) / (na + nb - 2)
                if sp == 0:
                    return CellError(CellError.DIV0)
                t = (ma - mb) / math.sqrt(sp * (1.0 / na + 1.0 / nb))
                df = float(na + nb - 2)
            else:  # Welch
                sa, sb = va / na, vb / nb
                if sa + sb == 0:
                    return CellError(CellError.DIV0)
                t = (ma - mb) / math.sqrt(sa + sb)
                df = (sa + sb) ** 2 / (sa**2 / (na - 1) + sb**2 / (nb - 1))
        p = 1.0 - _t_cdf(abs(t), df)
        return tails * p
    except (ValueError, ZeroDivisionError, OverflowError):
        return CellError(CellError.NUM)


def _z_test(args: list) -> Any:
    """Z.TEST(array, x, [sigma]) — one-tailed P(mean > x) under H0."""
    xs = _numbers(_arg(args, 0))
    x0 = _num(_arg(args, 1))
    sigma = _num(_arg(args, 2)) if _arg(args, 2) is not None else None
    if x0 is None:
        return CellError(CellError.VALUE)
    n = len(xs)
    if n == 0:
        return CellError(CellError.NA)
    m, var = (xs[0], 0.0) if n == 1 else _mean_var(xs)
    sd = sigma if sigma is not None else math.sqrt(var)
    if sd <= 0:
        return CellError(CellError.DIV0)
    return 1.0 - _phi((m - x0) / (sd / math.sqrt(n)))


def _f_test(args: list) -> Any:
    """F.TEST(array1, array2) — two-tailed variance-equality p-value."""
    a = _numbers(_arg(args, 0))
    b = _numbers(_arg(args, 1))
    if len(a) < 2 or len(b) < 2:
        return CellError(CellError.DIV0)
    _, va = _mean_var(a)
    _, vb = _mean_var(b)
    if va == 0 or vb == 0:
        return CellError(CellError.DIV0)
    f = va / vb
    left = _f_cdf(f, len(a) - 1, len(b) - 1)
    return 2.0 * min(left, 1.0 - left)


def _grid_of(v: Any) -> "list[list[Any]]":
    if isinstance(v, RangeValue):
        return v.grid
    if isinstance(v, list):
        if v and isinstance(v[0], list):
            return v
        return [[x] for x in v]
    return [[v]]


def _chisq_test(args: list) -> Any:
    """CHISQ.TEST(actual, expected) — independence-test p-value."""
    actual = _grid_of(_arg(args, 0))
    expected = _grid_of(_arg(args, 1))
    rows = len(actual)
    cols = len(actual[0]) if rows else 0
    if rows == 0 or len(expected) != rows or any(len(r) != cols for r in actual) \
            or any(len(r) != cols for r in expected):
        return CellError(CellError.NA)
    stat = 0.0
    for ra, re in zip(actual, expected):
        for a, e in zip(ra, re):
            an, en = _num(a), _num(e)
            if an is None or en is None:
                return CellError(CellError.VALUE)
            if en <= 0:
                return CellError(CellError.DIV0)
            stat += (an - en) ** 2 / en
    if rows > 1 and cols > 1:
        df = (rows - 1) * (cols - 1)
    else:
        df = rows * cols - 1
    if df < 1:
        return CellError(CellError.NA)
    return 1.0 - _chisq_cdf(stat, float(df))


# --- registry ------------------------------------------------------------------

_REGISTRY: dict[str, Callable[[list], Any]] = {
    "NORM.S.DIST": _norm_s_dist,
    "T.DIST": _t_dist,
    "T.DIST.RT": _t_dist_rt,
    "T.DIST.2T": _t_dist_2t,
    "T.INV": _t_inv,
    "T.INV.2T": _t_inv_2t,
    "CHISQ.DIST": _chisq_dist,
    "CHISQ.INV": _chisq_inv,
    "F.DIST": _f_dist,
    "F.INV": _f_inv,
    "CONFIDENCE.T": _confidence_t,
    "T.TEST": _t_test,
    "Z.TEST": _z_test,
    "ZTEST": _z_test,
    "F.TEST": _f_test,
    "FTEST": _f_test,
    "CHISQ.TEST": _chisq_test,
    "CHITEST": _chisq_test,
}


def register(functions: dict) -> None:
    """Merge the dotted distribution/tests family into the engine's table."""
    functions.update(_REGISTRY)
