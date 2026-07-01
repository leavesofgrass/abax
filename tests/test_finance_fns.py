"""Tests for abax.core.finance_fns (Excel-compatible financial functions).

Oracle values are documented Excel results; compared with math.isclose at
rel_tol=1e-4 unless an exact integer/ratio is expected.
"""

from __future__ import annotations

import math

from abax.core import finance_fns as F
from abax.core.errors import CellError


def close(a, b, rel_tol=1e-4):
    assert not isinstance(a, CellError), f"unexpected error: {a}"
    return math.isclose(a, b, rel_tol=rel_tol)


# --- time value of money ---------------------------------------------------


def test_pmt():
    assert close(F._fn_pmt([0.08 / 12, 120, 10000]), -121.33)


def test_pmt_zero_rate():
    assert close(F._fn_pmt([0.0, 10, 1000]), -100.0)


def test_fv():
    assert close(F._fn_fv([0.06 / 12, 120, -100]), 16387.93)


def test_fv_zero_rate():
    assert close(F._fn_fv([0.0, 12, -100, 0, 0]), 1200.0)


def test_pv():
    assert close(F._fn_pv([0.08, 20, 500, 0, 0]), -4909.07)


def test_nper():
    assert close(F._fn_nper([0.08 / 12, -121.33, 10000]), 120.0, rel_tol=1e-3)


def test_rate():
    r = F._fn_rate([120, -121.33, 10000])
    assert close(r, 0.08 / 12, rel_tol=1e-3)


def test_ipmt_ppmt_sum_to_pmt():
    args = [0.10, 1, 3, 8000]
    ip = F._fn_ipmt(args)
    pp = F._fn_ppmt(args)
    pmt = F._fn_pmt([0.10, 3, 8000])
    assert close(ip, -800.0)
    assert close(ip + pp, pmt)


def test_ipmt_out_of_range():
    assert isinstance(F._fn_ipmt([0.10, 5, 3, 8000]), CellError)


# --- cashflow analysis -----------------------------------------------------


def test_npv_initial_outside():
    # Initial cost paid today (outside NPV), returns discounted from period 1.
    npv = F._fn_npv([0.1, 3000, 4200, 6800])
    assert close(npv - 10000, 1307.29)


def test_npv_full_stream():
    # Documented Excel example with the outflow discounted as period 1.
    assert close(F._fn_npv([0.1, -10000, 3000, 4200, 6800]), 1188.44)


def test_irr():
    from abax.core.values import RangeValue

    rv = RangeValue([[-70000, 12000, 15000, 18000, 21000, 26000]])
    assert close(F._fn_irr([rv]), 0.0866, rel_tol=1e-3)


def test_irr_no_convergence():
    from abax.core.values import RangeValue

    rv = RangeValue([[100, 200, 300]])  # all positive: no root
    assert isinstance(F._fn_irr([rv]), CellError)


def test_xnpv_xirr():
    from abax.core.values import RangeValue

    vals = RangeValue([[-10000, 2750, 4250, 3250, 2750]])
    dates = RangeValue([[
        "2008-01-01", "2008-03-01", "2008-10-30", "2009-02-15", "2009-04-01",
    ]])
    assert close(F._fn_xirr([vals, dates]), 0.3733, rel_tol=1e-3)
    # XNPV at the XIRR rate must be ~0.
    r = F._fn_xirr([vals, dates])
    assert abs(F._fn_xnpv([r, vals, dates])) < 1e-3


def test_mirr():
    from abax.core.values import RangeValue

    rv = RangeValue([[-120000, 39000, 30000, 21000, 37000, 46000]])
    assert close(F._fn_mirr([rv, 0.10, 0.12]), 0.1261)


def test_cumipmt():
    # First year interest of a 30-yr 9% loan on 125000.
    v = F._fn_cumipmt([0.09 / 12, 30 * 12, 125000, 13, 24, 0])
    assert close(v, -11135.23)


def test_cumprinc():
    v = F._fn_cumprinc([0.09 / 12, 30 * 12, 125000, 13, 24, 0])
    assert isinstance(v, float) and v < 0


# --- depreciation ----------------------------------------------------------


def test_sln():
    assert F._fn_sln([30000, 7500, 10]) == 2250.0


def test_syd():
    assert close(F._fn_syd([30000, 7500, 10, 1]), 4090.91)


def test_ddb():
    assert F._fn_ddb([2400, 300, 10, 1]) == 480.0


def test_db():
    # Documented Excel example (cost 1,000,000; salvage 100,000; life 6; month 7).
    assert close(F._fn_db([1000000, 100000, 6, 1, 7]), 186083.33)
    assert close(F._fn_db([1000000, 100000, 6, 2, 7]), 259639.42)


def test_vdb():
    # VDB of first period equals DDB of first period.
    assert close(F._fn_vdb([2400, 300, 10, 0, 1]), 480.0)


# --- rates & misc ----------------------------------------------------------


def test_effect():
    assert close(F._fn_effect([0.0525, 4]), 0.05354)


def test_nominal():
    assert close(F._fn_nominal([0.05354, 4]), 0.0525, rel_tol=1e-3)


def test_effect_nominal_roundtrip():
    e = F._fn_effect([0.0525, 4])
    assert close(F._fn_nominal([e, 4]), 0.0525)


def test_dollarde_dollarfr():
    assert close(F._fn_dollarde([1.02, 16]), 1.125)
    assert close(F._fn_dollarfr([1.125, 16]), 1.02)


def test_pduration():
    assert close(F._fn_pduration([0.025, 2000, 2200]), 3.86, rel_tol=1e-2)


def test_rri():
    assert close(F._fn_rri([96, 10000, 11000]), 0.000993, rel_tol=1e-3)


# --- error handling --------------------------------------------------------


def test_missing_required_arg_is_value_error():
    assert isinstance(F._fn_fv([]), CellError)
    assert isinstance(F._fn_sln([100, 10]), CellError)


def test_sln_zero_life():
    assert isinstance(F._fn_sln([1000, 100, 0]), CellError)


# --- public surface --------------------------------------------------------


def test_register_adds_exactly_signature_count():
    functions: dict = {}
    F.register(functions)
    assert len(functions) == len(F.SIGNATURES)
    for name in functions:
        assert name in F.SIGNATURES
    for name in F.SIGNATURES:
        assert name in functions


def test_every_registered_name_callable():
    functions: dict = {}
    F.register(functions)
    for name, fn in functions.items():
        assert callable(fn), name
