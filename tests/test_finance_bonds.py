"""Wave D tail — bond/security financial functions (finance_bonds pack).

Oracle values are the worked examples from the Microsoft function
documentation, cross-checked by hand day counts where noted.
"""

from __future__ import annotations

import math

from abax.core.errors import CellError
from abax.core.functions import FUNCTIONS


def v(name, *a):
    return FUNCTIONS[name](list(a))


def test_all_registered():
    for name in ("COUPPCD", "COUPNCD", "COUPNUM", "COUPDAYBS", "COUPDAYS",
                 "COUPDAYSNC", "PRICE", "YIELD", "DURATION", "MDURATION",
                 "PRICEDISC", "YIELDDISC", "DISC", "INTRATE", "RECEIVED",
                 "ACCRINT", "ACCRINTM", "PRICEMAT", "YIELDMAT",
                 "TBILLEQ", "TBILLPRICE", "TBILLYIELD"):
        assert name in FUNCTIONS, name


# --- coupon schedule ----------------------------------------------------------


def test_coupon_dates():
    # Excel doc example: settlement 25-Jan-2011, maturity 15-Nov-2011, semiannual.
    assert v("COUPPCD", "2011-01-25", "2011-11-15", 2, 1) == "2010-11-15"
    assert v("COUPNCD", "2011-01-25", "2011-11-15", 2, 1) == "2011-05-15"


def test_coupon_day_counts():
    # Excel doc examples (basis 1 = actual/actual).
    assert v("COUPDAYBS", "2011-01-25", "2011-11-15", 2, 1) == 71
    assert v("COUPDAYS", "2011-01-25", "2011-11-15", 2, 1) == 181
    assert v("COUPDAYSNC", "2011-01-25", "2011-11-15", 2, 1) == 110
    # 30/360 basis: a semiannual period is always 180 days.
    assert v("COUPDAYS", "2011-01-25", "2011-11-15", 2, 0) == 180


def test_coupnum():
    # Excel doc: COUPNUM(25-Jan-2007, 15-Nov-2008, 2, 1) = 4.
    assert v("COUPNUM", "2007-01-25", "2008-11-15", 2, 1) == 4
    # End-of-month rule: maturity on a month end keeps coupons on month ends.
    assert v("COUPPCD", "2026-01-15", "2026-08-31", 2, 0) == "2025-08-31"
    assert v("COUPNCD", "2026-01-15", "2026-08-31", 2, 0) == "2026-02-28"


def test_coupon_validation():
    assert isinstance(v("COUPNUM", "2011-11-15", "2011-01-25", 2, 1), CellError)
    assert isinstance(v("COUPNUM", "2011-01-25", "2011-11-15", 3, 1), CellError)


# --- PRICE / YIELD / DURATION ---------------------------------------------------


def test_price():
    # Excel doc: PRICE(15-Feb-08, 15-Nov-17, 5.75%, 6.5%, 100, 2, 0) = 94.63436162
    got = v("PRICE", "2008-02-15", "2017-11-15", 0.0575, 0.065, 100, 2, 0)
    assert math.isclose(got, 94.63436162, rel_tol=1e-8)


def test_yield_inverts_price():
    # Excel doc: YIELD(15-Feb-08, 15-Nov-16, 5.75%, 95.04287, 100, 2, 0) = 0.065
    got = v("YIELD", "2008-02-15", "2016-11-15", 0.0575, 95.04287, 100, 2, 0)
    assert math.isclose(got, 0.065, rel_tol=1e-6)
    # Round trip: PRICE at the recovered yield reproduces the price.
    pr = v("PRICE", "2008-02-15", "2016-11-15", 0.0575, got, 100, 2, 0)
    assert math.isclose(pr, 95.04287, rel_tol=1e-9)


def test_price_single_period():
    # One coupon left: the short simple-interest formula. At yield == coupon
    # rate and settlement on a coupon date, the bond prices at par.
    got = v("PRICE", "2017-05-15", "2017-11-15", 0.06, 0.06, 100, 2, 0)
    assert math.isclose(got, 100.0, rel_tol=1e-9)


def test_duration():
    # Excel doc: DURATION(1-Jan-08, 1-Jan-16, 8%, 9%, 2, 1) = 5.993775
    got = v("DURATION", "2008-01-01", "2016-01-01", 0.08, 0.09, 2, 1)
    assert math.isclose(got, 5.993775, rel_tol=1e-6)
    # Excel doc: MDURATION same args = 5.73567
    got_m = v("MDURATION", "2008-01-01", "2016-01-01", 0.08, 0.09, 2, 1)
    assert math.isclose(got_m, 5.73567, rel_tol=1e-5)
    assert math.isclose(got_m, got / 1.045, rel_tol=1e-12)


# --- discounted securities -------------------------------------------------------


def test_pricedisc_and_yielddisc():
    # Excel doc: PRICEDISC(16-Feb-08, 1-Mar-08, 5.25%, 100, 2) = 99.79583333
    got = v("PRICEDISC", "2008-02-16", "2008-03-01", 0.0525, 100, 2)
    assert math.isclose(got, 99.79583333, rel_tol=1e-9)
    # Excel doc: YIELDDISC(16-Feb-08, 1-Mar-08, 99.795, 100, 2) = 0.052823
    got = v("YIELDDISC", "2008-02-16", "2008-03-01", 99.795, 100, 2)
    assert math.isclose(got, 0.052823, rel_tol=1e-4)


def test_disc():
    # Excel doc: DISC(25-Jan-07, 15-Jun-07, 97.975, 100, 1) = 0.052420
    got = v("DISC", "2007-01-25", "2007-06-15", 97.975, 100, 1)
    assert math.isclose(got, 0.052420, rel_tol=1e-4)


def test_intrate_and_received():
    # Excel doc: INTRATE(15-Feb-08, 15-May-08, 1000000, 1014420, 2) = 0.05768
    got = v("INTRATE", "2008-02-15", "2008-05-15", 1000000, 1014420, 2)
    assert math.isclose(got, 0.05768, rel_tol=1e-6)
    # Excel doc: RECEIVED(15-Feb-08, 15-May-08, 1000000, 5.75%, 2) = 1014584.654
    got = v("RECEIVED", "2008-02-15", "2008-05-15", 1000000, 0.0575, 2)
    assert math.isclose(got, 1014584.654, rel_tol=1e-8)


# --- interest at maturity ---------------------------------------------------------


def test_accrint():
    # Excel doc: ACCRINT(1-Mar-08, 31-Aug-08, 1-May-08, 10%, 1000, 2, 0) = 16.666667
    got = v("ACCRINT", "2008-03-01", "2008-08-31", "2008-05-01", 0.1, 1000, 2, 0)
    assert math.isclose(got, 16.666667, rel_tol=1e-6)


def test_accrintm():
    # Excel doc: ACCRINTM(1-Apr-08, 15-Jun-08, 10%, 1000, 3) = 20.54794521
    got = v("ACCRINTM", "2008-04-01", "2008-06-15", 0.1, 1000, 3)
    assert math.isclose(got, 20.54794521, rel_tol=1e-9)


def test_pricemat_and_yieldmat():
    # Excel doc: PRICEMAT(15-Feb-08, 13-Apr-08, 11-Nov-07, 6.1%, 6.1%, 0) = 99.98449888
    got = v("PRICEMAT", "2008-02-15", "2008-04-13", "2007-11-11", 0.061, 0.061, 0)
    assert math.isclose(got, 99.98449888, rel_tol=1e-9)
    # Excel doc: YIELDMAT(15-Mar-08, 3-Nov-08, 8-Nov-07, 6.25%, 100.0123, 0) = 0.060954
    got = v("YIELDMAT", "2008-03-15", "2008-11-03", "2007-11-08", 0.0625, 100.0123, 0)
    assert math.isclose(got, 0.060954, rel_tol=1e-4)


# --- Treasury bills ----------------------------------------------------------------


def test_tbill_trio():
    # Excel doc: TBILLEQ(31-Mar-08, 1-Jun-08, 9.14%) = 0.09415149
    got = v("TBILLEQ", "2008-03-31", "2008-06-01", 0.0914)
    assert math.isclose(got, 0.09415149, rel_tol=1e-6)
    # Excel doc: TBILLPRICE(31-Mar-08, 1-Jun-08, 9%) = 98.45
    got = v("TBILLPRICE", "2008-03-31", "2008-06-01", 0.09)
    assert math.isclose(got, 98.45, rel_tol=1e-9)
    # Excel doc: TBILLYIELD(31-Mar-08, 1-Jun-08, 98.45) = 0.091417
    got = v("TBILLYIELD", "2008-03-31", "2008-06-01", 98.45)
    assert math.isclose(got, 0.091417, rel_tol=1e-4)


def test_tbill_long_maturity():
    # > 182 days uses the semiannual-compounding relation; the result must be
    # positive and a bit above the simple-form short-bill yield shape.
    got = v("TBILLEQ", "2008-01-01", "2008-09-30", 0.08)
    assert isinstance(got, float) and 0.08 < got < 0.10
    # More than a year is out of range.
    assert isinstance(v("TBILLPRICE", "2008-01-01", "2009-06-01", 0.08), CellError)


def test_validation_errors():
    assert isinstance(v("PRICE", "2017-11-15", "2008-02-15", 0.05, 0.06, 100, 2, 0),
                      CellError)
    assert isinstance(v("DISC", "2007-01-25", "2007-06-15", -1, 100, 1), CellError)
    assert isinstance(v("YIELDMAT", "2007-11-01", "2008-11-03", "2007-11-08",
                        0.06, 100, 0), CellError)  # settlement before issue
