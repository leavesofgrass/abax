"""Tests for HP-12C financial / statistics / calendar math (abax.core.science.financial)."""

from __future__ import annotations

import math

import pytest

from abax.core.science.financial import (
    FinanceError,
    Stats,
    add_months,
    bond_price,
    bond_price_dated,
    bond_ytm,
    bond_ytm_dated,
    coupon_schedule,
    date_plus_days,
    days_between,
    depreciation_db,
    depreciation_sl,
    depreciation_soyd,
    factorial,
    irr,
    npv,
    percent,
    percent_change,
    percent_total,
)

# --- cash flows ----------------------------------------------------------


def test_npv_positive_and_known_value():
    flows = [-1000.0, 500.0, 500.0, 500.0]
    value = npv(10.0, flows)
    assert value > 0.0
    expected = -1000.0 + 500.0 / 1.1 + 500.0 / 1.1 ** 2 + 500.0 / 1.1 ** 3
    assert value == pytest.approx(expected)


def test_npv_zero_rate_is_plain_sum():
    assert npv(0.0, [-100.0, 40.0, 40.0, 40.0]) == pytest.approx(20.0)


def test_npv_empty_raises():
    with pytest.raises(FinanceError):
        npv(10.0, [])


def test_npv_rate_minus_100_raises():
    with pytest.raises(FinanceError):
        npv(-100.0, [1.0, 2.0])


def test_irr_known_value():
    rate = irr([-1000.0, 600.0, 600.0])
    assert rate == pytest.approx(13.07, abs=0.01)
    # The recovered rate should zero out the NPV.
    assert npv(rate, [-1000.0, 600.0, 600.0]) == pytest.approx(0.0, abs=1e-6)


def test_irr_no_sign_change_raises():
    with pytest.raises(FinanceError):
        irr([100.0, 200.0, 300.0])


def test_irr_empty_raises():
    with pytest.raises(FinanceError):
        irr([])


# --- bonds ---------------------------------------------------------------


def test_bond_price_at_par_when_yield_equals_coupon():
    # Coupon == yield => price ~ 100 (par).
    assert bond_price(5.0, 5.0, 10.0) == pytest.approx(100.0, abs=1e-6)


def test_bond_price_ytm_round_trip():
    coupon, years, freq = 6.0, 8.0, 2
    price = bond_price(7.25, coupon, years, freq)
    ytm = bond_ytm(price, coupon, years, freq)
    assert ytm == pytest.approx(7.25, abs=1e-4)
    # ...and back to the same price.
    assert bond_price(ytm, coupon, years, freq) == pytest.approx(price, abs=1e-6)


def test_bond_ytm_bad_price_raises():
    with pytest.raises(FinanceError):
        bond_ytm(0.0, 5.0, 10.0)


# --- date-based (SIA) bonds ----------------------------------------------


def test_add_months_clamps_to_leap_february():
    assert add_months((2020, 1, 31), 1) == (2020, 2, 29)


def test_add_months_clamps_to_non_leap_february():
    assert add_months((2021, 1, 31), 1) == (2021, 2, 28)


def test_add_months_negative():
    assert add_months((2020, 3, 15), -2) == (2020, 1, 15)


def test_add_months_crosses_year():
    assert add_months((2020, 12, 15), 1) == (2021, 1, 15)


def test_coupon_schedule_semiannual():
    pc, nc, n = coupon_schedule((2008, 2, 15), (2017, 11, 15), 2)
    assert pc == (2007, 11, 15)
    assert nc == (2008, 5, 15)
    assert n == 20


def test_bond_price_dated_anchor_matches_excel_price():
    clean, accrued = bond_price_dated(
        6.5, 5.75, (2008, 2, 15), (2017, 11, 15), basis="30/360"
    )
    assert clean == pytest.approx(94.6343, abs=1e-2)
    assert accrued == pytest.approx(5.75 / 2 * (90 / 180), abs=1e-9)


def test_bond_ytm_dated_round_trip():
    clean, _ = bond_price_dated(
        6.5, 5.75, (2008, 2, 15), (2017, 11, 15), basis="30/360"
    )
    ytm = bond_ytm_dated(clean, 5.75, (2008, 2, 15), (2017, 11, 15), basis="30/360")
    assert ytm == pytest.approx(6.5, abs=1e-4)


def test_bond_price_dated_par_on_coupon_date():
    clean, accrued = bond_price_dated(5.0, 5.0, (2010, 1, 1), (2020, 1, 1))
    assert clean == pytest.approx(100.0, abs=1e-6)
    assert accrued == pytest.approx(0.0, abs=1e-9)


def test_bond_price_dated_actual_basis_near_30_360():
    clean_360, _ = bond_price_dated(
        6.5, 5.75, (2008, 2, 15), (2017, 11, 15), basis="30/360"
    )
    clean_act, _ = bond_price_dated(
        6.5, 5.75, (2008, 2, 15), (2017, 11, 15), basis="actual"
    )
    assert math.isfinite(clean_act)
    assert clean_act == pytest.approx(clean_360, abs=1.0)


def test_bond_price_dated_bad_basis_raises():
    with pytest.raises(FinanceError):
        bond_price_dated(6.5, 5.75, (2008, 2, 15), (2017, 11, 15), basis="bogus")


def test_bond_price_dated_bad_freq_raises():
    with pytest.raises(FinanceError):
        bond_price_dated(6.5, 5.75, (2008, 2, 15), (2017, 11, 15), freq=3)


def test_bond_price_dated_settlement_not_before_maturity_raises():
    with pytest.raises(FinanceError):
        bond_price_dated(6.5, 5.75, (2017, 11, 15), (2017, 11, 15))


# --- depreciation --------------------------------------------------------


def test_depreciation_sl():
    assert depreciation_sl(10000.0, 1000.0, 5, 1) == pytest.approx(1800.0)
    # Every year is identical for straight line.
    assert depreciation_sl(10000.0, 1000.0, 5, 5) == pytest.approx(1800.0)


def test_depreciation_soyd_year_one():
    assert depreciation_soyd(10000.0, 1000.0, 5, 1) == pytest.approx(3000.0)
    # SOYD total over all years equals the depreciable base.
    total = sum(depreciation_soyd(10000.0, 1000.0, 5, y) for y in range(1, 6))
    assert total == pytest.approx(9000.0)


def test_depreciation_db_year_one():
    assert depreciation_db(10000.0, 1000.0, 5, 1, factor=2.0) == pytest.approx(4000.0)


def test_depreciation_db_never_below_salvage():
    total = sum(depreciation_db(10000.0, 1000.0, 5, y) for y in range(1, 6))
    assert total <= 9000.0 + 1e-9


def test_depreciation_bad_life_raises():
    with pytest.raises(FinanceError):
        depreciation_sl(10000.0, 1000.0, 0, 1)


def test_depreciation_bad_year_raises():
    with pytest.raises(FinanceError):
        depreciation_soyd(10000.0, 1000.0, 5, 6)


# --- percents ------------------------------------------------------------


def test_percent():
    assert percent(200.0, 10.0) == pytest.approx(20.0)


def test_percent_change():
    assert percent_change(100.0, 150.0) == pytest.approx(50.0)
    assert percent_change(100.0, 50.0) == pytest.approx(-50.0)


def test_percent_change_zero_base_raises():
    with pytest.raises(FinanceError):
        percent_change(0.0, 50.0)


def test_percent_total():
    assert percent_total(200.0, 50.0) == pytest.approx(25.0)


def test_percent_total_zero_base_raises():
    with pytest.raises(FinanceError):
        percent_total(0.0, 50.0)


def test_factorial():
    assert factorial(5) == pytest.approx(120.0)
    assert factorial(0) == pytest.approx(1.0)


def test_factorial_negative_raises():
    with pytest.raises(FinanceError):
        factorial(-1)


def test_factorial_non_integer_raises():
    with pytest.raises(FinanceError):
        factorial(2.5)


# --- statistics ----------------------------------------------------------


def test_stats_mean_stdev_regression_correlation():
    s = Stats()
    points = [(1.0, 2.0), (2.0, 4.0), (3.0, 6.0), (4.0, 8.0)]
    for x, y in points:
        s.add(x, y)
    assert s.n == 4

    mx, my = s.mean()
    assert mx == pytest.approx(2.5)
    assert my == pytest.approx(5.0)

    sx, sy = s.stdev()
    # Sample std dev of 1,2,3,4 is sqrt(5/3).
    assert sx == pytest.approx(math.sqrt(5.0 / 3.0))
    assert sy == pytest.approx(math.sqrt(20.0 / 3.0))

    # Perfect line y = 2x: estimate at x=5 is 10, r == 1.
    assert s.linear_estimate(5.0) == pytest.approx(10.0)
    assert s.correlation() == pytest.approx(1.0)


def test_stats_imperfect_correlation():
    s = Stats()
    for x, y in [(1.0, 2.0), (2.0, 1.0), (3.0, 4.0), (4.0, 3.0), (5.0, 6.0)]:
        s.add(x, y)
    r = s.correlation()
    assert 0.0 < r < 1.0
    assert r == pytest.approx(0.82199, abs=1e-4)


def test_stats_remove():
    s = Stats()
    s.add(10.0, 20.0)
    s.add(30.0, 40.0)
    assert s.remove(30.0, 40.0) == 1
    assert s.n == 1
    assert s.mean() == pytest.approx((10.0, 20.0))


def test_stats_remove_empty_raises():
    s = Stats()
    with pytest.raises(FinanceError):
        s.remove(1.0)


def test_stats_mean_empty_raises():
    with pytest.raises(FinanceError):
        Stats().mean()


def test_stats_stdev_one_point_raises():
    s = Stats()
    s.add(5.0)
    with pytest.raises(FinanceError):
        s.stdev()


# --- calendar ------------------------------------------------------------


def test_days_between_actual():
    assert days_between((2026, 1, 1), (2026, 12, 31)) == 364


def test_days_between_leap_year_actual():
    assert days_between((2024, 1, 1), (2025, 1, 1)) == 366


def test_days_between_signed():
    assert days_between((2026, 12, 31), (2026, 1, 1)) == -364


def test_days_between_30_360():
    assert days_between((2026, 1, 1), (2027, 1, 1), actual=False) == 360
    assert days_between((2026, 1, 1), (2026, 2, 1), actual=False) == 30


def test_days_between_invalid_date_raises():
    with pytest.raises(FinanceError):
        days_between((2026, 13, 1), (2026, 1, 1))


def test_date_plus_days():
    assert date_plus_days((2026, 1, 1), 364) == (2026, 12, 31)
    assert date_plus_days((2026, 12, 31), 1) == (2027, 1, 1)
    assert date_plus_days((2026, 1, 1), -1) == (2025, 12, 31)


def test_date_plus_days_invalid_raises():
    with pytest.raises(FinanceError):
        date_plus_days((2026, 2, 30), 1)
