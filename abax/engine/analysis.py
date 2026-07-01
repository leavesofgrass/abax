"""Statistics / analysis engine — the brain behind abax's Stats/Analysis menu.

Each public function takes plain Python lists of floats (one list per column the
user selected in the grid) and returns an :class:`AnalysisResult`: a title, a few
human-readable ``summary`` lines (statistic, p-value, effect size, and a one-line
plain-English interpretation), and a 2-D ``table`` block (header row + data rows)
ready to paste straight back into the sheet.

The analyses cover the workhorses of data science and biostatistics — descriptive
summaries, group comparisons (t-test, one-way ANOVA), correlation, OLS regression,
a normality / assumption check, and Kaplan–Meier survival — chosen from the tests
that form the backbone of quantitative analysis (Student's t, Pearson correlation,
ANOVA F-test, linear regression, Shapiro–Wilk) plus survival analysis for
biostatistics.

This lives in the ``engine`` layer, so (unlike ``abax.core``) it may use optional
third-party packages — but it MUST degrade gracefully: importing this module never
fails when scipy / statsmodels / pingouin / lifelines are absent. Every optional
dependency is imported lazily inside the function that needs it, guarded so that a
missing package becomes an :class:`AnalysisError` ("… requires <pkg>") rather than
an ``ImportError``. Only :func:`describe` is guaranteed to work with zero optional
packages installed — it uses the stdlib :mod:`statistics` module exclusively.

References for the test selection:

* "Essential Statistical Tests for Data Scientists", DASCA —
  https://www.dasca.org/world-of-data-science/article/essential-statistical-tests-for-data-scientists
* "Selection of Appropriate Statistical Methods for Data Analysis", PMC6639881 —
  https://pmc.ncbi.nlm.nih.gov/articles/PMC6639881/
* pingouin (effect sizes / Cohen's d / cleaner test output) —
  https://pingouin-stats.org/
"""

from __future__ import annotations

import importlib.util
import math
import statistics
from dataclasses import dataclass, field


class AnalysisError(Exception):
    """Raised when an analysis cannot run: missing dependency or bad input."""


@dataclass
class AnalysisResult:
    """The result of one analysis, ready for the GUI/TUI to display and paste."""

    title: str
    summary: list[str] = field(default_factory=list)
    table: list[list[object]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# dependency probing                                                          #
# --------------------------------------------------------------------------- #
def _have(pkg: str) -> bool:
    """True if *pkg* is importable right now (no import side effects)."""
    try:
        return importlib.util.find_spec(pkg) is not None
    except (ImportError, ValueError):
        return False


def _require(pkg: str, what: str):
    """Import *pkg* or raise a clear :class:`AnalysisError`."""
    if not _have(pkg):
        raise AnalysisError(f"{what} requires {pkg}")
    import importlib

    try:
        return importlib.import_module(pkg)
    except ImportError as exc:  # pragma: no cover - find_spec said it was there
        raise AnalysisError(f"{what} requires {pkg}") from exc


# --------------------------------------------------------------------------- #
# input coercion                                                              #
# --------------------------------------------------------------------------- #
def _column(xs, *, minlen: int = 1, name: str = "data") -> list[float]:
    """Coerce one column to a list of floats; require at least *minlen* values."""
    try:
        out = [float(x) for x in xs]
    except (TypeError, ValueError) as exc:
        raise AnalysisError(f"{name} must be numeric") from exc
    if any(math.isnan(v) for v in out):
        raise AnalysisError(f"{name} contains non-numeric (NaN) values")
    if len(out) < minlen:
        raise AnalysisError(f"{name} needs at least {minlen} value(s)")
    return out


def _columns(columns, *, minlen: int = 1, equal: bool = False) -> list[list[float]]:
    """Coerce a list of columns; optionally require equal (non-ragged) lengths."""
    if not columns:
        raise AnalysisError("no columns supplied")
    out = [
        _column(c, minlen=minlen, name=f"column {i + 1}")
        for i, c in enumerate(columns)
    ]
    if equal:
        n = len(out[0])
        if any(len(c) != n for c in out):
            raise AnalysisError("columns must have equal length (ragged input)")
    return out


def _label(names, i: int) -> str:
    if names and i < len(names) and names[i] not in (None, ""):
        return str(names[i])
    return f"Col{i + 1}"


def _fmt(x: float, places: int = 4) -> float:
    """Round for display while keeping a float in the table cell."""
    if not math.isfinite(x):
        return x
    return round(x, places)


def _p_phrase(p: float, alpha: float = 0.05) -> str:
    rel = "significant" if p < alpha else "not significant"
    return f"{rel} at alpha={alpha:g}"


# --------------------------------------------------------------------------- #
# registry the GUI reads to build the Stats/Analysis menu                     #
# --------------------------------------------------------------------------- #
ANALYSES: dict[str, dict] = {
    "describe": {
        "label": "Descriptive statistics",
        "min_cols": 1,
        "needs": (),
        "doc": "n, mean, stdev, min, Q1, median, Q3, max per selected column.",
    },
    "ttest": {
        "label": "t-test (two columns)",
        "min_cols": 2,
        "needs": ("scipy",),
        "doc": "Independent or paired t-test: t, df, p, and Cohen's d effect size.",
    },
    "anova_oneway": {
        "label": "One-way ANOVA",
        "min_cols": 2,
        "needs": ("scipy",),
        "doc": "Compare means across 3+ groups: F, p, and eta-squared effect size.",
    },
    "correlation": {
        "label": "Correlation matrix",
        "min_cols": 2,
        "needs": ("scipy",),
        "doc": "Pearson or Spearman correlation matrix with p-values.",
    },
    "linear_regression": {
        "label": "Linear regression (OLS)",
        "min_cols": 2,
        "needs": (),  # statsmodels preferred, numpy fallback, else pure-Python
        "doc": "OLS of the first column on the rest: coefficients, R-squared, adj-R2.",
    },
    "normality": {
        "label": "Normality test (Shapiro-Wilk)",
        "min_cols": 1,
        "needs": ("scipy",),
        "doc": "Shapiro-Wilk test for normality: W, p, and a pass/fail note.",
    },
    "survival_km": {
        "label": "Kaplan-Meier survival",
        "min_cols": 2,
        "needs": ("lifelines",),
        "doc": "Kaplan-Meier estimate: time, at-risk, survival, and median survival.",
    },
}


def requirements_met(key: str) -> bool:
    """Are this analysis's required packages importable right now?

    Unknown keys return ``False``. Analyses with an empty ``needs`` tuple are
    always met (``describe`` and ``linear_regression`` have stdlib/fallback
    paths). Multi-package ``needs`` use *or* semantics: any one suffices.
    """
    entry = ANALYSES.get(key)
    if entry is None:
        return False
    needs = entry["needs"]
    if not needs:
        return True
    return any(_have(pkg) for pkg in needs)


# --------------------------------------------------------------------------- #
# 1. descriptive statistics (stdlib only — always available)                  #
# --------------------------------------------------------------------------- #
def describe(columns: list[list[float]], names=None) -> AnalysisResult:
    """Per-column summary: n, mean, stdev, min, Q1, median, Q3, max.

    Stdlib only (:mod:`statistics`); needs no third-party package.
    """
    cols = _columns(columns, minlen=1)
    header = ["Column", "n", "mean", "stdev", "min", "Q1", "median", "Q3", "max"]
    table: list[list[object]] = [header]
    summary: list[str] = []
    for i, data in enumerate(cols):
        name = _label(names, i)
        n = len(data)
        m = statistics.fmean(data)
        sd = statistics.stdev(data) if n >= 2 else 0.0
        srt = sorted(data)
        if n >= 2:
            q1, _med, q3 = statistics.quantiles(data, n=4, method="inclusive")
        else:
            q1 = q3 = srt[0]
        med = statistics.median(data)
        table.append(
            [
                name, n, _fmt(m), _fmt(sd), _fmt(srt[0]),
                _fmt(q1), _fmt(med), _fmt(q3), _fmt(srt[-1]),
            ]
        )
        summary.append(
            f"{name}: n={n}, mean={_fmt(m)}, stdev={_fmt(sd)}, "
            f"median={_fmt(med)}, range=[{_fmt(srt[0])}, {_fmt(srt[-1])}]"
        )
    return AnalysisResult("Descriptive statistics", summary, table)


# --------------------------------------------------------------------------- #
# 2. t-test (scipy / pingouin)                                                #
# --------------------------------------------------------------------------- #
def _cohens_d(a: list[float], b: list[float], paired: bool) -> float:
    """Cohen's d effect size for two samples."""
    na, nb = len(a), len(b)
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    if paired:
        diffs = [x - y for x, y in zip(a, b)]
        sd = statistics.stdev(diffs) if len(diffs) >= 2 else 0.0
        return (ma - mb) / sd if sd else 0.0
    va = statistics.variance(a) if na >= 2 else 0.0
    vb = statistics.variance(b) if nb >= 2 else 0.0
    pooled = ((na - 1) * va + (nb - 1) * vb) / (na + nb - 2)
    sd = math.sqrt(pooled)
    return (ma - mb) / sd if sd else 0.0


def _d_magnitude(d: float) -> str:
    a = abs(d)
    if a < 0.2:
        return "negligible"
    if a < 0.5:
        return "small"
    if a < 0.8:
        return "medium"
    return "large"


def ttest(a: list[float], b: list[float], *, paired: bool = False) -> AnalysisResult:
    """Two-sample t-test (independent Welch by default, or ``paired``).

    Reports t, degrees of freedom, two-sided p, and Cohen's d. Uses pingouin
    when installed (it returns a tidy frame incl. the effect size); otherwise
    scipy.stats with a hand-computed Cohen's d.
    """
    da = _column(a, minlen=2, name="sample A")
    db = _column(b, minlen=2, name="sample B")
    if paired and len(da) != len(db):
        raise AnalysisError("paired t-test needs equal-length samples")

    kind = "Paired t-test" if paired else "Independent t-test"

    if _have("pingouin"):
        pg = _require("pingouin", kind)
        res = pg.ttest(da, db, paired=paired)
        row = res.iloc[0]

        def _pick(*candidates):
            for c in candidates:
                if c in res.columns:
                    return float(row[c])
            raise AnalysisError("pingouin returned an unexpected column layout")

        t = _pick("T")
        df = _pick("dof", "df")
        p = _pick("p-val", "p_val", "pval")
        d = _pick("cohen-d", "cohen_d", "cohen")
        engine = "pingouin"
    else:
        _require("scipy", kind)
        from scipy import stats  # type: ignore

        if paired:
            t_stat, p = stats.ttest_rel(da, db)
            df = float(len(da) - 1)
        else:
            t_stat, p = stats.ttest_ind(da, db, equal_var=False)
            # Welch–Satterthwaite degrees of freedom.
            va, vb = statistics.variance(da), statistics.variance(db)
            na, nb = len(da), len(db)
            sea, seb = va / na, vb / nb
            num = (sea + seb) ** 2
            den = sea ** 2 / (na - 1) + seb ** 2 / (nb - 1)
            df = num / den if den else float(na + nb - 2)
        t = float(t_stat)
        p = float(p)
        d = _cohens_d(da, db, paired)
        engine = "scipy"

    ma, mb = statistics.fmean(da), statistics.fmean(db)
    summary = [
        f"{kind}: t={_fmt(t)}, df={_fmt(df, 2)}, p={_fmt(p)} ({_p_phrase(p)})",
        f"means: A={_fmt(ma)}, B={_fmt(mb)}; difference={_fmt(ma - mb)}",
        f"Cohen's d={_fmt(d)} ({_d_magnitude(d)} effect) [{engine}]",
    ]
    table = [
        ["statistic", "value"],
        ["t", _fmt(t)],
        ["df", _fmt(df, 2)],
        ["p-value", _fmt(p)],
        ["mean A", _fmt(ma)],
        ["mean B", _fmt(mb)],
        ["Cohen's d", _fmt(d)],
    ]
    return AnalysisResult(kind, summary, table)


# --------------------------------------------------------------------------- #
# 3. one-way ANOVA (scipy)                                                     #
# --------------------------------------------------------------------------- #
def anova_oneway(groups: list[list[float]], names=None) -> AnalysisResult:
    """One-way ANOVA across 2+ groups: F, p, and eta-squared effect size."""
    if not groups or len(groups) < 2:
        raise AnalysisError("ANOVA needs at least two groups")
    data = _columns(groups, minlen=2)

    _require("scipy", "One-way ANOVA")
    from scipy import stats  # type: ignore

    f_stat, p = stats.f_oneway(*data)
    f_stat = float(f_stat)
    p = float(p)

    # eta-squared = SS_between / SS_total.
    all_vals = [x for g in data for x in g]
    grand = statistics.fmean(all_vals)
    ss_between = math.fsum(len(g) * (statistics.fmean(g) - grand) ** 2 for g in data)
    ss_total = math.fsum((x - grand) ** 2 for x in all_vals)
    eta2 = ss_between / ss_total if ss_total else 0.0

    mag = "large" if eta2 >= 0.14 else "medium" if eta2 >= 0.06 else "small"
    k = len(data)
    n = len(all_vals)
    summary = [
        f"One-way ANOVA ({k} groups, n={n}): F={_fmt(f_stat)}, "
        f"df=({k - 1}, {n - k}), p={_fmt(p)} ({_p_phrase(p)})",
        f"eta-squared={_fmt(eta2)} ({mag} effect)",
        (
            "At least one group mean differs."
            if p < 0.05
            else "No detectable difference among group means."
        ),
    ]
    table = [["Group", "n", "mean"]]
    for i, g in enumerate(data):
        table.append([_label(names, i), len(g), _fmt(statistics.fmean(g))])
    table.append(["F", "", _fmt(f_stat)])
    table.append(["p-value", "", _fmt(p)])
    table.append(["eta-squared", "", _fmt(eta2)])
    return AnalysisResult("One-way ANOVA", summary, table)


# --------------------------------------------------------------------------- #
# 4. correlation matrix (scipy)                                               #
# --------------------------------------------------------------------------- #
def correlation(
    columns: list[list[float]], names=None, method: str = "pearson"
) -> AnalysisResult:
    """Pearson or Spearman correlation matrix with p-values (scipy.stats)."""
    method = method.lower()
    if method not in ("pearson", "spearman"):
        raise AnalysisError("method must be 'pearson' or 'spearman'")
    cols = _columns(columns, minlen=2, equal=True)
    if len(cols) < 2:
        raise AnalysisError("correlation needs at least two columns")

    _require("scipy", "Correlation")
    from scipy import stats  # type: ignore

    fn = stats.pearsonr if method == "pearson" else stats.spearmanr
    k = len(cols)
    labels = [_label(names, i) for i in range(k)]

    rmat = [[1.0] * k for _ in range(k)]
    pmat = [[0.0] * k for _ in range(k)]
    for i in range(k):
        for j in range(i + 1, k):
            r, p = fn(cols[i], cols[j])
            r, p = float(r), float(p)
            rmat[i][j] = rmat[j][i] = r
            pmat[i][j] = pmat[j][i] = p

    table: list[list[object]] = [[method + " r"] + labels]
    for i in range(k):
        table.append([labels[i]] + [_fmt(rmat[i][j]) for j in range(k)])

    # Strongest off-diagonal pair for the interpretation line.
    best = (0, 1, 0.0)
    for i in range(k):
        for j in range(i + 1, k):
            if abs(rmat[i][j]) >= abs(best[2]):
                best = (i, j, rmat[i][j])
    bi, bj, br = best
    summary = [
        f"{method.capitalize()} correlation matrix over {k} columns.",
        f"strongest: {labels[bi]} vs {labels[bj]} r={_fmt(br)} "
        f"(p={_fmt(pmat[bi][bj])}, {_p_phrase(pmat[bi][bj])})",
        (
            "Strong linear association."
            if abs(br) >= 0.7
            else "Moderate association."
            if abs(br) >= 0.3
            else "Weak association."
        ),
    ]
    return AnalysisResult(f"{method.capitalize()} correlation", summary, table)


# --------------------------------------------------------------------------- #
# 5. linear regression (statsmodels preferred, numpy / pure-Python fallback)  #
# --------------------------------------------------------------------------- #
def linear_regression(
    y: list[float], xs: list[list[float]], names=None
) -> AnalysisResult:
    """OLS of *y* on predictor columns *xs*.

    Reports coefficients, std errors, t, p, R-squared and adjusted R-squared.
    Uses statsmodels when present; otherwise a numpy least-squares fallback;
    otherwise a pure-Python normal-equations solve (so it always runs).
    """
    dy = _column(y, minlen=3, name="y")
    if not xs:
        raise AnalysisError("regression needs at least one predictor column")
    dxs = _columns(xs, minlen=3)
    n = len(dy)
    for c in dxs:
        if len(c) != n:
            raise AnalysisError("y and predictors must have equal length")
    k = len(dxs)  # number of predictors (excluding intercept)
    if n <= k + 1:
        raise AnalysisError("need more observations than coefficients")

    pred_names = [_label(names, i + 1) if names else f"x{i + 1}" for i in range(k)]

    if _have("statsmodels"):
        engine = "statsmodels"
        sm = _require("statsmodels.api", "Linear regression")
        import numpy as np  # statsmodels depends on numpy

        X = np.column_stack([np.ones(n)] + [np.asarray(c, float) for c in dxs])
        model = sm.OLS(np.asarray(dy, float), X).fit()
        coef = list(map(float, model.params))
        se = list(map(float, model.bse))
        tvals = list(map(float, model.tvalues))
        pvals = list(map(float, model.pvalues))
        r2 = float(model.rsquared)
        adj = float(model.rsquared_adj)
    else:
        engine = "numpy" if _have("numpy") else "pure-python"
        coef, se, tvals, pvals, r2, adj = _ols_fallback(dy, dxs)

    rows = ["const"] + pred_names
    table: list[list[object]] = [["term", "coef", "std err", "t", "p-value"]]
    for name, c, s, t, p in zip(rows, coef, se, tvals, pvals):
        table.append([name, _fmt(c), _fmt(s), _fmt(t), _fmt(p)])
    table.append(["R-squared", _fmt(r2), "", "", ""])
    table.append(["adj R-squared", _fmt(adj), "", "", ""])

    eqn = " + ".join(
        f"{_fmt(c, 3)}*{nm}" for c, nm in zip(coef[1:], pred_names)
    )
    summary = [
        f"OLS: y = {_fmt(coef[0], 3)} + {eqn} [{engine}]",
        f"R-squared={_fmt(r2)}, adjusted R-squared={_fmt(adj)}",
        (
            f"Model explains {_fmt(r2 * 100, 1)}% of the variance in y."
        ),
    ]
    return AnalysisResult("Linear regression (OLS)", summary, table)


def _ols_fallback(y: list[float], xs: list[list[float]]):
    """OLS via numpy lstsq if available, else pure-Python normal equations.

    Returns ``(coef, se, t, p, r2, adj_r2)`` with the intercept first.
    """
    n = len(y)
    k = len(xs)
    p_full = k + 1  # parameters incl. intercept
    # Design matrix rows: [1, x1, x2, ...].
    X = [[1.0] + [xs[j][i] for j in range(k)] for i in range(n)]

    if _have("numpy"):
        import numpy as np

        A = np.asarray(X, float)
        b = np.asarray(y, float)
        coef, *_ = np.linalg.lstsq(A, b, rcond=None)
        coef = list(map(float, coef))
        resid = b - A @ np.asarray(coef)
        dof = n - p_full
        sigma2 = float(resid @ resid) / dof if dof > 0 else 0.0
        xtx_inv = np.linalg.inv(A.T @ A)
        se = [float(math.sqrt(max(sigma2 * xtx_inv[i, i], 0.0))) for i in range(p_full)]
        ss_res = float(resid @ resid)
        ybar = float(b.mean())
        ss_tot = float(((b - ybar) ** 2).sum())
    else:
        # Pure-Python normal equations: (X'X) beta = X'y.
        xtx = [[math.fsum(X[r][i] * X[r][j] for r in range(n)) for j in range(p_full)]
               for i in range(p_full)]
        xty = [math.fsum(X[r][i] * y[r] for r in range(n)) for i in range(p_full)]
        inv = _invert(xtx)
        coef = [math.fsum(inv[i][j] * xty[j] for j in range(p_full)) for i in range(p_full)]
        fitted = [math.fsum(coef[j] * X[r][j] for j in range(p_full)) for r in range(n)]
        resid = [y[r] - fitted[r] for r in range(n)]
        ss_res = math.fsum(e * e for e in resid)
        dof = n - p_full
        sigma2 = ss_res / dof if dof > 0 else 0.0
        se = [math.sqrt(max(sigma2 * inv[i][i], 0.0)) for i in range(p_full)]
        ybar = math.fsum(y) / n
        ss_tot = math.fsum((v - ybar) ** 2 for v in y)

    tvals = [coef[i] / se[i] if se[i] else math.inf for i in range(p_full)]
    pvals = [_t_sf(abs(t), n - p_full) for t in tvals]
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 1.0
    adj = 1.0 - (1.0 - r2) * (n - 1) / (n - p_full) if (n - p_full) > 0 else r2
    return coef, se, tvals, pvals, r2, adj


def _invert(m: list[list[float]]) -> list[list[float]]:
    """Gauss–Jordan inverse of a small square matrix (pure-Python fallback)."""
    n = len(m)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-15:
            raise AnalysisError("singular design matrix (collinear predictors)")
        a[col], a[piv] = a[piv], a[col]
        pv = a[col][col]
        a[col] = [v / pv for v in a[col]]
        for r in range(n):
            if r != col:
                factor = a[r][col]
                a[r] = [a[r][c] - factor * a[col][c] for c in range(2 * n)]
    return [row[n:] for row in a]


def _t_sf(t: float, df: int) -> float:
    """Two-sided p-value for |t| with *df* (stdlib regularized incomplete beta)."""
    if df <= 0 or not math.isfinite(t):
        return float("nan")
    x = df / (df + t * t)
    return _betai(df / 2.0, 0.5, x)  # = 2 * P(T > |t|)


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b), used only by the OLS fallback."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _betacf(a: float, b: float, x: float, max_iter: int = 300, eps: float = 1e-14) -> float:
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
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
    return h


# --------------------------------------------------------------------------- #
# 6. normality — Shapiro–Wilk (scipy)                                         #
# --------------------------------------------------------------------------- #
def normality(column: list[float]) -> AnalysisResult:
    """Shapiro–Wilk normality test: W, p, and a pass/fail note at alpha=0.05."""
    data = _column(column, minlen=3, name="sample")

    _require("scipy", "Normality test")
    from scipy import stats  # type: ignore

    w, p = stats.shapiro(data)
    w, p = float(w), float(p)
    normal = p >= 0.05
    note = (
        "consistent with a normal distribution (fail to reject H0)"
        if normal
        else "departs from normality (reject H0)"
    )
    summary = [
        f"Shapiro–Wilk: W={_fmt(w)}, p={_fmt(p)} (n={len(data)})",
        f"At alpha=0.05 the data {note}.",
        (
            "Parametric tests (t-test, ANOVA) are reasonable."
            if normal
            else "Consider a non-parametric test or a transform."
        ),
    ]
    table = [
        ["statistic", "value"],
        ["W", _fmt(w)],
        ["p-value", _fmt(p)],
        ["n", len(data)],
        ["normal (alpha=0.05)", "yes" if normal else "no"],
    ]
    return AnalysisResult("Shapiro–Wilk normality", summary, table)


# --------------------------------------------------------------------------- #
# 7. Kaplan–Meier survival (lifelines)                                        #
# --------------------------------------------------------------------------- #
def survival_km(durations: list[float], events: list[int]) -> AnalysisResult:
    """Kaplan–Meier survival estimate via lifelines.

    *durations* are observed times; *events* are 1 (event/death) or 0 (censored).
    The table is ``(time, at_risk, survival)`` rows plus the median survival time.
    """
    dur = _column(durations, minlen=1, name="durations")
    try:
        ev = [int(e) for e in events]
    except (TypeError, ValueError) as exc:
        raise AnalysisError("events must be 0/1 integers") from exc
    if len(dur) != len(ev):
        raise AnalysisError("durations and events must have equal length")
    if any(e not in (0, 1) for e in ev):
        raise AnalysisError("events must be 0 (censored) or 1 (event)")

    if not _have("lifelines"):
        raise AnalysisError("Kaplan–Meier survival requires lifelines")
    kmf_mod = _require("lifelines", "Kaplan–Meier survival")
    kmf = kmf_mod.KaplanMeierFitter()
    kmf.fit(dur, event_observed=ev)

    sf = kmf.survival_function_
    at_risk_frame = kmf.event_table  # indexed by time, has "at_risk"
    times = list(sf.index)

    table: list[list[object]] = [["time", "at_risk", "survival"]]
    for t in times:
        try:
            at_risk = int(at_risk_frame.loc[t, "at_risk"])
        except Exception:  # pragma: no cover - defensive
            at_risk = ""
        surv = float(sf.loc[t].iloc[0])
        table.append([_fmt(float(t), 4), at_risk, _fmt(surv)])

    median = kmf.median_survival_time_
    n_events = sum(ev)
    n_cens = len(ev) - n_events
    median_disp = "not reached" if (median is None or math.isinf(median) or
                                    (isinstance(median, float) and math.isnan(median))) \
        else _fmt(float(median))
    summary = [
        f"Kaplan–Meier: n={len(dur)}, events={n_events}, censored={n_cens}",
        f"median survival time = {median_disp}",
        f"final survival estimate = {_fmt(float(sf.iloc[-1].iloc[0]))}",
    ]
    return AnalysisResult("Kaplan–Meier survival", summary, table)
