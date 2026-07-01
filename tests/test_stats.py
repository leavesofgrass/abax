"""Tests for :mod:`abax.core.science.stats` (pure-stdlib statistics)."""

from __future__ import annotations

import pytest

from abax.core.science import stats


# --------------------------------------------------------------------------- #
# descriptive                                                                  #
# --------------------------------------------------------------------------- #
def test_mean():
    assert stats.mean([1, 2, 3, 4]) == pytest.approx(2.5, abs=1e-9)


def test_median_odd_even():
    assert stats.median([1, 2, 3]) == pytest.approx(2.0, abs=1e-9)
    assert stats.median([1, 2, 3, 4]) == pytest.approx(2.5, abs=1e-9)


def test_mode_smallest_most_frequent():
    assert stats.mode([1, 1, 2, 2, 3]) == 1
    assert stats.mode([4, 4, 4, 1]) == 4


def test_stdev_population():
    assert stats.stdev([2, 4, 4, 4, 5, 5, 7, 9], sample=False) == pytest.approx(
        2.0, abs=1e-9
    )


def test_variance_sample_vs_population():
    xs = [2, 4, 4, 4, 5, 5, 7, 9]
    vp = stats.variance(xs, sample=False)
    vs = stats.variance(xs, sample=True)
    assert vp == pytest.approx(4.0, abs=1e-9)
    # sample = pop * n / (n-1)
    assert vs == pytest.approx(vp * 8 / 7, abs=1e-9)
    assert vs > vp


def test_percentile_and_quantile():
    assert stats.percentile([1, 2, 3, 4], 50) == pytest.approx(2.5, abs=1e-9)
    assert stats.quantile([1, 2, 3, 4], 0.0) == pytest.approx(1.0, abs=1e-9)
    assert stats.quantile([1, 2, 3, 4], 1.0) == pytest.approx(4.0, abs=1e-9)


def test_iqr():
    assert stats.iqr([1, 2, 3, 4, 5]) == pytest.approx(2.0, abs=1e-9)


def test_correlation():
    assert stats.correlation([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0, abs=1e-9)
    assert stats.correlation([1, 2, 3], [6, 4, 2]) == pytest.approx(-1.0, abs=1e-9)


def test_covariance():
    cov = stats.covariance([1, 2, 3], [2, 4, 6], sample=True)
    assert cov == pytest.approx(2.0, abs=1e-9)


def test_correlation_matrix():
    m = stats.correlation_matrix([[1, 2, 3], [2, 4, 6], [3, 2, 1]])
    assert m[0][0] == pytest.approx(1.0)
    assert m[0][1] == pytest.approx(1.0, abs=1e-9)
    assert m[0][2] == pytest.approx(-1.0, abs=1e-9)
    # symmetry
    assert m[1][0] == pytest.approx(m[0][1])


def test_skewness_symmetric_is_zero():
    assert stats.skewness([1, 2, 3, 4, 5]) == pytest.approx(0.0, abs=1e-9)


def test_kurtosis_excess_flag():
    xs = [1, 2, 3, 4, 5, 6, 7, 8]
    ex = stats.kurtosis(xs, excess=True)
    non = stats.kurtosis(xs, excess=False)
    assert non == pytest.approx(ex + 3.0, abs=1e-9)


def test_describe_keys():
    d = stats.describe([1, 2, 3, 4])
    for key in ("count", "mean", "std", "min", "q1", "median", "q3", "max"):
        assert key in d
    assert d["count"] == 4
    assert d["min"] == 1
    assert d["max"] == 4


# --------------------------------------------------------------------------- #
# distributions                                                                #
# --------------------------------------------------------------------------- #
def test_normal_cdf():
    assert stats.normal_cdf(0.0) == pytest.approx(0.5, abs=1e-12)
    assert stats.normal_cdf(1.96) == pytest.approx(0.975, abs=1e-3)


def test_normal_pdf():
    assert stats.normal_pdf(0.0) == pytest.approx(0.39894, abs=1e-4)


def test_normal_ppf():
    assert stats.normal_ppf(0.975) == pytest.approx(1.96, abs=1e-3)
    # round-trip
    assert stats.normal_cdf(stats.normal_ppf(0.3)) == pytest.approx(0.3, abs=1e-6)


def test_t_cdf():
    assert stats.t_cdf(0.0, 10) == pytest.approx(0.5, abs=1e-9)
    assert stats.t_cdf(2.228, 10) == pytest.approx(0.975, abs=2e-3)


def test_f_cdf_monotone():
    assert stats.f_cdf(0.0, 3, 10) == pytest.approx(0.0, abs=1e-12)
    assert stats.f_cdf(1.0, 3, 10) < stats.f_cdf(10.0, 3, 10)
    assert 0.0 < stats.f_cdf(1.0, 3, 10) < 1.0


# --------------------------------------------------------------------------- #
# hypothesis tests                                                             #
# --------------------------------------------------------------------------- #
def test_t_test_1samp_null_true():
    t, p = stats.t_test_1samp([1, 2, 3, 4, 5], 3)
    assert t == pytest.approx(0.0, abs=1e-9)
    assert p == pytest.approx(1.0, abs=1e-9)


def test_t_test_ind_separated():
    t, p = stats.t_test_ind([5, 6, 7, 6, 5], [8, 9, 10, 9, 8])
    assert abs(t) > 5.0
    assert p < 0.01


def test_t_test_paired():
    t, p = stats.t_test_paired([5, 6, 7], [4, 5, 6])
    assert t > 0.0
    assert 0.0 <= p <= 1.0


def test_anova_identical_groups():
    f, p = stats.anova_oneway([1, 2, 3], [1, 2, 3], [1, 2, 3])
    assert f == pytest.approx(0.0, abs=1e-9)
    assert p == pytest.approx(1.0, abs=1e-9)


def test_anova_separated_groups():
    f, p = stats.anova_oneway([1, 2, 3], [11, 12, 13], [21, 22, 23])
    assert f > 10.0
    assert p < 0.01


def test_chi_square_goodness_of_fit():
    chi2, p = stats.chi_square([16, 18, 16, 14, 12, 12, 24])
    assert chi2 > 0.0
    assert 0.0 <= p <= 1.0


def test_chi_square_contingency():
    table = [[10, 20], [20, 40]]  # perfectly independent -> chi2 ~ 0
    chi2, p = stats.chi_square(table)
    assert chi2 == pytest.approx(0.0, abs=1e-9)
    assert p == pytest.approx(1.0, abs=1e-6)


def test_chi_square_contingency_dependent():
    table = [[30, 10], [10, 30]]
    chi2, p = stats.chi_square(table)
    assert chi2 > 0.0
    assert p < 0.01


def test_confidence_interval_mean():
    lo, hi = stats.confidence_interval_mean([1, 2, 3, 4, 5], 0.95)
    assert lo < 3.0 < hi
    assert hi - lo > 0.0


# --------------------------------------------------------------------------- #
# error paths                                                                  #
# --------------------------------------------------------------------------- #
def test_errors():
    with pytest.raises(stats.StatsError):
        stats.mean([])
    with pytest.raises(stats.StatsError):
        stats.quantile([1, 2, 3], 1.5)
    with pytest.raises(stats.StatsError):
        stats.percentile([1, 2, 3], 200)
    with pytest.raises(stats.StatsError):
        stats.correlation([1, 2, 3], [1, 2])
    with pytest.raises(stats.StatsError):
        stats.t_cdf(1.0, 0)
    with pytest.raises(stats.StatsError):
        stats.anova_oneway([1, 2, 3])
    with pytest.raises(stats.StatsError):
        stats.normal_ppf(1.5)
