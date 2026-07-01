"""Distribution formula functions (normal / t / F / chi-square) + confidence.

These expose abax's existing pure-Python distribution machinery as Excel-named
spreadsheet functions familiar to spreadsheet and R/RStudio users. Values are
checked against standard textbook critical values.
"""

from __future__ import annotations

import math

import pytest

from abax.core.errors import is_error
from abax.core.science import stats
from abax.core.sheet import Sheet


def _val(formula: str):
    s = Sheet()
    s.set("A1", formula)
    return s.get_value(0, 0)


def test_stats_inverse_helpers():
    assert stats.chi_square_ppf(0.95, 1) == pytest.approx(3.8415, abs=1e-2)
    assert stats.t_ppf(0.975, 10) == pytest.approx(2.2281, abs=1e-3)
    assert stats.f_ppf(0.95, 5, 10) == pytest.approx(3.3258, abs=1e-2)
    assert stats.chi_square_cdf(3.8415, 1) == pytest.approx(0.95, abs=1e-3)


def test_normal_formulas():
    assert _val("=NORMDIST(0,0,1,TRUE)") == pytest.approx(0.5)
    assert _val("=NORMDIST(0,0,1,FALSE)") == pytest.approx(1.0 / math.sqrt(2 * math.pi), abs=1e-6)
    assert _val("=NORMINV(0.975,0,1)") == pytest.approx(1.95996, abs=1e-3)


def test_t_formulas():
    assert _val("=TINV(0.05,10)") == pytest.approx(2.2281, abs=1e-3)
    assert _val("=TDIST(2.2281,10,2)") == pytest.approx(0.05, abs=1e-3)
    assert _val("=TDIST(2.2281,10,1)") == pytest.approx(0.025, abs=1e-3)


def test_f_and_chi_formulas():
    assert _val("=FINV(0.05,5,10)") == pytest.approx(3.3258, abs=1e-2)
    assert _val("=FDIST(3.3258,5,10)") == pytest.approx(0.05, abs=1e-3)
    assert _val("=CHIINV(0.05,1)") == pytest.approx(3.8415, abs=1e-2)
    assert _val("=CHIDIST(3.8415,1)") == pytest.approx(0.05, abs=1e-3)


def test_confidence():
    assert _val("=CONFIDENCE(0.05,1,100)") == pytest.approx(0.19600, abs=1e-3)


def test_bad_args_return_error():
    assert is_error(_val("=TINV(2,10)"))     # p outside (0,1)
    assert is_error(_val("=CHIDIST(1,-1)"))  # non-positive df
    assert is_error(_val("=TDIST(-1,10,2)")) # Excel TDIST requires x >= 0
