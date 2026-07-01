"""Tests for abax.core.stats_dist — Excel-named statistics distributions,
correlation/regression helpers, descriptive extras and *IFS conditional
aggregates. Oracle values are documented Excel results, compared with a
relative tolerance of 1e-4.
"""

from __future__ import annotations

import math

import pytest

from abax.core.errors import CellError
from abax.core.stats_dist import SIGNATURES, register
from abax.core.values import RangeValue

# Build a live registry so we call the functions exactly as the engine does.
FUNCS: dict = {}
register(FUNCS)


def call(name, *args):
    return FUNCS[name](list(args))


def close(a, b, rel=1e-4):
    return math.isclose(a, b, rel_tol=rel, abs_tol=1e-9)


# --- registration surface --------------------------------------------------


def test_register_adds_exactly_signature_count():
    fresh: dict = {}
    register(fresh)
    assert len(fresh) == len(SIGNATURES)


def test_every_registered_name_has_a_signature():
    for name in FUNCS:
        assert name in SIGNATURES, f"missing signature for {name}"
    for name in SIGNATURES:
        assert name in FUNCS, f"signature without impl: {name}"


# --- discrete distributions ------------------------------------------------


def test_binomdist():
    assert close(call("BINOMDIST", 6, 10, 0.5, False), 0.205078)
    assert close(call("BINOMDIST", 6, 10, 0.5, True), 0.828125)
    # dotted alias points at the same impl
    assert close(call("BINOM.DIST", 6, 10, 0.5, False), 0.205078)


def test_binominv_critbinom():
    # smallest k with CDF >= alpha
    assert call("BINOM.INV", 10, 0.5, 0.75) == 6.0
    assert call("CRITBINOM", 10, 0.5, 0.75) == 6.0


def test_negbinomdist():
    # P(3 failures before 2nd success, p=0.5) = C(4,3) p^2 q^3 = 4*0.25*0.125
    assert close(call("NEGBINOMDIST", 3, 2, 0.5, False), 0.125)


def test_poisson():
    assert close(call("POISSON", 2, 5, False), 0.084224)
    assert close(call("POISSON", 2, 5, True), 0.124652)
    assert close(call("POISSON.DIST", 2, 5, True), 0.124652)


def test_hypgeomdist():
    assert close(call("HYPGEOMDIST", 1, 4, 8, 20, False), 0.363261)


# --- continuous distributions ----------------------------------------------


def test_expondist():
    assert close(call("EXPONDIST", 0.2, 10, True), 0.864665)
    assert close(call("EXPONDIST", 0.2, 10, False), 1.353353)


def test_gammadist_and_inv():
    assert close(call("GAMMADIST", 10, 9, 2, True), 0.068094)
    assert close(call("GAMMA.INV", 0.068094, 9, 2), 10, rel=1e-3)


def test_gamma_roundtrip():
    for x, a, b in [(10, 9, 2), (3.5, 2.0, 1.5), (20.0, 5.0, 3.0)]:
        p = call("GAMMADIST", x, a, b, True)
        back = call("GAMMA.INV", p, a, b)
        assert close(back, x, rel=1e-4)


def test_betadist_and_inv():
    # Prompt oracle listed 0.68522 "(verify)"; the exact I_0.5(8,10) is
    # 0.6854706 (confirmed against scipy.stats.beta.cdf), so we assert that.
    val = call("BETADIST", 0.5, 8, 10, True)
    assert close(val, 0.6854706, rel=1e-4)
    # Round-trip through the inverse.
    assert close(call("BETA.INV", val, 8, 10), 0.5, rel=1e-3)


def test_weibull():
    assert close(call("WEIBULL", 105, 20, 100, True), 0.929581)


def test_lognorm():
    # LOGNORMDIST(4, 3.5, 1.2) round-trips through LOGINV
    p = call("LOGNORMDIST", 4, 3.5, 1.2, True)
    assert close(call("LOGINV", p, 3.5, 1.2), 4, rel=1e-4)


def test_phi_and_gauss():
    assert close(call("PHI", 0.0), 1.0 / math.sqrt(2 * math.pi))
    assert close(call("GAUSS", 0.0), 0.0, rel=1e-6) or abs(call("GAUSS", 0.0)) < 1e-9
    assert close(call("GAUSS", 2.0), 0.477250, rel=1e-4)


# --- correlation / regression ----------------------------------------------


def test_standardize():
    assert close(call("STANDARDIZE", 42, 40, 1.5), 1.333333)


def test_fisher_roundtrip():
    assert close(call("FISHER", 0.75), 0.972955)
    assert close(call("FISHERINV", 0.972955), 0.75)


def test_pearson_and_steyx():
    ys = RangeValue([[2], [3], [5], [4], [6]])
    xs = RangeValue([[1], [2], [3], [4], [5]])
    r = call("PEARSON", ys, xs)
    assert -1.0 <= r <= 1.0
    # STEYX is non-negative
    se = call("STEYX", ys, xs)
    assert isinstance(se, float) and se >= 0.0


# --- descriptive extras ----------------------------------------------------


def test_devsq():
    r = RangeValue([[4], [5], [8], [7], [11], [4], [3]])
    assert close(call("DEVSQ", r), 48.0)


def test_avedev():
    r = RangeValue([[4], [5], [6], [7], [5], [4], [3]])
    assert close(call("AVEDEV", r), 1.020408)


def test_averagea():
    r = RangeValue([[10], [True], ["text"], [20]])
    # (10 + 1 + 0 + 20) / 4 = 7.75
    assert close(call("AVERAGEA", r), 7.75)


def test_trimmean():
    r = RangeValue([[1], [2], [3], [4], [5], [6], [7], [8], [9], [10]])
    # trim 20% -> drop 1 from each end -> mean of 2..9 = 5.5
    assert close(call("TRIMMEAN", r, 0.2), 5.5)


def test_percentrank():
    r = RangeValue([[1], [2], [3], [4], [5]])
    assert close(call("PERCENTRANK", r, 3), 0.5)
    assert close(call("PERCENTRANK", r, 1), 0.0)
    assert close(call("PERCENTRANK", r, 5), 1.0)


def test_rank_eq_and_avg():
    r = RangeValue([[7], [3.5], [3.5], [1], [2]])
    # descending order (default): 7,3.5,3.5,2,1 -> 3.5 is rank 2 (eq) / 2.5 (avg)
    assert call("RANK.EQ", 3.5, r, 0) == 2.0
    assert close(call("RANK.AVG", 3.5, r, 0), 2.5)


# --- conditional multi-criteria aggregates ---------------------------------


def test_countifs():
    r = RangeValue([[1], [2], [3], [4]])
    assert call("COUNTIFS", r, ">2") == 2.0
    assert call("COUNTIFS", r, ">=2", r, "<=3") == 2.0


def test_sumifs():
    sum_range = RangeValue([[1], [2], [3], [4]])
    crit_range = RangeValue([[1], [2], [3], [4]])
    # rows where crit > 2 -> values 3, 4 -> sum 7
    assert close(call("SUMIFS", sum_range, crit_range, ">2"), 7.0)


def test_averageifs():
    avg_range = RangeValue([[10], [20], [30], [40]])
    crit_range = RangeValue([[1], [2], [3], [4]])
    # rows where crit >= 3 -> 30, 40 -> average 35
    assert close(call("AVERAGEIFS", avg_range, crit_range, ">=3"), 35.0)
    # no matches -> DIV/0!
    res = call("AVERAGEIFS", avg_range, crit_range, ">99")
    assert isinstance(res, CellError) and res.code == CellError.DIV0


def test_maxifs_minifs():
    vals = RangeValue([[10], [20], [30], [40]])
    crit = RangeValue([[1], [2], [3], [4]])
    assert call("MAXIFS", vals, crit, ">=3") == 40.0
    assert call("MINIFS", vals, crit, ">=3") == 30.0
    # no matches -> MAXIFS returns 0
    assert call("MAXIFS", vals, crit, ">99") == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
