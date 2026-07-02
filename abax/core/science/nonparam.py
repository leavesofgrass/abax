"""Pure-Python nonparametric and rank statistics.

A dependency-free companion to :mod:`abax.core.science.stats`. abax has strong
parametric tests (t-tests, ANOVA, chi-square) but no rank-based ones; this
module fills that gap without pulling in scipy. Everything is computed in IEEE
doubles via the stdlib :mod:`math` module only (no numpy/scipy).

Five two-sided tests, each returning a small namedtuple with the test statistic
plus a p-value:

* :func:`mann_whitney_u` -- the Mann-Whitney U (Wilcoxon rank-sum) test for two
  independent samples, with a normal approximation that applies the tie
  correction to the variance and a continuity correction to the z-score.
* :func:`wilcoxon_signed_rank` -- the Wilcoxon signed-rank test for paired
  samples: zero differences are dropped, ranks of the absolute differences are
  tie-averaged and tie-corrected, and the p-value comes from a
  continuity-corrected normal approximation.
* :func:`kruskal_wallis` -- the Kruskal-Wallis H test (nonparametric one-way
  ANOVA) across two or more groups, tie-corrected, with a chi-square p-value.
* :func:`spearman_rho` -- Spearman's rank correlation ``rho`` with a Student-t
  approximation on ``n - 2`` degrees of freedom.
* :func:`kendall_tau` -- Kendall's ``tau-b`` (tie-adjusted) with a
  normal-approximation p-value.

Ties are resolved with average (fractional) ranks throughout. Degenerate or
too-small inputs (empty groups, mismatched lengths, all-equal data where a
statistic is undefined) raise :class:`StatsError` rather than returning a bogus
number.
"""

from __future__ import annotations

import math
from collections import namedtuple
from typing import Sequence

from .stats import StatsError, chi_square_cdf, normal_cdf, t_cdf

# --------------------------------------------------------------------------- #
# result types                                                                 #
# --------------------------------------------------------------------------- #
MannWhitneyResult = namedtuple("MannWhitneyResult", ["statistic", "pvalue"])
WilcoxonResult = namedtuple("WilcoxonResult", ["statistic", "pvalue"])
KruskalResult = namedtuple("KruskalResult", ["statistic", "df", "pvalue"])
SpearmanResult = namedtuple("SpearmanResult", ["statistic", "pvalue"])
KendallResult = namedtuple("KendallResult", ["statistic", "pvalue"])


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _floats(xs: Sequence[float], *, minlen: int = 1, name: str = "data") -> list[float]:
    """Coerce ``xs`` to a list of floats, requiring at least ``minlen`` items."""
    out = [float(x) for x in xs]
    if len(out) < minlen:
        raise StatsError(f"{name} must have at least {minlen} value(s)")
    return out


def _average_ranks(values: Sequence[float]) -> list[float]:
    """Rank ``values`` ascending (ranks start at 1), averaging tied ranks."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        # Extend the run of equal values.
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        # Average of the ranks (1-based) spanning positions i..j.
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _tie_groups(values: Sequence[float]) -> list[int]:
    """Sizes of each group of tied values in ``values`` (order irrelevant)."""
    counts: dict[float, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return [c for c in counts.values() if c > 1]


def _two_sided_normal_p(z: float) -> float:
    """Two-sided p-value for a standard-normal z statistic."""
    return 2.0 * (1.0 - normal_cdf(abs(z)))


def _two_sided_t_p(t: float, df: float) -> float:
    """Two-sided p-value for a t statistic on ``df`` degrees of freedom."""
    return 2.0 * (1.0 - t_cdf(abs(t), df))


# --------------------------------------------------------------------------- #
# Mann-Whitney U (Wilcoxon rank-sum)                                           #
# --------------------------------------------------------------------------- #
def mann_whitney_u(a: Sequence[float], b: Sequence[float]) -> MannWhitneyResult:
    """Mann-Whitney U test for two independent samples.

    Returns ``(U, p)`` where ``U`` is the smaller of the two group U statistics
    and ``p`` is a two-sided normal-approximation p-value with the tie
    correction applied to the variance and a continuity correction of 0.5.
    """
    da = _floats(a, minlen=1, name="a")
    db = _floats(b, minlen=1, name="b")
    n1, n2 = len(da), len(db)

    combined = da + db
    ranks = _average_ranks(combined)
    r1 = math.fsum(ranks[:n1])

    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)

    n = n1 + n2
    mu = n1 * n2 / 2.0

    # Tie-corrected variance of U.
    tie_term = math.fsum(t * (t * t - 1.0) for t in _tie_groups(combined))
    var = (n1 * n2 / 12.0) * ((n + 1) - tie_term / (n * (n - 1)))
    if var <= 0.0:
        raise StatsError("Mann-Whitney U variance is zero (data all tied)")

    # Continuity correction toward the mean.
    z = (u - mu + 0.5) / math.sqrt(var) if u < mu else (u - mu - 0.5) / math.sqrt(var)
    return MannWhitneyResult(u, _two_sided_normal_p(z))


# --------------------------------------------------------------------------- #
# Wilcoxon signed-rank (paired)                                                #
# --------------------------------------------------------------------------- #
def wilcoxon_signed_rank(a: Sequence[float], b: Sequence[float]) -> WilcoxonResult:
    """Wilcoxon signed-rank test for paired samples.

    Ranks the absolute nonzero differences ``a - b`` (tie-averaged), sums the
    positive and negative ranks, and reports ``W`` (the smaller sum) with a
    two-sided, tie- and continuity-corrected normal-approximation p-value. Zero
    differences are dropped.
    """
    da = _floats(a, minlen=1, name="a")
    db = _floats(b, minlen=1, name="b")
    if len(da) != len(db):
        raise StatsError("a and b must have equal length")

    diffs = [x - y for x, y in zip(da, db) if x - y != 0.0]
    n = len(diffs)
    if n < 1:
        raise StatsError("Wilcoxon signed-rank needs at least one nonzero difference")

    abs_diffs = [abs(d) for d in diffs]
    ranks = _average_ranks(abs_diffs)
    w_plus = math.fsum(r for d, r in zip(diffs, ranks) if d > 0.0)
    w_minus = math.fsum(r for d, r in zip(diffs, ranks) if d < 0.0)
    w = min(w_plus, w_minus)

    mu = n * (n + 1) / 4.0
    tie_term = math.fsum(t * (t * t - 1.0) for t in _tie_groups(abs_diffs))
    var = n * (n + 1) * (2 * n + 1) / 24.0 - tie_term / 48.0
    if var <= 0.0:
        raise StatsError("Wilcoxon signed-rank variance is zero (data all tied)")

    z = (w - mu + 0.5) / math.sqrt(var) if w < mu else (w - mu - 0.5) / math.sqrt(var)
    return WilcoxonResult(w, _two_sided_normal_p(z))


# --------------------------------------------------------------------------- #
# Kruskal-Wallis H                                                             #
# --------------------------------------------------------------------------- #
def kruskal_wallis(*groups: Sequence[float]) -> KruskalResult:
    """Kruskal-Wallis H test across ``groups`` (>= 2).

    Returns ``(H, df, p)`` with the tie correction applied and a chi-square
    p-value on ``k - 1`` degrees of freedom.
    """
    if len(groups) < 2:
        raise StatsError("Kruskal-Wallis needs at least two groups")
    data = [_floats(g, minlen=1, name="group") for g in groups]
    k = len(data)
    sizes = [len(g) for g in data]
    n = sum(sizes)
    if n <= k:
        raise StatsError("need more observations than groups")

    combined = [x for g in data for x in g]
    ranks = _average_ranks(combined)

    # Sum of ranks per group, walking the flat rank list group by group.
    idx = 0
    rank_sum_sq = 0.0
    for size in sizes:
        rs = math.fsum(ranks[idx:idx + size])
        rank_sum_sq += rs * rs / size
        idx += size

    h = 12.0 / (n * (n + 1)) * rank_sum_sq - 3.0 * (n + 1)

    # Tie correction.
    tie_term = math.fsum(t ** 3 - t for t in _tie_groups(combined))
    correction = 1.0 - tie_term / (n ** 3 - n)
    if correction <= 0.0:
        raise StatsError("Kruskal-Wallis undefined (all values tied)")
    h /= correction

    df = k - 1
    p = 1.0 - chi_square_cdf(h, df)
    return KruskalResult(h, df, p)


# --------------------------------------------------------------------------- #
# Spearman rank correlation                                                    #
# --------------------------------------------------------------------------- #
def spearman_rho(a: Sequence[float], b: Sequence[float]) -> SpearmanResult:
    """Spearman rank correlation ``rho`` of paired ``a``/``b``.

    Ranks each variable (tie-averaged), computes the Pearson correlation of the
    ranks, and reports a two-sided p-value from a Student-t approximation on
    ``n - 2`` degrees of freedom.
    """
    da = _floats(a, minlen=2, name="a")
    db = _floats(b, minlen=2, name="b")
    if len(da) != len(db):
        raise StatsError("a and b must have equal length")
    n = len(da)

    ra = _average_ranks(da)
    rb = _average_ranks(db)
    ma = math.fsum(ra) / n
    mb = math.fsum(rb) / n
    cov = math.fsum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.fsum((x - ma) ** 2 for x in ra)
    vb = math.fsum((y - mb) ** 2 for y in rb)
    if va == 0.0 or vb == 0.0:
        raise StatsError("Spearman undefined for constant ranks")
    rho = cov / math.sqrt(va * vb)

    if n <= 2:
        p = float("nan")
    elif abs(rho) >= 1.0:
        p = 0.0
    else:
        df = n - 2
        t = rho * math.sqrt(df / (1.0 - rho * rho))
        p = _two_sided_t_p(t, df)
    return SpearmanResult(rho, p)


# --------------------------------------------------------------------------- #
# Kendall tau-b                                                                #
# --------------------------------------------------------------------------- #
def kendall_tau(a: Sequence[float], b: Sequence[float]) -> KendallResult:
    """Kendall's ``tau-b`` rank correlation of paired ``a``/``b``.

    Counts concordant and discordant pairs with the tie-adjusted (tau-b)
    denominator and reports a two-sided normal-approximation p-value.
    """
    da = _floats(a, minlen=2, name="a")
    db = _floats(b, minlen=2, name="b")
    if len(da) != len(db):
        raise StatsError("a and b must have equal length")
    n = len(da)

    concordant = 0
    discordant = 0
    ties_a = 0
    ties_b = 0
    for i in range(n):
        for j in range(i + 1, n):
            da_ij = da[i] - da[j]
            db_ij = db[i] - db[j]
            prod = da_ij * db_ij
            if prod > 0.0:
                concordant += 1
            elif prod < 0.0:
                discordant += 1
            else:
                if da_ij == 0.0:
                    ties_a += 1
                if db_ij == 0.0:
                    ties_b += 1

    n0 = n * (n - 1) / 2.0
    denom = math.sqrt((n0 - ties_a) * (n0 - ties_b))
    if denom == 0.0:
        raise StatsError("Kendall tau undefined (a variable is constant)")
    tau = (concordant - discordant) / denom

    # Normal approximation (tie-corrected variance of S = C - D).
    tie_a_groups = _tie_groups(da)
    tie_b_groups = _tie_groups(db)

    def _t1(groups):
        return math.fsum(t * (t - 1.0) for t in groups)

    def _t2(groups):
        return math.fsum(t * (t - 1.0) * (t - 2.0) for t in groups)

    def _t3(groups):
        return math.fsum(t * (t - 1.0) * (2.0 * t + 5.0) for t in groups)

    v0 = n * (n - 1.0) * (2.0 * n + 5.0)
    vt = _t3(tie_a_groups)
    vu = _t3(tie_b_groups)
    v1 = _t1(tie_a_groups) * _t1(tie_b_groups)
    v2 = _t2(tie_a_groups) * _t2(tie_b_groups)

    var = (
        (v0 - vt - vu) / 18.0
        + v1 / (2.0 * n * (n - 1.0))
        + v2 / (9.0 * n * (n - 1.0) * (n - 2.0))
    )
    s = concordant - discordant
    if var <= 0.0:
        p = 0.0 if s != 0 else 1.0
    else:
        z = s / math.sqrt(var)
        p = _two_sided_normal_p(z)
    return KendallResult(tau, p)
