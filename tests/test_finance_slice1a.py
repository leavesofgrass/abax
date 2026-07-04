"""Finance-tail slice 1a — FVSCHEDULE and ISPMT.

Oracle values are the worked examples from the Microsoft function
documentation; abax reuses the same closed-form definitions Excel and gnumeric
implement, so these pin exact-value fidelity, not just registration.

* FVSCHEDULE(principal, schedule) = principal * PROD(1 + rate_i)
* ISPMT(rate, per, nper, pv)      = pv * rate * (per/nper - 1)   (level-principal
  loan interest; negative under Excel's pay-out-is-negative sign convention)
"""

from __future__ import annotations

import math

from abax.core.errors import CellError
from abax.core.functions import FUNCTIONS
from abax.core.values import RangeValue


def v(name, *a):
    return FUNCTIONS[name](list(a))


def test_registered():
    assert "FVSCHEDULE" in FUNCTIONS
    assert "ISPMT" in FUNCTIONS


# --- FVSCHEDULE ------------------------------------------------------------


def test_fvschedule_doc_example():
    # Excel doc: FVSCHEDULE(1, {0.09, 0.11, 0.1}) = 1.3308900 (a row range).
    row = RangeValue([[0.09, 0.11, 0.1]])
    assert math.isclose(v("FVSCHEDULE", 1, row), 1.33089, rel_tol=1e-9)


def test_fvschedule_column_range():
    # Orientation is irrelevant: a column of the same rates gives the same FV.
    col = RangeValue([[0.09], [0.11], [0.1]])
    assert math.isclose(v("FVSCHEDULE", 1, col), 1.33089, rel_tol=1e-9)


def test_fvschedule_scales_with_principal():
    row = RangeValue([[0.09, 0.11, 0.1]])
    assert math.isclose(v("FVSCHEDULE", 100000, row), 133089.0, rel_tol=1e-9)


def test_fvschedule_zero_and_negative_rates():
    # A 0% year is a no-op; a negative rate compounds a loss.
    sched = RangeValue([[0.05, 0.0, -0.10]])
    assert math.isclose(v("FVSCHEDULE", 1000, sched), 1000 * 1.05 * 1.0 * 0.90)


def test_fvschedule_empty_schedule_returns_principal():
    # No rates to compound -> the principal is returned unchanged.
    assert v("FVSCHEDULE", 500, RangeValue([[]])) == 500.0


def test_fvschedule_nonnumeric_cell_is_value_error():
    # A text cell in the schedule is #VALUE! in Excel, not silently skipped.
    got = v("FVSCHEDULE", 1, RangeValue([[0.09, "x", 0.1]]))
    assert got == CellError(CellError.VALUE)


def test_fvschedule_missing_principal_is_value_error():
    assert v("FVSCHEDULE", "", RangeValue([[0.09]])) == CellError(CellError.VALUE)


# --- ISPMT -----------------------------------------------------------------


def test_ispmt_first_month_doc_example():
    # Excel doc: ISPMT(10%/12, 1, 3*12, 8000000) = -64814.8148148148 — interest
    # for the first monthly period of a level-principal 3-year loan.
    got = v("ISPMT", 0.1 / 12, 1, 3 * 12, 8000000)
    assert math.isclose(got, -64814.8148148148, rel_tol=1e-12)


def test_ispmt_first_year_doc_example():
    # Excel doc: ISPMT(10%, 1, 3, 8000000) = -533333.333333333.
    got = v("ISPMT", 0.1, 1, 3, 8000000)
    assert math.isclose(got, -533333.333333333, rel_tol=1e-12)


def test_ispmt_period_zero_is_full_interest():
    # Before any principal is repaid the whole balance accrues interest.
    assert math.isclose(v("ISPMT", 0.05, 0, 12, 1000), -50.0, rel_tol=1e-12)


def test_ispmt_final_period_is_zero():
    # In the last level-principal period the balance is gone, so interest is 0.
    assert v("ISPMT", 0.05, 3, 3, 1000) == 0.0


def test_ispmt_linear_in_period():
    # Interest falls linearly with the period number (level principal): the drop
    # from per=1 to per=2 equals one nper-th of the period-0 interest.
    pv, rate, nper = 1000.0, 0.06, 10
    i0 = v("ISPMT", rate, 0, nper, pv)
    i1 = v("ISPMT", rate, 1, nper, pv)
    i2 = v("ISPMT", rate, 2, nper, pv)
    assert math.isclose(i1 - i2, i0 / nper, rel_tol=1e-12)


def test_ispmt_nper_zero_is_div0():
    assert v("ISPMT", 0.05, 1, 0, 1000) == CellError(CellError.DIV0)


def test_ispmt_missing_arg_is_value_error():
    assert v("ISPMT", 0.05, 1, 12) == CellError(CellError.VALUE)
