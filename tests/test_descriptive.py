"""Oracle tests for :mod:`abax.core.science.descriptive`.

The canonical sample ``[2, 4, 4, 4, 5, 5, 7, 9]`` (Wikipedia's standard-deviation
example) has known descriptive statistics. Quartiles follow the module's own
linear-interpolation ``quantile`` convention, so the expected Q1/Q3 are computed
from that same helper rather than hard-coded to a rival convention.
"""

from __future__ import annotations

import math

import pytest

from abax.core.science import descriptive, stats

SAMPLE = [2, 4, 4, 4, 5, 5, 7, 9]


def test_describe_canonical_sample():
    s = descriptive.describe(SAMPLE)
    assert s["count"] == 8
    assert s["sum"] == pytest.approx(40.0)
    assert s["mean"] == pytest.approx(5.0)
    assert s["median"] == pytest.approx(4.5)
    assert s["mode"] == pytest.approx(4.0)
    assert s["min"] == pytest.approx(2.0)
    assert s["max"] == pytest.approx(9.0)
    assert s["range"] == pytest.approx(7.0)
    # Population stdev = 2.0 exactly; sample stdev ≈ 2.138.
    assert s["stdev_pop"] == pytest.approx(2.0)
    assert s["variance_pop"] == pytest.approx(4.0)
    assert s["stdev"] == pytest.approx(2.13809, abs=1e-4)
    assert s["variance"] == pytest.approx(32.0 / 7.0)


def test_describe_quartiles_match_quantile_convention():
    s = descriptive.describe(SAMPLE)
    assert s["Q1"] == pytest.approx(stats.quantile([float(x) for x in SAMPLE], 0.25))
    assert s["Q3"] == pytest.approx(stats.quantile([float(x) for x in SAMPLE], 0.75))
    # For this sample the convention yields Q1=4.0, Q3=5.5.
    assert s["Q1"] == pytest.approx(4.0)
    assert s["Q3"] == pytest.approx(5.5)


def test_describe_higher_moments_present_for_large_sample():
    s = descriptive.describe(SAMPLE)
    assert s["skewness"] is not None
    assert s["kurtosis"] is not None
    assert s["skewness"] == pytest.approx(stats.skewness([float(x) for x in SAMPLE]))
    assert s["kurtosis"] == pytest.approx(stats.kurtosis([float(x) for x in SAMPLE]))


def test_describe_ignores_blanks_and_text():
    s = descriptive.describe([2, "", None, 4, "abc", 4, 4, 5, 5, 7, 9, True])
    # True is a bool -> ignored; blanks/text dropped. Same as SAMPLE.
    assert s["count"] == 8
    assert s["mean"] == pytest.approx(5.0)


def test_describe_empty_does_not_crash():
    s = descriptive.describe([])
    assert s["count"] == 0
    assert s["sum"] == pytest.approx(0.0)
    for key in descriptive.FIELDS:
        if key in ("count", "sum"):
            continue
        assert s[key] is None
    # Also cover the all-blank case.
    s2 = descriptive.describe(["", None, "x"])
    assert s2["count"] == 0
    assert s2["mean"] is None


def test_describe_single_value_does_not_crash():
    s = descriptive.describe([42])
    assert s["count"] == 1
    assert s["sum"] == pytest.approx(42.0)
    assert s["mean"] == pytest.approx(42.0)
    assert s["median"] == pytest.approx(42.0)
    assert s["mode"] == pytest.approx(42.0)
    assert s["min"] == pytest.approx(42.0)
    assert s["max"] == pytest.approx(42.0)
    assert s["range"] == pytest.approx(0.0)
    # Population variance/stdev defined (0.0) for n=1.
    assert s["variance_pop"] == pytest.approx(0.0)
    assert s["stdev_pop"] == pytest.approx(0.0)
    # Sample variance/stdev + higher moments undefined -> None.
    assert s["variance"] is None
    assert s["stdev"] is None
    assert s["skewness"] is None
    assert s["kurtosis"] is None


def test_describe_returns_all_fields():
    s = descriptive.describe(SAMPLE)
    assert set(s.keys()) == set(descriptive.FIELDS)


def test_describe_two_values_has_sample_stats_but_no_moments():
    s = descriptive.describe([1, 3])
    assert s["variance"] == pytest.approx(2.0)
    assert s["stdev"] == pytest.approx(math.sqrt(2.0))
    assert s["skewness"] is None
    assert s["kurtosis"] is None
