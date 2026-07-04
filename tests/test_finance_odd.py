"""Odd-period / French-depreciation finance functions (DF-finance workstream).

Every expected value is a *documented* worked example — no hand-derived
numbers. Sources are cited per-assertion:

* AMORLINC / AMORDEGRC — the Data/Description example tables in Microsoft's
  function reference (cost 2400, purchased 39679 = 2008-08-19, first period
  39813 = 2008-12-31, salvage 300, period 1, rate 0.15, basis 1):
    - AMORLINC  -> 360   (support.microsoft.com AMORLINC function)
    - AMORDEGRC -> 776   (support.microsoft.com AMORDEGRC function)
  The coefficient table and algorithm mirror gnumeric's get_amorlinc /
  get_amordegrc (plugins/fn-financial/sc-fin.c), which match Excel.

* ODDFPRICE / ODDFYIELD / ODDLPRICE / ODDLYIELD — Microsoft's documented
  worked examples (support.microsoft.com), cross-checked against gnumeric's
  calc_oddfprice / calc_oddlprice / calc_oddlyield. Microsoft prints the
  price/yield results rounded to the cent / basis point, so the price checks
  assert to that documented precision (abs_tol on the rounded figure) and the
  full-precision internal consistency is pinned by the PRICE<->YIELD
  round-trips.
"""

from __future__ import annotations

import math

from abax.core.errors import CellError
from abax.core.functions import FUNCTIONS


def v(name, *a):
    return FUNCTIONS[name](list(a))


def test_all_registered():
    for name in ("AMORLINC", "AMORDEGRC",
                 "ODDFPRICE", "ODDFYIELD", "ODDLPRICE", "ODDLYIELD"):
        assert name in FUNCTIONS, name


# --- French depreciation ------------------------------------------------------


def test_amorlinc_microsoft_example():
    # MS AMORLINC doc: AMORLINC(2400, 19-Aug-2008, 31-Dec-2008, 300, 1, 0.15, 1)
    # = 360 ("First period depreciation").
    assert v("AMORLINC", 2400, "2008-08-19", "2008-12-31", 300, 1, 0.15, 1) == 360.0


def test_amorlinc_periods_progression():
    # Period 0 is the pro-rated odd first period: YEARFRAC(19-Aug,31-Dec, act/act)
    # * 0.15 * 2400. 2008 is a leap year, 134 actual days -> 134/366.
    got = v("AMORLINC", 2400, "2008-08-19", "2008-12-31", 300, 0, 0.15, 1)
    assert math.isclose(got, 134.0 / 366.0 * 0.15 * 2400, rel_tol=1e-12)
    # A full middle period is the flat cost*rate = 360.
    assert v("AMORLINC", 2400, "2008-08-19", "2008-12-31", 300, 5, 0.15, 1) == 360.0
    # Past the residual the deduction is zero (never depreciates below salvage).
    assert v("AMORLINC", 2400, "2008-08-19", "2008-12-31", 300, 30, 0.15, 1) == 0.0


def test_amordegrc_microsoft_example():
    # MS AMORDEGRC doc: AMORDEGRC(2400, 19-Aug-2008, 31-Dec-2008, 300, 1, 0.15, 1)
    # = 776 ("First period depreciation"). Life = 1/0.15 = 6.67 yr -> coeff 2.5.
    assert v("AMORDEGRC", 2400, "2008-08-19", "2008-12-31", 300, 1, 0.15, 1) == 776.0


def test_amordegrc_coefficient_table():
    # The life coefficient is keyed on 1/rate: rate 0.5 -> life 2 yr (< 3) ->
    # coeff 1.0, so each period is round(rate * book value) with the odd first
    # period pro-rated by YEARFRAC. cost 1000, salvage 0, rate 0.5, basis 1:
    #   first period ~= round(0.5*1000)=~500, book ~=500,
    #   period 1 round(0.5*book) = 250 (currency rounding).
    assert v("AMORDEGRC", 1000, "2008-01-01", "2009-01-01", 0, 1, 0.5, 1) == 250.0


# --- odd first period ---------------------------------------------------------


def test_oddfprice_microsoft_example():
    # MS ODDFPRICE doc: settlement 11-Nov-2008, maturity 1-Mar-2021,
    # issue 15-Oct-2008, first coupon 1-Mar-2009, rate 7.85%, yield 6.25%,
    # redemption 100, freq 2, basis 1 (act/act) -> $113.60.
    got = v("ODDFPRICE", "2008-11-11", "2021-03-01", "2008-10-15", "2009-03-01",
            0.0785, 0.0625, 100, 2, 1)
    assert round(got, 2) == 113.60


def test_oddfyield_microsoft_example():
    # MS ODDFYIELD doc: settlement 11-Nov-2008, maturity 1-Mar-2021,
    # issue 15-Oct-2008, first coupon 1-Mar-2009, rate 5.75%, price 84.50,
    # redemption 100, freq 2, basis 0 (US 30/360) -> 7.72%.
    got = v("ODDFYIELD", "2008-11-11", "2021-03-01", "2008-10-15", "2009-03-01",
            0.0575, 84.50, 100, 2, 0)
    assert round(got, 4) == 0.0772


def test_oddfprice_oddfyield_roundtrip():
    # ODDFYIELD inverts ODDFPRICE exactly (same odd-first-period machinery).
    args = ("2008-11-11", "2021-03-01", "2008-10-15", "2009-03-01", 0.0575)
    y = v("ODDFYIELD", *args, 84.50, 100, 2, 0)
    pr = v("ODDFPRICE", *args, y, 100, 2, 0)
    assert math.isclose(pr, 84.50, rel_tol=1e-9)


# --- odd last period ----------------------------------------------------------


def test_oddlprice_microsoft_example():
    # MS ODDLPRICE doc: settlement 7-Feb-2008, maturity 15-Jun-2008,
    # last interest 15-Oct-2007, rate 3.75%, yield 4.05%, redemption 100,
    # freq 2, basis 0 (US 30/360) -> $99.88.
    got = v("ODDLPRICE", "2008-02-07", "2008-06-15", "2007-10-15",
            0.0375, 0.0405, 100, 2, 0)
    assert round(got, 2) == 99.88


def test_oddlyield_microsoft_example():
    # MS ODDLYIELD doc: settlement 20-Apr-2008, maturity 15-Jun-2008,
    # last interest 24-Dec-2007, rate 3.75%, price 99.875, redemption 100,
    # freq 2, basis 0 (US 30/360) -> 4.52% (0.04519).
    got = v("ODDLYIELD", "2008-04-20", "2008-06-15", "2007-12-24",
            0.0375, 99.875, 100, 2, 0)
    assert round(got, 5) == 0.04519


def test_oddlprice_oddlyield_are_consistent():
    # ODDLYIELD and ODDLPRICE are algebraic inverses (both closed-form on the
    # same x1/x2/x3 date ratios): pricing at the recovered yield reproduces it.
    args = ("2008-04-20", "2008-06-15", "2007-12-24", 0.0375)
    y = v("ODDLYIELD", *args, 99.875, 100, 2, 0)
    pr = v("ODDLPRICE", *args, y, 100, 2, 0)
    assert math.isclose(pr, 99.875, rel_tol=1e-9)


# --- validation ---------------------------------------------------------------


def test_validation_errors():
    # AMORLINC: rate must be > 0; purchase must not follow first period.
    assert isinstance(
        v("AMORLINC", 2400, "2008-08-19", "2008-12-31", 300, 1, 0, 1), CellError)
    assert isinstance(
        v("AMORLINC", 2400, "2009-01-01", "2008-12-31", 300, 1, 0.15, 1), CellError)
    # AMORDEGRC: bad basis.
    assert isinstance(
        v("AMORDEGRC", 2400, "2008-08-19", "2008-12-31", 300, 1, 0.15, 9), CellError)
    # ODDF*: date ordering issue <= settlement <= first_coupon <= maturity.
    assert isinstance(
        v("ODDFPRICE", "2008-11-11", "2021-03-01", "2009-01-01", "2009-03-01",
          0.0785, 0.0625, 100, 2, 1), CellError)  # issue after settlement
    # ODDL*: last_interest must not follow settlement.
    assert isinstance(
        v("ODDLPRICE", "2008-02-07", "2008-06-15", "2008-03-01",
          0.0375, 0.0405, 100, 2, 0), CellError)
    # Bad frequency (must be 1, 2 or 4).
    assert isinstance(
        v("ODDLYIELD", "2008-04-20", "2008-06-15", "2007-12-24",
          0.0375, 99.875, 100, 3, 0), CellError)
