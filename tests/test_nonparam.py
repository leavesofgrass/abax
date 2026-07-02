"""Nonparametric / rank statistics (abax.core.science.nonparam).

Oracle-tested against known worked values. Statistics are hardcoded from
textbook examples and cross-checked with scipy's asymptotic methods
(mannwhitneyu(use_continuity=True), wilcoxon(mode='approx'), kruskal,
spearmanr, kendalltau(method='asymptotic')). Statistics are asserted to ~1e-9,
p-values to ~1e-6.
"""

from __future__ import annotations

import math

import pytest

from abax.core.science.nonparam import (
    kendall_tau,
    kruskal_wallis,
    mann_whitney_u,
    spearman_rho,
    wilcoxon_signed_rank,
)
from abax.core.science.stats import StatsError

TOL_STAT = 1e-9
TOL_P = 1e-6


# --------------------------------------------------------------------------- #
# Mann-Whitney U                                                               #
# --------------------------------------------------------------------------- #
def test_mann_whitney_fully_separated():
    # Two disjoint samples: group A entirely below group B => U = 0.
    a = [1, 2, 3, 4, 5]
    b = [6, 7, 8, 9, 10]
    res = mann_whitney_u(a, b)
    assert res.statistic == pytest.approx(0.0, abs=TOL_STAT)
    # scipy asymptotic two-sided with continuity correction.
    assert res.pvalue == pytest.approx(0.012185780355344813, abs=TOL_P)


def test_mann_whitney_overlapping():
    a = [1.83, 0.50, 1.62, 2.48, 1.68, 1.88, 1.55, 3.06, 1.30]
    b = [0.878, 0.647, 0.598, 2.05, 1.06, 1.29, 1.06, 3.14, 1.29]
    res = mann_whitney_u(a, b)
    # We report the smaller of the two U's (scipy reports U1 = 58; U2 = 23).
    assert res.statistic == pytest.approx(23.0, abs=TOL_STAT)
    assert res.pvalue == pytest.approx(0.13291945818531892, abs=TOL_P)


def test_mann_whitney_rejects_empty():
    with pytest.raises(StatsError):
        mann_whitney_u([], [1, 2, 3])


def test_mann_whitney_rejects_all_tied():
    with pytest.raises(StatsError):
        mann_whitney_u([5, 5, 5], [5, 5, 5])


# --------------------------------------------------------------------------- #
# Wilcoxon signed-rank                                                         #
# --------------------------------------------------------------------------- #
def test_wilcoxon_known_pair():
    x = [125, 115, 130, 140, 140, 115, 140, 125, 140, 135]
    y = [110, 122, 125, 120, 140, 124, 123, 137, 135, 145]
    res = wilcoxon_signed_rank(x, y)
    # scipy wilcoxon(mode='approx', correction=True): W = 18, p = 0.63528932.
    assert res.statistic == pytest.approx(18.0, abs=TOL_STAT)
    assert res.pvalue == pytest.approx(0.6352893188352069, abs=TOL_P)


def test_wilcoxon_drops_zero_differences():
    # The zero-diff pair (3,3) is dropped; the remaining diffs are all +ve.
    x = [3, 5, 7, 9]
    y = [3, 4, 6, 8]
    res = wilcoxon_signed_rank(x, y)
    # n = 3 nonzero diffs, all positive => W = min(6, 0) = 0.
    assert res.statistic == pytest.approx(0.0, abs=TOL_STAT)


def test_wilcoxon_length_mismatch():
    with pytest.raises(StatsError):
        wilcoxon_signed_rank([1, 2, 3], [1, 2])


def test_wilcoxon_all_zero_diffs():
    with pytest.raises(StatsError):
        wilcoxon_signed_rank([1, 2, 3], [1, 2, 3])


# --------------------------------------------------------------------------- #
# Kruskal-Wallis H                                                             #
# --------------------------------------------------------------------------- #
def test_kruskal_three_groups():
    g1 = [2.9, 3.0, 2.5, 2.6, 3.2]
    g2 = [3.8, 2.7, 4.0, 2.4]
    g3 = [2.8, 3.4, 3.7, 2.2, 2.0]
    res = kruskal_wallis(g1, g2, g3)
    # scipy.stats.kruskal: H = 0.7714285714, df = 2, p = 0.6799647736.
    assert res.statistic == pytest.approx(0.7714285714285722, abs=1e-6)
    assert res.df == 2
    assert res.pvalue == pytest.approx(0.6799647735788936, abs=TOL_P)


def test_kruskal_with_ties():
    # A set with ties across groups; verified against scipy.stats.kruskal.
    a = [1, 2, 3, 4]
    b = [2, 3, 4, 5]
    c = [3, 4, 5, 6]
    res = kruskal_wallis(a, b, c)
    assert res.df == 2
    # scipy.stats.kruskal (tie-corrected): H = 3.596920290, p = 0.165553621.
    assert res.statistic == pytest.approx(3.596920289855073, abs=1e-6)
    assert res.pvalue == pytest.approx(0.16555362062824724, abs=TOL_P)


def test_kruskal_needs_two_groups():
    with pytest.raises(StatsError):
        kruskal_wallis([1, 2, 3])


# --------------------------------------------------------------------------- #
# Spearman rho                                                                 #
# --------------------------------------------------------------------------- #
def test_spearman_perfect_monotonic():
    # A strictly monotonic pairing => rho = 1.0 exactly.
    res = spearman_rho([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
    assert res.statistic == pytest.approx(1.0, abs=TOL_STAT)
    assert res.pvalue == pytest.approx(0.0, abs=TOL_P)


def test_spearman_perfect_negative():
    res = spearman_rho([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])
    assert res.statistic == pytest.approx(-1.0, abs=TOL_STAT)


def test_spearman_with_ties():
    res = spearman_rho([1, 2, 3, 4, 5], [5, 6, 7, 8, 7])
    # scipy.stats.spearmanr: rho = 0.8207826817, p = 0.0885870053.
    assert res.statistic == pytest.approx(0.8207826816681233, abs=1e-6)
    assert res.pvalue == pytest.approx(0.08858700531354384, abs=TOL_P)


def test_spearman_length_mismatch():
    with pytest.raises(StatsError):
        spearman_rho([1, 2, 3], [1, 2])


def test_spearman_constant_input():
    with pytest.raises(StatsError):
        spearman_rho([1, 1, 1, 1], [2, 3, 4, 5])


# --------------------------------------------------------------------------- #
# Kendall tau-b                                                                #
# --------------------------------------------------------------------------- #
def test_kendall_perfect_concordant():
    res = kendall_tau([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
    assert res.statistic == pytest.approx(1.0, abs=TOL_STAT)


def test_kendall_with_ties():
    a = [12, 2, 1, 12, 2]
    b = [1, 4, 7, 1, 0]
    res = kendall_tau(a, b)
    # scipy.stats.kendalltau: tau = -0.4714045208, asymptotic p = 0.2827454599.
    assert res.statistic == pytest.approx(-0.4714045207910316, abs=1e-6)
    assert res.pvalue == pytest.approx(0.28274545993277467, abs=TOL_P)


def test_kendall_no_ties_asymptotic():
    a = list(range(12))
    b = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8]
    res = kendall_tau(a, b)
    # scipy.stats.kendalltau(method='asymptotic'): tau = 0.3940062613,
    # p = 0.0822777727.
    assert res.statistic == pytest.approx(0.3940062612820493, abs=1e-6)
    assert res.pvalue == pytest.approx(0.08227777272211645, abs=TOL_P)


def test_kendall_length_mismatch():
    with pytest.raises(StatsError):
        kendall_tau([1, 2, 3], [1, 2])


def test_kendall_constant_input():
    with pytest.raises(StatsError):
        kendall_tau([1, 1, 1, 1], [2, 3, 4, 5])


# --------------------------------------------------------------------------- #
# module wiring                                                                #
# --------------------------------------------------------------------------- #
def test_pvalues_are_finite_probabilities():
    for res in (
        mann_whitney_u([1, 2, 3], [4, 5, 6]),
        wilcoxon_signed_rank([1, 3, 5, 7], [2, 1, 6, 4]),
        kruskal_wallis([1, 2, 3], [4, 5, 6], [7, 8, 9]),
        spearman_rho([1, 2, 3, 4], [4, 3, 2, 1]),
        kendall_tau([1, 2, 3, 4], [1, 3, 2, 4]),
    ):
        assert 0.0 <= res.pvalue <= 1.0
        assert math.isfinite(res.statistic)
