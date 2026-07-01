"""Tests for the statistics/analysis engine (``abax.engine.analysis``).

The descriptive-stats test and the registry/error tests run with zero optional
packages installed. Tests needing scipy / statsmodels / lifelines use
``pytest.importorskip`` so the suite stays green on a stdlib-only install.
"""

from __future__ import annotations

import math

import pytest

from abax.engine import analysis as A
from abax.engine.analysis import AnalysisError, AnalysisResult


# --------------------------------------------------------------------------- #
# describe — stdlib only, always runs                                         #
# --------------------------------------------------------------------------- #
def test_describe_basic():
    res = A.describe([[1, 2, 3, 4, 5]])
    assert isinstance(res, AnalysisResult)
    header, row = res.table[0], res.table[1]
    cells = dict(zip(header, row))
    assert cells["n"] == 5
    assert cells["mean"] == pytest.approx(3.0)
    assert cells["median"] == pytest.approx(3.0)
    assert cells["min"] == pytest.approx(1.0)
    assert cells["max"] == pytest.approx(5.0)
    assert cells["stdev"] == pytest.approx(math.sqrt(2.5), abs=1e-4)
    assert res.summary  # non-empty interpretation lines


def test_describe_multiple_columns_and_names():
    res = A.describe([[1, 2, 3], [10, 20, 30]], names=["a", "b"])
    assert res.table[1][0] == "a"
    assert res.table[2][0] == "b"
    assert len(res.table) == 3  # header + 2 rows


def test_describe_needs_nothing():
    assert A.requirements_met("describe") is True


# --------------------------------------------------------------------------- #
# registry                                                                    #
# --------------------------------------------------------------------------- #
def test_registry_shape():
    assert isinstance(A.ANALYSES, dict)
    for key, entry in A.ANALYSES.items():
        assert set(entry) >= {"label", "min_cols", "needs", "doc"}
        assert isinstance(entry["label"], str)
        assert isinstance(entry["min_cols"], int)
        assert isinstance(entry["needs"], tuple)
        assert isinstance(entry["doc"], str)
        # every registered key maps to a callable in the module
        assert callable(getattr(A, key))


def test_requirements_met_unknown_key():
    assert A.requirements_met("does_not_exist") is False


# --------------------------------------------------------------------------- #
# errors (no optional deps required)                                          #
# --------------------------------------------------------------------------- #
def test_describe_too_few_values():
    with pytest.raises(AnalysisError):
        A.describe([[]])


def test_describe_non_numeric():
    with pytest.raises(AnalysisError):
        A.describe([["a", "b", "c"]])


def test_correlation_ragged_raises():
    # Ragged columns must raise even before any dependency is touched... but
    # correlation needs scipy; skip if absent so the error path is the dep one.
    pytest.importorskip("scipy")
    with pytest.raises(AnalysisError):
        A.correlation([[1, 2, 3], [1, 2]])


def test_ttest_too_few_points():
    with pytest.raises(AnalysisError):
        A.ttest([1.0], [1.0, 2.0, 3.0])


def test_anova_needs_two_groups():
    with pytest.raises(AnalysisError):
        A.anova_oneway([[1, 2, 3]])


def test_regression_ragged():
    with pytest.raises(AnalysisError):
        A.linear_regression([1, 2, 3], [[1, 2]])


# --------------------------------------------------------------------------- #
# t-test (scipy)                                                              #
# --------------------------------------------------------------------------- #
def test_ttest_different_samples():
    pytest.importorskip("scipy")
    a = [1.0, 2.0, 3.0, 2.0, 1.5, 2.5]
    b = [10.0, 11.0, 12.0, 10.5, 11.5, 9.5]
    res = A.ttest(a, b)
    cells = {r[0]: r[1] for r in res.table[1:]}
    assert cells["p-value"] < 0.05
    assert abs(cells["Cohen's d"]) > 0.8  # large, non-zero effect
    assert any("Cohen" in line for line in res.summary)


def test_ttest_paired_runs():
    pytest.importorskip("scipy")
    a = [5.0, 6.0, 7.0, 8.0, 9.0]
    b = [4.0, 5.5, 6.0, 7.5, 8.0]
    res = A.ttest(a, b, paired=True)
    assert res.title == "Paired t-test"


# --------------------------------------------------------------------------- #
# ANOVA (scipy)                                                               #
# --------------------------------------------------------------------------- #
def test_anova_separated_groups():
    pytest.importorskip("scipy")
    g1 = [1.0, 2.0, 1.5, 2.5, 1.0]
    g2 = [10.0, 11.0, 10.5, 9.5, 11.5]
    g3 = [20.0, 21.0, 19.5, 20.5, 22.0]
    res = A.anova_oneway([g1, g2, g3])
    rows = {r[0]: r[2] for r in res.table if r[0] in ("F", "p-value", "eta-squared")}
    assert rows["p-value"] < 0.05
    assert rows["eta-squared"] > 0.5  # well-separated -> large effect


# --------------------------------------------------------------------------- #
# correlation (scipy)                                                         #
# --------------------------------------------------------------------------- #
def test_correlation_perfect_pearson():
    pytest.importorskip("scipy")
    res = A.correlation([[1, 2, 3, 4], [2, 4, 6, 8]], method="pearson")
    # off-diagonal entry of the 2x2 matrix
    assert res.table[1][2] == pytest.approx(1.0, abs=1e-9)
    assert res.table[2][1] == pytest.approx(1.0, abs=1e-9)


def test_correlation_bad_method():
    with pytest.raises(AnalysisError):
        A.correlation([[1, 2, 3], [3, 2, 1]], method="kendall")


# --------------------------------------------------------------------------- #
# linear regression (statsmodels OR numpy/pure-python fallback)               #
# --------------------------------------------------------------------------- #
def test_linear_regression_y_equals_2x():
    # No importorskip: there is always a path (statsmodels -> numpy -> pure).
    y = [2.0, 4.0, 6.0, 8.0, 10.0]
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    res = A.linear_regression(y, [x])
    terms = {r[0]: r[1] for r in res.table[1:]}
    assert terms["x1"] == pytest.approx(2.0, abs=1e-6)
    assert terms["const"] == pytest.approx(0.0, abs=1e-6)
    assert terms["R-squared"] == pytest.approx(1.0, abs=1e-9)


def test_linear_regression_multiple_predictors():
    y = [3.0, 5.0, 7.0, 9.0, 11.0, 13.0]
    x1 = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    x2 = [1.0, 1.0, 2.0, 2.0, 3.0, 3.0]
    res = A.linear_regression(y, [x1, x2])
    terms = {r[0]: r[1] for r in res.table[1:]}
    assert terms["R-squared"] == pytest.approx(1.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# normality (scipy)                                                           #
# --------------------------------------------------------------------------- #
def test_normality_runs_on_nonnormal():
    pytest.importorskip("scipy")
    sample = [1.0, 1.0, 1.0, 1.0, 1.0, 100.0, 200.0]
    res = A.normality(sample)
    assert isinstance(res, AnalysisResult)
    assert res.table  # has a W / p table; must not raise
    assert any("Shapiro" in line for line in res.summary)


# --------------------------------------------------------------------------- #
# survival (lifelines)                                                        #
# --------------------------------------------------------------------------- #
def test_survival_km_basic():
    pytest.importorskip("lifelines")
    durations = [5, 6, 6, 2, 4, 4, 8, 3, 10, 7]
    events = [1, 0, 1, 1, 1, 0, 1, 0, 1, 1]
    res = A.survival_km(durations, events)
    assert res.table[0] == ["time", "at_risk", "survival"]
    assert len(res.table) > 1
    assert any("median survival" in line for line in res.summary)


def test_survival_km_length_mismatch():
    with pytest.raises(AnalysisError):
        A.survival_km([1, 2, 3], [1, 0])


# --------------------------------------------------------------------------- #
# module imports cleanly regardless of optional deps                          #
# --------------------------------------------------------------------------- #
def test_import_does_not_require_optional_deps():
    # Importing the module (done at top) must not raise; requirements_met must
    # answer for every registered analysis without importing the package.
    for key in A.ANALYSES:
        assert isinstance(A.requirements_met(key), bool)
