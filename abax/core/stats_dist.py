"""Statistical distribution, correlation and conditional-aggregate functions.

A self-contained, pure-standard-library extension registering a large batch of
Excel-named statistics functions that the core engine does not already provide:
discrete and continuous probability distributions (binomial, Poisson,
exponential, gamma, beta, Weibull, hypergeometric, log-normal, …), their
inverses, a handful of correlation/regression helpers (STEYX, PEARSON, FISHER,
…), descriptive extras (DEVSQ, AVEDEV, TRIMMEAN, PERCENTRANK, RANK.EQ/AVG) and
the multi-criteria conditional aggregates (COUNTIFS/SUMIFS/AVERAGEIFS/MAXIFS/
MINIFS).

The numerical backbone (regularized incomplete gamma/beta, the normal CDF and
its inverse) is implemented here from Numerical-Recipes-style series and
continued fractions, so nothing outside the standard library is imported.
"""

from __future__ import annotations

import math

from .criteria import make_predicate, numeric_criterion
from .errors import CellError
from .functions.helpers import _arg, _flatten, _numbers, _try_num
from .values import RangeValue
from .._runtime import aggregate_accelerator

# ---------------------------------------------------------------------------
# Numerical building blocks (pure Python)
# ---------------------------------------------------------------------------

_SQRT2 = math.sqrt(2.0)
_SQRT2PI = math.sqrt(2.0 * math.pi)
_EPS = 3.0e-16
_FPMIN = 1.0e-300
_MAXIT = 400


def _erf(x: float) -> float:
    return math.erf(x)


def _erfc(x: float) -> float:
    return math.erfc(x)


def _gammp(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a, x)."""
    if x < 0.0 or a <= 0.0:
        raise ValueError("gammp domain")
    if x == 0.0:
        return 0.0
    if x < a + 1.0:
        return _gser(a, x)
    return 1.0 - _gcf(a, x)


def _gammq(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x) = 1 - P(a, x)."""
    if x < 0.0 or a <= 0.0:
        raise ValueError("gammq domain")
    if x == 0.0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gser(a, x)
    return _gcf(a, x)


def _gser(a: float, x: float) -> float:
    """Series representation of P(a, x), good for x < a + 1."""
    gln = math.lgamma(a)
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(_MAXIT):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * _EPS:
            break
    return total * math.exp(-x + a * math.log(x) - gln)


def _gcf(a: float, x: float) -> float:
    """Continued-fraction representation of Q(a, x), good for x >= a + 1."""
    gln = math.lgamma(a)
    b = x + 1.0 - a
    c = 1.0 / _FPMIN
    d = 1.0 / b
    h = d
    for i in range(1, _MAXIT + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = b + an / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x < 0.0 or x > 1.0:
        raise ValueError("betai domain")
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, _MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h


def _phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * _erfc(-z / _SQRT2)


def _norm_pdf_std(z: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * z * z) / _SQRT2PI


# Acklam's algorithm for the inverse standard normal CDF.
_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)


def _norm_ppf_std(p: float) -> float:
    """Inverse standard normal CDF via Acklam, refined with one Halley step."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError("norm_ppf domain")
    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        x = (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    elif p <= phigh:
        q = p - 0.5
        r = q * q
        x = (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q / (
            ((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0
        )
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        x = -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    # One Halley refinement step for full double precision.
    e = _phi(x) - p
    u = e * _SQRT2PI * math.exp(0.5 * x * x)
    x = x - u / (1.0 + 0.5 * x * u)
    return x


def _bisect_cdf(cdf, target: float, lo: float, hi: float, tol: float = 1e-12) -> float:
    """Solve cdf(t) == target on [lo, hi] by bisection."""
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if cdf(mid) < target:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol * max(1.0, abs(mid)):
            break
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _num(v):
    """Coerce to float or return None (used for scalar args)."""
    return _try_num(v)


# ---------------------------------------------------------------------------
# Discrete distributions
# ---------------------------------------------------------------------------


def _binom_pmf(k: int, n: int, p: float) -> float:
    if k < 0 or k > n:
        return 0.0
    if p <= 0.0:
        return 1.0 if k == 0 else 0.0
    if p >= 1.0:
        return 1.0 if k == n else 0.0
    logc = math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
    return math.exp(logc + k * math.log(p) + (n - k) * math.log1p(-p))


def _binomdist(args):
    ks = _num(_arg(args, 0))
    n = _num(_arg(args, 1))
    p = _num(_arg(args, 2))
    if ks is None or n is None or p is None:
        return CellError(CellError.VALUE)
    if len(args) < 4:
        return CellError(CellError.NA)
    cumulative = _truthy(_arg(args, 3))
    k = int(math.floor(ks))
    n = int(math.floor(n))
    if k < 0 or n < 0 or k > n or not (0.0 <= p <= 1.0):
        return CellError(CellError.NUM)
    try:
        if not cumulative:
            return _binom_pmf(k, n, p)
        return sum(_binom_pmf(i, n, p) for i in range(0, k + 1))
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _binominv(args):
    """BINOM.INV / CRITBINOM — smallest k with CDF(k) >= alpha."""
    n = _num(_arg(args, 0))
    p = _num(_arg(args, 1))
    alpha = _num(_arg(args, 2))
    if n is None or p is None or alpha is None:
        return CellError(CellError.VALUE)
    n = int(math.floor(n))
    if n < 0 or not (0.0 <= p <= 1.0) or not (0.0 < alpha < 1.0):
        return CellError(CellError.NUM)
    try:
        cum = 0.0
        for k in range(0, n + 1):
            cum += _binom_pmf(k, n, p)
            if cum >= alpha:
                return float(k)
        return float(n)
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _negbinom_pmf(f: int, s: int, p: float) -> float:
    if f < 0 or s < 1:
        return 0.0
    logc = math.lgamma(f + s) - math.lgamma(f + 1) - math.lgamma(s)
    return math.exp(logc + s * math.log(p) + f * math.log1p(-p))


def _negbinomdist(args):
    fnum = _num(_arg(args, 0))
    snum = _num(_arg(args, 1))
    p = _num(_arg(args, 2))
    if fnum is None or snum is None or p is None:
        return CellError(CellError.VALUE)
    cumulative = _truthy(_arg(args, 3, False))
    f = int(math.floor(fnum))
    s = int(math.floor(snum))
    if f < 0 or s < 1 or not (0.0 < p <= 1.0):
        return CellError(CellError.NUM)
    try:
        if not cumulative:
            return _negbinom_pmf(f, s, p)
        return sum(_negbinom_pmf(i, s, p) for i in range(0, f + 1))
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _poisson_pmf(k: int, mean: float) -> float:
    if k < 0:
        return 0.0
    return math.exp(-mean + k * math.log(mean) - math.lgamma(k + 1)) if mean > 0 else (1.0 if k == 0 else 0.0)


def _poisson(args):
    xnum = _num(_arg(args, 0))
    mean = _num(_arg(args, 1))
    if xnum is None or mean is None:
        return CellError(CellError.VALUE)
    if len(args) < 3:
        return CellError(CellError.NA)
    cumulative = _truthy(_arg(args, 2))
    x = int(math.floor(xnum))
    if x < 0 or mean < 0:
        return CellError(CellError.NUM)
    try:
        if not cumulative:
            return _poisson_pmf(x, mean)
        # CDF(x) = Q(x+1, mean) = 1 - P(x+1, mean)
        if mean == 0.0:
            return 1.0
        return _gammq(x + 1, mean)
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _hypgeom_pmf(k: int, ns: int, m: int, npop: int) -> float:
    """P(X=k): k successes in sample of ns, m successes in population npop."""
    if k < 0 or k > ns or k > m or (ns - k) > (npop - m):
        return 0.0
    logc = (
        math.lgamma(m + 1) - math.lgamma(k + 1) - math.lgamma(m - k + 1)
        + math.lgamma(npop - m + 1) - math.lgamma(ns - k + 1) - math.lgamma(npop - m - ns + k + 1)
        - (math.lgamma(npop + 1) - math.lgamma(ns + 1) - math.lgamma(npop - ns + 1))
    )
    return math.exp(logc)


def _hypgeomdist(args):
    ks = _num(_arg(args, 0))
    ns = _num(_arg(args, 1))
    ms = _num(_arg(args, 2))
    npop = _num(_arg(args, 3))
    if ks is None or ns is None or ms is None or npop is None:
        return CellError(CellError.VALUE)
    cumulative = _truthy(_arg(args, 4, False))
    k = int(math.floor(ks))
    ns = int(math.floor(ns))
    m = int(math.floor(ms))
    npop = int(math.floor(npop))
    if k < 0 or ns < 0 or m < 0 or npop < 0 or ns > npop or m > npop or k > ns or k > m:
        return CellError(CellError.NUM)
    try:
        if not cumulative:
            return _hypgeom_pmf(k, ns, m, npop)
        return sum(_hypgeom_pmf(i, ns, m, npop) for i in range(0, k + 1))
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


# ---------------------------------------------------------------------------
# Continuous distributions
# ---------------------------------------------------------------------------


def _expondist(args):
    x = _num(_arg(args, 0))
    lam = _num(_arg(args, 1))
    if x is None or lam is None:
        return CellError(CellError.VALUE)
    if len(args) < 3:
        return CellError(CellError.NA)
    cumulative = _truthy(_arg(args, 2))
    if x < 0 or lam <= 0:
        return CellError(CellError.NUM)
    try:
        if cumulative:
            return 1.0 - math.exp(-lam * x)
        return lam * math.exp(-lam * x)
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _gamma_cdf(x: float, a: float, b: float) -> float:
    return _gammp(a, x / b)


def _gamma_pdf(x: float, a: float, b: float) -> float:
    if x < 0:
        return 0.0
    if x == 0.0:
        return 0.0 if a > 1 else (1.0 / b if a == 1 else math.inf)
    return math.exp((a - 1.0) * math.log(x) - x / b - a * math.log(b) - math.lgamma(a))


def _gammadist(args):
    x = _num(_arg(args, 0))
    a = _num(_arg(args, 1))
    b = _num(_arg(args, 2))
    if x is None or a is None or b is None:
        return CellError(CellError.VALUE)
    if len(args) < 4:
        return CellError(CellError.NA)
    cumulative = _truthy(_arg(args, 3))
    if x < 0 or a <= 0 or b <= 0:
        return CellError(CellError.NUM)
    try:
        return _gamma_cdf(x, a, b) if cumulative else _gamma_pdf(x, a, b)
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _gammainv(args):
    p = _num(_arg(args, 0))
    a = _num(_arg(args, 1))
    b = _num(_arg(args, 2))
    if p is None or a is None or b is None:
        return CellError(CellError.VALUE)
    if not (0.0 <= p < 1.0) or a <= 0 or b <= 0:
        return CellError(CellError.NUM)
    if p == 0.0:
        return 0.0
    try:
        # Bracket then bisect on the standardized (beta=1) variable.
        hi = 1.0
        while _gammp(a, hi) < p:
            hi *= 2.0
            if hi > 1e18:
                return CellError(CellError.NUM)
        t = _bisect_cdf(lambda z: _gammp(a, z), p, 0.0, hi)
        return t * b
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _beta_scale(x, a1, a2):
    return (x - a1) / (a2 - a1)


def _betadist(args):
    x = _num(_arg(args, 0))
    a = _num(_arg(args, 1))
    b = _num(_arg(args, 2))
    if x is None or a is None or b is None:
        return CellError(CellError.VALUE)
    cumulative = _truthy(_arg(args, 3, True))
    lo = _num(_arg(args, 4, 0.0))
    hi = _num(_arg(args, 5, 1.0))
    if lo is None or hi is None or a <= 0 or b <= 0 or hi <= lo:
        return CellError(CellError.NUM)
    if x < lo or x > hi:
        return CellError(CellError.NUM)
    y = _beta_scale(x, lo, hi)
    try:
        if cumulative:
            return _betai(a, b, y)
        # scaled pdf
        if y <= 0.0 or y >= 1.0:
            edge = (y <= 0.0 and a < 1) or (y >= 1.0 and b < 1)
            if edge:
                return math.inf
            return 0.0
        logpdf = (
            (a - 1.0) * math.log(y)
            + (b - 1.0) * math.log1p(-y)
            + math.lgamma(a + b)
            - math.lgamma(a)
            - math.lgamma(b)
        )
        return math.exp(logpdf) / (hi - lo)
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _betainv(args):
    p = _num(_arg(args, 0))
    a = _num(_arg(args, 1))
    b = _num(_arg(args, 2))
    if p is None or a is None or b is None:
        return CellError(CellError.VALUE)
    lo = _num(_arg(args, 3, 0.0))
    hi = _num(_arg(args, 4, 1.0))
    if lo is None or hi is None or not (0.0 <= p <= 1.0) or a <= 0 or b <= 0 or hi <= lo:
        return CellError(CellError.NUM)
    try:
        y = _bisect_cdf(lambda z: _betai(a, b, z), p, 0.0, 1.0)
        return lo + y * (hi - lo)
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _weibull(args):
    x = _num(_arg(args, 0))
    a = _num(_arg(args, 1))
    b = _num(_arg(args, 2))
    if x is None or a is None or b is None:
        return CellError(CellError.VALUE)
    if len(args) < 4:
        return CellError(CellError.NA)
    cumulative = _truthy(_arg(args, 3))
    if x < 0 or a <= 0 or b <= 0:
        return CellError(CellError.NUM)
    try:
        if cumulative:
            return 1.0 - math.exp(-((x / b) ** a))
        return (a / b) * ((x / b) ** (a - 1.0)) * math.exp(-((x / b) ** a))
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _lognormdist(args):
    x = _num(_arg(args, 0))
    mean = _num(_arg(args, 1))
    sd = _num(_arg(args, 2))
    if x is None or mean is None or sd is None:
        return CellError(CellError.VALUE)
    cumulative = _truthy(_arg(args, 3, True))
    if sd <= 0 or x <= 0:
        return CellError(CellError.NUM)
    try:
        z = (math.log(x) - mean) / sd
        if cumulative:
            return _phi(z)
        return _norm_pdf_std(z) / (x * sd)
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _loginv(args):
    p = _num(_arg(args, 0))
    mean = _num(_arg(args, 1))
    sd = _num(_arg(args, 2))
    if p is None or mean is None or sd is None:
        return CellError(CellError.VALUE)
    if not (0.0 < p < 1.0) or sd <= 0:
        return CellError(CellError.NUM)
    try:
        return math.exp(mean + sd * _norm_ppf_std(p))
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _phi_fn(args):
    """PHI(x) — standard normal probability density."""
    x = _num(_arg(args, 0))
    if x is None:
        return CellError(CellError.VALUE)
    return _norm_pdf_std(x)


def _gauss(args):
    """GAUSS(z) — Phi(z) - 0.5."""
    z = _num(_arg(args, 0))
    if z is None:
        return CellError(CellError.VALUE)
    return _phi(z) - 0.5


# ---------------------------------------------------------------------------
# Correlation / regression extras
# ---------------------------------------------------------------------------


def _paired_numbers(a1, a2):
    """Return (xs, ys) as equal-length numeric lists, or None on mismatch."""
    if not isinstance(a1, (RangeValue, list)):
        a1 = [a1]
    if not isinstance(a2, (RangeValue, list)):
        a2 = [a2]
    xs = a1.flat() if isinstance(a1, RangeValue) else _flatten([a1])
    ys = a2.flat() if isinstance(a2, RangeValue) else _flatten([a2])
    if len(xs) != len(ys):
        return None
    px, py = [], []
    for xv, yv in zip(xs, ys):
        xn, yn = _try_num(xv), _try_num(yv)
        if xn is not None and yn is not None and not isinstance(xv, str) and not isinstance(yv, str):
            px.append(xn)
            py.append(yn)
    return px, py


def _steyx(args):
    """STEYX(known_ys, known_xs) — standard error of the predicted y."""
    pair = _paired_numbers(_arg(args, 0), _arg(args, 1))
    if pair is None:
        return CellError(CellError.NA)
    ys, xs = pair
    n = len(xs)
    if n < 3:
        return CellError(CellError.DIV0)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return CellError(CellError.DIV0)
    try:
        val = (syy - sxy * sxy / sxx) / (n - 2)
        return math.sqrt(max(val, 0.0))
    except (ValueError, ZeroDivisionError):
        return CellError(CellError.DIV0)


def _pearson(args):
    """PEARSON(array1, array2) — Pearson correlation coefficient."""
    pair = _paired_numbers(_arg(args, 0), _arg(args, 1))
    if pair is None:
        return CellError(CellError.NA)
    xs, ys = pair
    n = len(xs)
    if n < 1:
        return CellError(CellError.DIV0)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom = math.sqrt(sxx * syy)
    if denom == 0:
        return CellError(CellError.DIV0)
    return sxy / denom


def _fisher(args):
    x = _num(_arg(args, 0))
    if x is None:
        return CellError(CellError.VALUE)
    if not (-1.0 < x < 1.0):
        return CellError(CellError.NUM)
    return math.atanh(x)


def _fisherinv(args):
    y = _num(_arg(args, 0))
    if y is None:
        return CellError(CellError.VALUE)
    return math.tanh(y)


def _standardize(args):
    x = _num(_arg(args, 0))
    mean = _num(_arg(args, 1))
    sd = _num(_arg(args, 2))
    if x is None or mean is None or sd is None:
        return CellError(CellError.VALUE)
    if sd <= 0:
        return CellError(CellError.NUM)
    return (x - mean) / sd


# ---------------------------------------------------------------------------
# Descriptive extras
# ---------------------------------------------------------------------------


def _devsq(args):
    nums = _numbers(args)
    if not nums:
        return 0.0
    m = sum(nums) / len(nums)
    return sum((v - m) ** 2 for v in nums)


def _avedev(args):
    nums = _numbers(args)
    if not nums:
        return CellError(CellError.NUM)
    m = sum(nums) / len(nums)
    return sum(abs(v - m) for v in nums) / len(nums)


def _averagea(args):
    """AVERAGEA — text -> 0, TRUE -> 1, FALSE -> 0, blanks ignored."""
    flat = _flatten(args)
    total = 0.0
    count = 0
    for v in flat:
        if v is None:
            continue
        if isinstance(v, CellError):
            return v
        if isinstance(v, bool):
            total += 1.0 if v else 0.0
            count += 1
        elif isinstance(v, (int, float)):
            total += float(v)
            count += 1
        elif isinstance(v, str):
            if v == "":
                continue
            total += 0.0
            count += 1
    if count == 0:
        return CellError(CellError.DIV0)
    return total / count


def _trimmean(args):
    """TRIMMEAN(array, percent) — mean after trimming percent of the data."""
    arr = _arg(args, 0)
    pct = _num(_arg(args, 1))
    if pct is None:
        return CellError(CellError.VALUE)
    if not (0.0 <= pct < 1.0):
        return CellError(CellError.NUM)
    nums = sorted(_numbers([arr]))
    n = len(nums)
    if n == 0:
        return CellError(CellError.NUM)
    trim = int(math.floor(n * pct))
    trim -= trim % 2  # round down to even, split top/bottom
    k = trim // 2
    kept = nums[k: n - k] if k > 0 else nums
    if not kept:
        return CellError(CellError.NUM)
    return sum(kept) / len(kept)


def _percentrank(args):
    """PERCENTRANK / PERCENTRANK.INC(array, x, [significance=3])."""
    arr = _arg(args, 0)
    x = _num(_arg(args, 1))
    if x is None:
        return CellError(CellError.VALUE)
    sig = _num(_arg(args, 2, 3.0))
    sig = 3 if sig is None else max(1, int(sig))
    nums = sorted(_numbers([arr]))
    n = len(nums)
    if n == 0:
        return CellError(CellError.NUM)
    if x < nums[0] or x > nums[-1]:
        return CellError(CellError.NA)
    if n == 1:
        return _trunc_sig(1.0, sig)
    # find bracketing indices
    if x <= nums[0]:
        rank = 0.0
    elif x >= nums[-1]:
        rank = float(n - 1)
    else:
        lo = 0
        while lo < n - 1 and nums[lo + 1] <= x:
            lo += 1
        if nums[lo] == x:
            # first exact match position
            rank = float(lo)
        else:
            # interpolate between nums[lo] and nums[lo+1]
            frac = (x - nums[lo]) / (nums[lo + 1] - nums[lo])
            rank = lo + frac
    result = rank / (n - 1)
    return _trunc_sig(result, sig)


def _trunc_sig(value: float, sig: int) -> float:
    factor = 10 ** sig
    return math.floor(value * factor) / factor


def _rank_common(args, average: bool):
    number = _num(_arg(args, 0))
    ref = _arg(args, 1)
    if number is None:
        return CellError(CellError.VALUE)
    order = _num(_arg(args, 2, 0.0)) or 0.0
    nums = _numbers([ref])
    if number not in nums:
        return CellError(CellError.NA)
    ascending = order != 0.0
    ordered = sorted(nums) if ascending else sorted(nums, reverse=True)
    # positions (1-based) of all equal values
    positions = [i + 1 for i, v in enumerate(ordered) if v == number]
    if not positions:
        return CellError(CellError.NA)
    if average:
        return sum(positions) / len(positions)
    return float(positions[0])


def _rank_eq(args):
    return _rank_common(args, average=False)


def _rank_avg(args):
    return _rank_common(args, average=True)


# ---------------------------------------------------------------------------
# Conditional multi-criteria aggregates
# ---------------------------------------------------------------------------


def _as_range_list(arg) -> list | None:
    if isinstance(arg, RangeValue):
        return arg.flat()
    if isinstance(arg, list):
        return _flatten([arg])
    return [arg]


def _qualifying_indices(crit_pairs) -> list[int] | CellError:
    """Return row indices where every (crit_range, criterion) predicate holds."""
    ranges = []
    preds = []
    length = None
    for crange, crit in crit_pairs:
        vals = _as_range_list(crange)
        if vals is None:
            return CellError(CellError.VALUE)
        if length is None:
            length = len(vals)
        elif len(vals) != length:
            return CellError(CellError.VALUE)
        ranges.append(vals)
        preds.append(make_predicate(crit))
    if length is None:
        return []
    out = []
    for i in range(length):
        if all(preds[k](ranges[k][i]) for k in range(len(preds))):
            out.append(i)
    return out


def _pairs_from(args, start: int):
    rest = args[start:]
    return list(zip(rest[0::2], rest[1::2]))


# Below this many criteria cells (summed across the criteria ranges) the pure-
# Python loop wins: the numpy array round-trip isn't worth it. Mirrors the
# aggregate accelerator's _ACCEL_MIN_CELLS in abax.core.functions.builtins.
_ACCEL_MIN_CELLS = 4096


def _ifs_criteria(pairs):
    """Prepare the criteria side of a ``*IFS`` call for the numpy accelerator.

    Returns ``(crit_grids, ops_thresholds)`` when *every* criteria range is a
    ``RangeValue`` and *every* criterion is a numeric comparison (per
    :func:`numeric_criterion`), and the pool clears :data:`_ACCEL_MIN_CELLS`;
    otherwise ``None`` so the caller keeps the exact stdlib predicate loop (this
    is what makes text, wildcard and mixed/blank/error inputs fall back). The
    grids are handed to the kernel raw -- it does the finite-numeric / equal-length
    gating and bails on any dirty block."""
    if not pairs:
        return None
    if aggregate_accelerator() is None:
        return None
    grids = []
    ops = []
    cells = 0
    for crange, crit in pairs:
        if not isinstance(crange, RangeValue):
            return None
        spec = numeric_criterion(crit)
        if spec is None:
            return None                 # text/wildcard criterion -> stdlib loop
        grids.append(crange.grid)
        ops.append(spec)
        cells += crange.nrows * crange.ncols
    if cells < _ACCEL_MIN_CELLS:
        return None
    return grids, ops


def _accel(name):
    """Fetch a named kernel off the registered accelerator object, or ``None``.

    The engine hangs the criteria kernels (``countifs`` / ``sumifs`` /
    ``averageifs``) as attributes of the one accelerator callable in the
    ``abax._runtime`` seam; core reads them through here and never imports numpy."""
    accel = aggregate_accelerator()
    return getattr(accel, name, None) if accel is not None else None


def _countifs(args):
    pairs = _pairs_from(args, 0)
    if not pairs:
        return CellError(CellError.VALUE)
    prep = _ifs_criteria(pairs)
    if prep is not None:
        kernel = _accel("countifs")
        if kernel is not None:
            handled, value = kernel(prep[0], prep[1])
            if handled:
                return value
    idx = _qualifying_indices(pairs)
    if isinstance(idx, CellError):
        return idx
    return float(len(idx))


def _sumifs(args):
    value_arg = _arg(args, 0)
    sum_range = _as_range_list(value_arg)
    if sum_range is None:
        return CellError(CellError.VALUE)
    pairs = _pairs_from(args, 1)
    if not pairs:
        return CellError(CellError.VALUE)
    if isinstance(value_arg, RangeValue):
        prep = _ifs_criteria(pairs)
        if prep is not None:
            kernel = _accel("sumifs")
            if kernel is not None:
                handled, value = kernel(value_arg.grid, prep[0], prep[1])
                if handled:
                    return value
    idx = _qualifying_indices(pairs)
    if isinstance(idx, CellError):
        return idx
    total = 0.0
    for i in idx:
        if i < len(sum_range):
            n = _try_num(sum_range[i])
            if n is not None and not isinstance(sum_range[i], str):
                total += n
    return total


def _averageifs(args):
    value_arg = _arg(args, 0)
    avg_range = _as_range_list(value_arg)
    if avg_range is None:
        return CellError(CellError.VALUE)
    pairs = _pairs_from(args, 1)
    if not pairs:
        return CellError(CellError.VALUE)
    if isinstance(value_arg, RangeValue):
        prep = _ifs_criteria(pairs)
        if prep is not None:
            kernel = _accel("averageifs")
            if kernel is not None:
                handled, value = kernel(value_arg.grid, prep[0], prep[1])
                if handled:
                    return value if value is not None else CellError(CellError.DIV0)
    idx = _qualifying_indices(pairs)
    if isinstance(idx, CellError):
        return idx
    total = 0.0
    count = 0
    for i in idx:
        if i < len(avg_range):
            n = _try_num(avg_range[i])
            if n is not None and not isinstance(avg_range[i], str):
                total += n
                count += 1
    if count == 0:
        return CellError(CellError.DIV0)
    return total / count


def _maxifs(args):
    return _minmaxifs(args, want_max=True)


def _minifs(args):
    return _minmaxifs(args, want_max=False)


def _minmaxifs(args, want_max: bool):
    target = _as_range_list(_arg(args, 0))
    if target is None:
        return CellError(CellError.VALUE)
    pairs = _pairs_from(args, 1)
    if not pairs:
        return CellError(CellError.VALUE)
    idx = _qualifying_indices(pairs)
    if isinstance(idx, CellError):
        return idx
    vals = []
    for i in idx:
        if i < len(target):
            n = _try_num(target[i])
            if n is not None and not isinstance(target[i], str):
                vals.append(n)
    if not vals:
        return 0.0
    return max(vals) if want_max else min(vals)


# ---------------------------------------------------------------------------
# Local truthiness (avoid importing the private helper name churn)
# ---------------------------------------------------------------------------


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1")
    return bool(v)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_REGISTRY = {
    # discrete distributions
    "BINOMDIST": _binomdist,
    "BINOM.DIST": _binomdist,
    "BINOM.INV": _binominv,
    "CRITBINOM": _binominv,
    "NEGBINOMDIST": _negbinomdist,
    "NEGBINOM.DIST": _negbinomdist,
    "POISSON": _poisson,
    "POISSON.DIST": _poisson,
    "HYPGEOMDIST": _hypgeomdist,
    "HYPGEOM.DIST": _hypgeomdist,
    # continuous distributions
    "EXPONDIST": _expondist,
    "EXPON.DIST": _expondist,
    "GAMMADIST": _gammadist,
    "GAMMA.DIST": _gammadist,
    "GAMMAINV": _gammainv,
    "GAMMA.INV": _gammainv,
    "BETADIST": _betadist,
    "BETA.DIST": _betadist,
    "BETAINV": _betainv,
    "BETA.INV": _betainv,
    "WEIBULL": _weibull,
    "WEIBULL.DIST": _weibull,
    "LOGNORMDIST": _lognormdist,
    "LOGNORM.DIST": _lognormdist,
    "LOGINV": _loginv,
    "LOGNORM.INV": _loginv,
    "PHI": _phi_fn,
    "GAUSS": _gauss,
    # correlation / regression
    "STEYX": _steyx,
    "PEARSON": _pearson,
    "FISHER": _fisher,
    "FISHERINV": _fisherinv,
    "STANDARDIZE": _standardize,
    # descriptive extras
    "DEVSQ": _devsq,
    "AVEDEV": _avedev,
    "AVERAGEA": _averagea,
    "TRIMMEAN": _trimmean,
    "PERCENTRANK": _percentrank,
    "PERCENTRANK.INC": _percentrank,
    "RANK.EQ": _rank_eq,
    "RANK.AVG": _rank_avg,
    # conditional aggregates
    "COUNTIFS": _countifs,
    "SUMIFS": _sumifs,
    "AVERAGEIFS": _averageifs,
    "MAXIFS": _maxifs,
    "MINIFS": _minifs,
}


SIGNATURES = {
    "BINOMDIST": "BINOMDIST(number_s, trials, prob_s, cumulative)",
    "BINOM.DIST": "BINOM.DIST(number_s, trials, prob_s, cumulative)",
    "BINOM.INV": "BINOM.INV(trials, prob_s, alpha)",
    "CRITBINOM": "CRITBINOM(trials, prob_s, alpha)",
    "NEGBINOMDIST": "NEGBINOMDIST(number_f, number_s, prob_s, [cumulative])",
    "NEGBINOM.DIST": "NEGBINOM.DIST(number_f, number_s, prob_s, [cumulative])",
    "POISSON": "POISSON(x, mean, cumulative)",
    "POISSON.DIST": "POISSON.DIST(x, mean, cumulative)",
    "HYPGEOMDIST": "HYPGEOMDIST(sample_s, number_sample, population_s, number_pop, [cumulative])",
    "HYPGEOM.DIST": "HYPGEOM.DIST(sample_s, number_sample, population_s, number_pop, [cumulative])",
    "EXPONDIST": "EXPONDIST(x, lambda, cumulative)",
    "EXPON.DIST": "EXPON.DIST(x, lambda, cumulative)",
    "GAMMADIST": "GAMMADIST(x, alpha, beta, cumulative)",
    "GAMMA.DIST": "GAMMA.DIST(x, alpha, beta, cumulative)",
    "GAMMAINV": "GAMMAINV(probability, alpha, beta)",
    "GAMMA.INV": "GAMMA.INV(probability, alpha, beta)",
    "BETADIST": "BETADIST(x, alpha, beta, [cumulative], [A], [B])",
    "BETA.DIST": "BETA.DIST(x, alpha, beta, [cumulative], [A], [B])",
    "BETAINV": "BETAINV(probability, alpha, beta, [A], [B])",
    "BETA.INV": "BETA.INV(probability, alpha, beta, [A], [B])",
    "WEIBULL": "WEIBULL(x, alpha, beta, cumulative)",
    "WEIBULL.DIST": "WEIBULL.DIST(x, alpha, beta, cumulative)",
    "LOGNORMDIST": "LOGNORMDIST(x, mean, standard_dev, [cumulative])",
    "LOGNORM.DIST": "LOGNORM.DIST(x, mean, standard_dev, [cumulative])",
    "LOGINV": "LOGINV(probability, mean, standard_dev)",
    "LOGNORM.INV": "LOGNORM.INV(probability, mean, standard_dev)",
    "PHI": "PHI(x)",
    "GAUSS": "GAUSS(z)",
    "STEYX": "STEYX(known_ys, known_xs)",
    "PEARSON": "PEARSON(array1, array2)",
    "FISHER": "FISHER(x)",
    "FISHERINV": "FISHERINV(y)",
    "STANDARDIZE": "STANDARDIZE(x, mean, standard_dev)",
    "DEVSQ": "DEVSQ(number1, [number2], ...)",
    "AVEDEV": "AVEDEV(number1, [number2], ...)",
    "AVERAGEA": "AVERAGEA(value1, [value2], ...)",
    "TRIMMEAN": "TRIMMEAN(array, percent)",
    "PERCENTRANK": "PERCENTRANK(array, x, [significance])",
    "PERCENTRANK.INC": "PERCENTRANK.INC(array, x, [significance])",
    "RANK.EQ": "RANK.EQ(number, ref, [order])",
    "RANK.AVG": "RANK.AVG(number, ref, [order])",
    "COUNTIFS": "COUNTIFS(criteria_range1, criteria1, ...)",
    "SUMIFS": "SUMIFS(sum_range, criteria_range1, criteria1, ...)",
    "AVERAGEIFS": "AVERAGEIFS(average_range, criteria_range1, criteria1, ...)",
    "MAXIFS": "MAXIFS(max_range, criteria_range1, criteria1, ...)",
    "MINIFS": "MINIFS(min_range, criteria_range1, criteria1, ...)",
}


def register(functions: dict) -> None:
    """Merge the distribution/statistics functions into the engine's table."""
    functions.update(_REGISTRY)
