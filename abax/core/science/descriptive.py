"""Descriptive statistics summary — a single :func:`describe` over a sequence.

A thin orchestration layer on top of :mod:`abax.core.science.stats`. It coerces a
raw sequence (blanks / non-numeric entries are dropped), then reuses the existing
stats helpers (:func:`~abax.core.science.stats.mean`, ``median``, ``mode``,
``variance``, ``stdev``, ``quantile``, ``skewness``, ``kurtosis``) to fill a
summary dict. No formulas are re-derived here.

The result carries the full spread of descriptive measures:

``count sum mean median mode min Q1 Q3 max range variance stdev
variance_pop stdev_pop skewness kurtosis``

Small samples degrade gracefully rather than raising: statistics that are
undefined for the given ``n`` (sample variance/stdev need ``n >= 2``, skewness
``n >= 3``, kurtosis ``n >= 4``) come back as ``None``. An empty input yields a
dict with ``count == 0`` and every statistic ``None`` (``sum`` stays ``0.0``).
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from . import stats

# The ordered set of keys :func:`describe` always returns. Handy for GUIs that
# want to render the summary in a stable row order.
FIELDS: tuple[str, ...] = (
    "count",
    "sum",
    "mean",
    "median",
    "mode",
    "min",
    "Q1",
    "Q3",
    "max",
    "range",
    "variance",
    "stdev",
    "variance_pop",
    "stdev_pop",
    "skewness",
    "kurtosis",
)


def _numeric(values: Sequence) -> list[float]:
    """Keep only the finite numeric entries of ``values`` (drop blanks/text/bools)."""
    out: list[float] = []
    for v in values:
        if isinstance(v, bool) or v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    return out


def describe(values: Sequence) -> dict:
    """Summary statistics for ``values`` (non-numeric entries ignored).

    Returns a dict keyed by :data:`FIELDS`. Undefined statistics for the given
    sample size are ``None`` and never raise; ``count == 0`` is handled.
    """
    data = _numeric(values)
    n = len(data)

    summary: dict[str, Optional[float]] = {key: None for key in FIELDS}
    summary["count"] = n
    summary["sum"] = math.fsum(data) if n else 0.0

    if n == 0:
        return summary

    lo = min(data)
    hi = max(data)
    summary["mean"] = stats.mean(data)
    summary["median"] = stats.median(data)
    summary["mode"] = stats.mode(data)
    summary["min"] = lo
    summary["max"] = hi
    summary["range"] = hi - lo
    summary["Q1"] = stats.quantile(data, 0.25)
    summary["Q3"] = stats.quantile(data, 0.75)

    # Population variance/stdev (n divisor) are defined for any n >= 1.
    summary["variance_pop"] = stats.variance(data, sample=False)
    summary["stdev_pop"] = stats.stdev(data, sample=False)

    # Sample variance/stdev need n >= 2.
    if n >= 2:
        summary["variance"] = stats.variance(data, sample=True)
        summary["stdev"] = stats.stdev(data, sample=True)

    # Skewness needs n >= 3, kurtosis n >= 4; both are undefined for zero
    # variance. stats.* raises StatsError in those cases -> report None.
    if n >= 3:
        try:
            summary["skewness"] = stats.skewness(data)
        except stats.StatsError:
            summary["skewness"] = None
    if n >= 4:
        try:
            summary["kurtosis"] = stats.kurtosis(data)
        except stats.StatsError:
            summary["kurtosis"] = None

    return summary
