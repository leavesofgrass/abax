"""Pure-Python statistics: descriptive stats, distributions, hypothesis tests.

A dependency-free statistics toolkit for abax. Everything is computed in IEEE
doubles via the stdlib :mod:`math` module only (no numpy/scipy). Where numerical
accuracy matters we lean on :func:`math.erf` (normal CDF), :func:`math.lgamma`
(the log-gamma used by the incomplete beta), and :func:`math.fsum` (compensated
summation for means and sums of squares).

Three families:

* **Descriptive** -- :func:`mean`, :func:`median`, :func:`mode`,
  :func:`variance`, :func:`stdev`, :func:`quantile`/:func:`percentile`,
  :func:`iqr`, :func:`skewness`, :func:`kurtosis`, :func:`covariance`,
  :func:`correlation`, :func:`correlation_matrix`, :func:`describe`.
* **Distributions** -- the normal PDF/CDF/PPF and the Student-t and F CDFs. The
  t and F CDFs are expressed through the regularized incomplete beta function
  :func:`betai`, implemented with the classic Lentz continued fraction
  (:func:`_betacf`) plus :func:`math.lgamma`.
* **Hypothesis tests** -- one-sample / independent (Welch by default) / paired
  t-tests, one-way ANOVA, the chi-square goodness-of-fit and contingency tests,
  and a mean confidence interval. Tests return ``(statistic, p_value)`` with a
  two-sided ``p`` where applicable.

Bad arguments (empty input, length mismatch, ``q``/``p`` out of range,
``df <= 0``, fewer than two groups) raise :class:`StatsError` rather than
returning a bogus number.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence


class StatsError(Exception):
    """Raised when a statistics routine cannot produce a valid result."""


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _floats(xs: Sequence[float], *, minlen: int = 1, name: str = "data") -> list[float]:
    """Coerce ``xs`` to a list of floats, requiring at least ``minlen`` items."""
    out = [float(x) for x in xs]
    if len(out) < minlen:
        raise StatsError(f"{name} must have at least {minlen} value(s)")
    return out


# --------------------------------------------------------------------------- #
# descriptive statistics                                                       #
# --------------------------------------------------------------------------- #
def mean(xs: Sequence[float]) -> float:
    """Arithmetic mean of ``xs`` (compensated summation). ``len(xs) >= 1``."""
    data = _floats(xs)
    return math.fsum(data) / len(data)


def median(xs: Sequence[float]) -> float:
    """Median of ``xs`` -- average of the two middle values when even-length."""
    data = sorted(_floats(xs))
    n = len(data)
    mid = n // 2
    if n % 2 == 1:
        return data[mid]
    return 0.5 * (data[mid - 1] + data[mid])


def mode(xs: Sequence[float]) -> float:
    """Most-frequent value of ``xs``; ties broken by the smallest value."""
    data = _floats(xs)
    counts: dict[float, int] = {}
    for x in data:
        counts[x] = counts.get(x, 0) + 1
    best = max(counts.values())
    return min(v for v, c in counts.items() if c == best)


def variance(xs: Sequence[float], sample: bool = True) -> float:
    """Variance of ``xs``: sample (``n-1``) by default, else population (``n``)."""
    minlen = 2 if sample else 1
    data = _floats(xs, minlen=minlen)
    n = len(data)
    m = math.fsum(data) / n
    ss = math.fsum((x - m) ** 2 for x in data)
    denom = (n - 1) if sample else n
    return ss / denom


def stdev(xs: Sequence[float], sample: bool = True) -> float:
    """Standard deviation: the square root of :func:`variance`."""
    return math.sqrt(variance(xs, sample=sample))


def quantile(xs: Sequence[float], q: float) -> float:
    """``q``-quantile (``0 <= q <= 1``) by linear interpolation between ranks."""
    if not (0.0 <= q <= 1.0):
        raise StatsError("q must be in [0, 1]")
    data = sorted(_floats(xs))
    n = len(data)
    if n == 1:
        return data[0]
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return data[lo]
    frac = pos - lo
    return data[lo] * (1.0 - frac) + data[hi] * frac


def percentile(xs: Sequence[float], p: float) -> float:
    """``p``-th percentile (``p`` in ``0..100``); thin wrapper over :func:`quantile`."""
    if not (0.0 <= p <= 100.0):
        raise StatsError("p must be in [0, 100]")
    return quantile(xs, p / 100.0)


def iqr(xs: Sequence[float]) -> float:
    """Interquartile range: ``Q3 - Q1`` (75th minus 25th percentile)."""
    return quantile(xs, 0.75) - quantile(xs, 0.25)


def skewness(xs: Sequence[float]) -> float:
    """Sample (Fisher-Pearson) skewness; needs ``len(xs) >= 3``."""
    data = _floats(xs, minlen=3)
    n = len(data)
    m = math.fsum(data) / n
    s = stdev(data, sample=True)
    if s == 0.0:
        raise StatsError("skewness undefined for zero variance")
    g = math.fsum(((x - m) / s) ** 3 for x in data)
    return (n / ((n - 1) * (n - 2))) * g


def kurtosis(xs: Sequence[float], excess: bool = True) -> float:
    """Sample kurtosis; ``excess=True`` subtracts 3. Needs ``len(xs) >= 4``."""
    data = _floats(xs, minlen=4)
    n = len(data)
    m = math.fsum(data) / n
    s = stdev(data, sample=True)
    if s == 0.0:
        raise StatsError("kurtosis undefined for zero variance")
    g = math.fsum(((x - m) / s) ** 4 for x in data)
    num = n * (n + 1) * g
    biased = num / ((n - 1) * (n - 2) * (n - 3))
    correction = 3.0 * (n - 1) ** 2 / ((n - 2) * (n - 3))
    excess_kurt = biased - correction
    return excess_kurt if excess else excess_kurt + 3.0


def covariance(xs: Sequence[float], ys: Sequence[float], sample: bool = True) -> float:
    """Covariance of paired ``xs``/``ys`` (sample by default)."""
    minlen = 2 if sample else 1
    dx = _floats(xs, minlen=minlen, name="xs")
    dy = _floats(ys, minlen=minlen, name="ys")
    if len(dx) != len(dy):
        raise StatsError("xs and ys must have equal length")
    n = len(dx)
    mx = math.fsum(dx) / n
    my = math.fsum(dy) / n
    cov = math.fsum((a - mx) * (b - my) for a, b in zip(dx, dy))
    denom = (n - 1) if sample else n
    return cov / denom


def correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Pearson correlation coefficient ``r`` of paired ``xs``/``ys``."""
    dx = _floats(xs, minlen=2, name="xs")
    dy = _floats(ys, minlen=2, name="ys")
    if len(dx) != len(dy):
        raise StatsError("xs and ys must have equal length")
    sx = stdev(dx, sample=True)
    sy = stdev(dy, sample=True)
    if sx == 0.0 or sy == 0.0:
        raise StatsError("correlation undefined for zero variance")
    return covariance(dx, dy, sample=True) / (sx * sy)


def correlation_matrix(columns: list[list[float]]) -> list[list[float]]:
    """Symmetric Pearson correlation matrix over the given equal-length columns."""
    if len(columns) < 1:
        raise StatsError("need at least one column")
    k = len(columns)
    n = len(columns[0])
    for c in columns:
        if len(c) != n:
            raise StatsError("all columns must have equal length")
    out = [[1.0] * k for _ in range(k)]
    for i in range(k):
        for j in range(i + 1, k):
            r = correlation(columns[i], columns[j])
            out[i][j] = r
            out[j][i] = r
    return out


def describe(xs: Sequence[float]) -> dict:
    """Summary dict: ``count mean std min q1 median q3 max`` for ``xs``."""
    data = _floats(xs)
    return {
        "count": len(data),
        "mean": mean(data),
        "std": stdev(data, sample=True) if len(data) >= 2 else 0.0,
        "min": min(data),
        "q1": quantile(data, 0.25),
        "median": median(data),
        "q3": quantile(data, 0.75),
        "max": max(data),
    }


# --------------------------------------------------------------------------- #
# special functions: regularized incomplete beta                              #
# --------------------------------------------------------------------------- #
def _betacf(a: float, b: float, x: float, max_iter: int = 300, eps: float = 1e-14) -> float:
    """Continued fraction for the incomplete beta (Lentz's algorithm)."""
    tiny = 1e-30
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            return h
    raise StatsError("betacf failed to converge")


def betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function ``I_x(a, b)`` for ``0 <= x <= 1``."""
    if a <= 0.0 or b <= 0.0:
        raise StatsError("betai requires a > 0 and b > 0")
    if x < 0.0 or x > 1.0:
        raise StatsError("betai requires 0 <= x <= 1")
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


# --------------------------------------------------------------------------- #
# distributions                                                                #
# --------------------------------------------------------------------------- #
def normal_pdf(x: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    """Probability density of ``N(mu, sigma^2)`` at ``x``."""
    if sigma <= 0.0:
        raise StatsError("sigma must be positive")
    z = (x - mu) / sigma
    return math.exp(-0.5 * z * z) / (sigma * math.sqrt(2.0 * math.pi))


def normal_cdf(x: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    """Cumulative distribution of ``N(mu, sigma^2)`` via ``0.5*(1+erf(...))``."""
    if sigma <= 0.0:
        raise StatsError("sigma must be positive")
    z = (x - mu) / (sigma * math.sqrt(2.0))
    return 0.5 * (1.0 + math.erf(z))


def normal_ppf(p: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    """Inverse normal CDF (quantile) using the Acklam rational approximation."""
    if not (0.0 < p < 1.0):
        raise StatsError("p must be in (0, 1)")
    if sigma <= 0.0:
        raise StatsError("sigma must be positive")

    # Acklam's algorithm coefficients.
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]

    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        z = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    elif p <= phigh:
        q = p - 0.5
        r = q * q
        z = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        z = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)

    # One Halley refinement step against the exact CDF.
    e = normal_cdf(z) - p
    u = e * math.sqrt(2.0 * math.pi) * math.exp(0.5 * z * z)
    z = z - u / (1.0 + 0.5 * z * u)
    return mu + sigma * z


def t_cdf(t: float, df: float) -> float:
    """Student-t CDF with ``df`` degrees of freedom via the incomplete beta."""
    if df <= 0.0:
        raise StatsError("df must be positive")
    x = df / (df + t * t)
    ib = betai(df / 2.0, 0.5, x)
    if t >= 0.0:
        return 1.0 - 0.5 * ib
    return 0.5 * ib


def f_cdf(x: float, d1: float, d2: float) -> float:
    """F-distribution CDF with ``(d1, d2)`` degrees of freedom via incomplete beta."""
    if d1 <= 0.0 or d2 <= 0.0:
        raise StatsError("degrees of freedom must be positive")
    if x <= 0.0:
        return 0.0
    y = d1 * x / (d1 * x + d2)
    return betai(d1 / 2.0, d2 / 2.0, y)


# --------------------------------------------------------------------------- #
# hypothesis tests                                                             #
# --------------------------------------------------------------------------- #
def _two_sided_t_p(t: float, df: float) -> float:
    """Two-sided p-value for a t statistic: ``2*(1 - t_cdf(|t|, df))``."""
    return 2.0 * (1.0 - t_cdf(abs(t), df))


def t_test_1samp(xs: Sequence[float], popmean: float) -> tuple[float, float]:
    """One-sample t-test of ``mean(xs) == popmean``. Returns ``(t, p_two_sided)``."""
    data = _floats(xs, minlen=2)
    n = len(data)
    m = mean(data)
    s = stdev(data, sample=True)
    if s == 0.0:
        t = 0.0 if m == popmean else math.inf
    else:
        t = (m - popmean) / (s / math.sqrt(n))
    df = n - 1
    if not math.isfinite(t):
        return t, 0.0
    return t, _two_sided_t_p(t, df)


def t_test_ind(
    xs: Sequence[float], ys: Sequence[float], equal_var: bool = False
) -> tuple[float, float]:
    """Two independent-sample t-test (Welch by default). Returns ``(t, p)``."""
    dx = _floats(xs, minlen=2, name="xs")
    dy = _floats(ys, minlen=2, name="ys")
    n1, n2 = len(dx), len(dy)
    m1, m2 = mean(dx), mean(dy)
    v1, v2 = variance(dx, sample=True), variance(dy, sample=True)

    if equal_var:
        sp2 = ((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2)
        denom = math.sqrt(sp2 * (1.0 / n1 + 1.0 / n2))
        df = float(n1 + n2 - 2)
    else:
        se1 = v1 / n1
        se2 = v2 / n2
        denom = math.sqrt(se1 + se2)
        num = (se1 + se2) ** 2
        den = (se1 ** 2) / (n1 - 1) + (se2 ** 2) / (n2 - 1)
        df = num / den if den > 0.0 else float(n1 + n2 - 2)

    if denom == 0.0:
        t = 0.0 if m1 == m2 else math.inf
    else:
        t = (m1 - m2) / denom
    if not math.isfinite(t):
        return t, 0.0
    return t, _two_sided_t_p(t, df)


def t_test_paired(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    """Paired-sample t-test on the differences ``xs - ys``. Returns ``(t, p)``."""
    dx = _floats(xs, minlen=2, name="xs")
    dy = _floats(ys, minlen=2, name="ys")
    if len(dx) != len(dy):
        raise StatsError("xs and ys must have equal length")
    diffs = [a - b for a, b in zip(dx, dy)]
    return t_test_1samp(diffs, 0.0)


def anova_oneway(*groups: Sequence[float]) -> tuple[float, float]:
    """One-way ANOVA across ``groups`` (>= 2). Returns ``(F, p_value)``."""
    if len(groups) < 2:
        raise StatsError("anova needs at least two groups")
    data = [_floats(g, name="group") for g in groups]
    k = len(data)
    all_vals = [x for g in data for x in g]
    n = len(all_vals)
    if n <= k:
        raise StatsError("need more observations than groups")
    grand = math.fsum(all_vals) / n

    ss_between = math.fsum(len(g) * (mean(g) - grand) ** 2 for g in data)
    ss_within = math.fsum(
        math.fsum((x - mean(g)) ** 2 for x in g) for g in data
    )
    df_between = k - 1
    df_within = n - k
    ms_between = ss_between / df_between
    ms_within = ss_within / df_within
    if ms_within == 0.0:
        f = 0.0 if ss_between == 0.0 else math.inf
    else:
        f = ms_between / ms_within
    if not math.isfinite(f):
        return f, 0.0
    p = 1.0 - f_cdf(f, df_between, df_within)
    return f, p


def _chi_square_cdf(x: float, df: float) -> float:
    """Chi-square CDF via the regularized lower incomplete gamma (series/CF)."""
    if x <= 0.0:
        return 0.0
    return _gammainc_lower(df / 2.0, x / 2.0)


def _gammainc_lower(a: float, x: float) -> float:
    """Regularized lower incomplete gamma ``P(a, x)`` (Numerical Recipes split)."""
    if x < 0.0 or a <= 0.0:
        raise StatsError("invalid arguments to gammainc")
    if x == 0.0:
        return 0.0
    if x < a + 1.0:
        # Series representation.
        ap = a
        total = 1.0 / a
        delta = total
        for _ in range(1000):
            ap += 1.0
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * 1e-15:
                break
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # Continued fraction for the upper part, then complement.
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return 1.0 - q


def chi_square(
    observed: Sequence, expected: Optional[Sequence] = None
) -> tuple[float, float]:
    """Chi-square test.

    1-D ``observed`` (a flat list) runs a goodness-of-fit test; ``expected``
    defaults to a uniform distribution with the same total. A 2-D ``observed``
    (a list of equal-length rows) runs a test of independence on the
    contingency table (``expected`` is ignored and derived from the margins).
    Returns ``(chi2, p_value)``.
    """
    if len(observed) == 0:
        raise StatsError("observed must be non-empty")

    # Detect a 2-D contingency table.
    if isinstance(observed[0], (list, tuple)):
        rows = [[float(v) for v in row] for row in observed]
        ncols = len(rows[0])
        if ncols == 0:
            raise StatsError("contingency rows must be non-empty")
        for r in rows:
            if len(r) != ncols:
                raise StatsError("contingency rows must have equal length")
        nrows = len(rows)
        row_tot = [math.fsum(r) for r in rows]
        col_tot = [math.fsum(rows[i][j] for i in range(nrows)) for j in range(ncols)]
        grand = math.fsum(row_tot)
        if grand == 0.0:
            raise StatsError("contingency table total is zero")
        chi2 = 0.0
        for i in range(nrows):
            for j in range(ncols):
                exp = row_tot[i] * col_tot[j] / grand
                if exp > 0.0:
                    chi2 += (rows[i][j] - exp) ** 2 / exp
        df = (nrows - 1) * (ncols - 1)
        if df < 1:
            raise StatsError("contingency table needs >= 2 rows and >= 2 columns")
        p = 1.0 - _chi_square_cdf(chi2, df)
        return chi2, p

    # 1-D goodness-of-fit.
    obs = [float(v) for v in observed]
    k = len(obs)
    if k < 2:
        raise StatsError("goodness-of-fit needs at least two categories")
    if expected is None:
        total = math.fsum(obs)
        exp = [total / k] * k
    else:
        exp = [float(v) for v in expected]
        if len(exp) != k:
            raise StatsError("observed and expected must have equal length")
    chi2 = 0.0
    for o, e in zip(obs, exp):
        if e <= 0.0:
            raise StatsError("expected frequencies must be positive")
        chi2 += (o - e) ** 2 / e
    df = k - 1
    p = 1.0 - _chi_square_cdf(chi2, df)
    return chi2, p


def confidence_interval_mean(
    xs: Sequence[float], confidence: float = 0.95
) -> tuple[float, float]:
    """Two-sided ``confidence``-level CI for the population mean (t-based)."""
    if not (0.0 < confidence < 1.0):
        raise StatsError("confidence must be in (0, 1)")
    data = _floats(xs, minlen=2)
    n = len(data)
    m = mean(data)
    se = stdev(data, sample=True) / math.sqrt(n)
    df = n - 1
    alpha = 1.0 - confidence
    tcrit = _t_ppf(1.0 - alpha / 2.0, df)
    return m - tcrit * se, m + tcrit * se


def _t_ppf(p: float, df: float) -> float:
    """Inverse Student-t CDF by bisection on :func:`t_cdf`."""
    if not (0.0 < p < 1.0):
        raise StatsError("p must be in (0, 1)")
    if df <= 0.0:
        raise StatsError("df must be positive")
    lo, hi = -1e6, 1e6
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return 0.5 * (lo + hi)


# Public inverse/CDF wrappers used by the spreadsheet distribution functions.

def t_ppf(p: float, df: float) -> float:
    """Inverse Student-t CDF (quantile) with ``df`` degrees of freedom."""
    return _t_ppf(p, df)


def chi_square_cdf(x: float, df: float) -> float:
    """Chi-square CDF with ``df`` degrees of freedom."""
    return _chi_square_cdf(x, df)


def _ppf_bisect(cdf, p: float, lo: float, hi: float) -> float:
    """Invert a monotone CDF on a non-negative domain by expand-then-bisect."""
    if not (0.0 < p < 1.0):
        raise StatsError("p must be in (0, 1)")
    while cdf(hi) < p and hi < 1e13:
        hi *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if cdf(mid) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return 0.5 * (lo + hi)


def chi_square_ppf(p: float, df: float) -> float:
    """Inverse chi-square CDF (quantile) with ``df`` degrees of freedom."""
    if df <= 0.0:
        raise StatsError("df must be positive")
    return _ppf_bisect(lambda x: _chi_square_cdf(x, df), p, 0.0, 1.0)


def f_ppf(p: float, d1: float, d2: float) -> float:
    """Inverse F-distribution CDF (quantile) with ``(d1, d2)`` degrees of freedom."""
    if d1 <= 0.0 or d2 <= 0.0:
        raise StatsError("degrees of freedom must be positive")
    return _ppf_bisect(lambda x: f_cdf(x, d1, d2), p, 0.0, 1.0)
