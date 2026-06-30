"""Tests for the HP-12C financial keypad (:mod:`qcell.core.calc.rpn12`).

Sign convention under test (HP cash-flow): money received is positive, money
paid out is negative. For a loan you receive the principal (``PV`` positive) and
pay it back (``PMT`` negative); ``FV`` of 0 means the loan is fully amortized.
"""

from __future__ import annotations

import pytest

from qcell.core.calc import voyager
from qcell.core.calc.rpn12 import BUTTONS, LEGENDS_12C, Voyager12Keypad, grid_pos

# Button numbers by primary legend, for readable presses.
_BY_PRIMARY = {legend[0]: num for num, legend in LEGENDS_12C.items()}


def _press(kp: Voyager12Keypad, *primaries: str) -> None:
    for p in primaries:
        kp.press(_BY_PRIMARY[p])


def _keyin(kp: Voyager12Keypad, text: str) -> None:
    """Type a number (with an optional decimal point) onto the keypad."""
    for ch in text:
        kp.press(_BY_PRIMARY["decimal"] if ch == "." else _BY_PRIMARY[ch])


def test_bond_price_date_based():
    # yield 6.5% (i), coupon 5.75% (PMT); settle 2008-02-15, mature 2017-11-15.
    # Matches Excel PRICE (30/360): clean ~94.6344, accrued ~1.4375.
    kp = Voyager12Keypad()
    _keyin(kp, "6.5"); _press(kp, "i")
    _keyin(kp, "5.75"); _press(kp, "PMT")
    _keyin(kp, "2.152008"); _press(kp, "ENTER")     # settlement (M.DY)
    _keyin(kp, "11.152017")                          # maturity
    _press(kp, "f", "y^x")                           # f BOND PRICE
    assert abs(kp.rpn.x - 94.6344) < 0.01
    assert abs(kp.rpn.stack[1] - 1.4375) < 0.01      # accrued interest in Y


def test_bond_ytm_round_trips():
    kp = Voyager12Keypad()
    _keyin(kp, "94.6344"); _press(kp, "PV")          # price
    _keyin(kp, "5.75"); _press(kp, "PMT")
    _keyin(kp, "2.152008"); _press(kp, "ENTER")
    _keyin(kp, "11.152017")
    _press(kp, "f", "1/x")                            # f BOND YTM
    assert abs(kp.rpn.x - 6.5) < 0.05


def test_date_arithmetic_and_format_toggle():
    # M.DY: 2024-06-15 + 30 days = 2024-07-15 -> 7.152024
    kp = Voyager12Keypad()
    _keyin(kp, "6.152024"); _press(kp, "ENTER")
    _keyin(kp, "30")
    _press(kp, "f", "CHS")                            # f DATE
    assert abs(kp.rpn.x - 7.152024) < 1e-6
    assert kp.message in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    # Switch to D.MY and confirm parsing flips
    _press(kp, "f", "4")                              # f D.MY
    assert kp.date_mode == "DMY"
    _keyin(kp, "15.042024"); _press(kp, "ENTER")      # 15 April 2024
    _keyin(kp, "30")
    _press(kp, "f", "CHS")                            # f DATE -> 15 May 2024
    assert abs(kp.rpn.x - 15.052024) < 1e-6


def test_delta_days_between_dates():
    kp = Voyager12Keypad()
    _keyin(kp, "1.012024"); _press(kp, "ENTER")       # 2024-01-01
    _keyin(kp, "12.312024")                           # 2024-12-31
    _press(kp, "f", "EEX")                            # f DeltaDYS
    assert kp.rpn.x == 365.0                          # actual days (leap year)
    assert kp.rpn.stack[1] == 360.0                   # 30/360 days in Y


# -- grid / re-export ------------------------------------------------------


def test_reuses_voyager_grid():
    assert BUTTONS is voyager.BUTTONS
    assert grid_pos is voyager.grid_pos
    assert grid_pos(11) == (0, 0)
    assert grid_pos(40) == (3, 9)


# -- basic RPN -------------------------------------------------------------


def test_addition():
    kp = Voyager12Keypad()
    _press(kp, "3", "ENTER", "4", "add")
    assert kp.display() == "7"


def test_multiplication():
    kp = Voyager12Keypad()
    _press(kp, "2", "ENTER", "3", "multiply")
    assert kp.display() == "6"


def test_chs_negates_entry():
    kp = Voyager12Keypad()
    _press(kp, "5", "CHS")
    assert kp.display() == "-5"
    _press(kp, "ENTER")
    assert kp.rpn.x == -5.0


def test_chs_negates_x_after_commit():
    kp = Voyager12Keypad()
    _press(kp, "8", "ENTER")
    _press(kp, "CHS")
    assert kp.rpn.x == -8.0


def test_clx_clears():
    kp = Voyager12Keypad()
    _press(kp, "9", "ENTER", "7")
    _press(kp, "CLx")
    assert kp.display() == "0"


def test_decimal_entry():
    kp = Voyager12Keypad()
    _press(kp, "1", "decimal", "5")
    assert kp.display() == "1.5"


# -- label_for / shift -----------------------------------------------------


def test_label_for_primary_by_default():
    kp = Voyager12Keypad()
    assert kp.label_for(13) == "PV"
    assert kp.label_for(11) == "n"


def test_label_for_gold_under_f():
    kp = Voyager12Keypad()
    kp.press(_BY_PRIMARY["f"])
    assert kp.shift == "f"
    assert kp.label_for(13) == "NPV"      # gold on PV
    assert kp.label_for(15) == "IRR"      # gold on FV


def test_label_for_blue_under_g():
    kp = Voyager12Keypad()
    kp.press(_BY_PRIMARY["g"])
    assert kp.shift == "g"
    assert kp.label_for(13) == "CF0"      # blue on PV
    assert kp.label_for(22) == "e^x"      # blue on 1/x


def test_f_then_g_toggle():
    kp = Voyager12Keypad()
    kp.press(_BY_PRIMARY["f"])
    assert kp.shift == "f"
    kp.press(_BY_PRIMARY["f"])            # toggles off
    assert kp.shift == ""


# -- TVM: store then solve -------------------------------------------------


def test_tvm_solve_pmt_classic_loan():
    """n=360, i=0.5%/mo, PV=100000 -> PMT solved.

    PV is positive (cash received); the solved PMT is negative (cash paid out).
    """
    kp = Voyager12Keypad()
    _press(kp, "3", "6", "0", "n")          # store n = 360
    assert kp.n == 360.0
    _press(kp, "decimal", "5", "i")         # store i = 0.5 (percent/period)
    assert kp.i_pct == pytest.approx(0.5)
    _press(kp, "1", "0", "0", "0", "0", "0", "PV")  # store PV = 100000
    assert kp.PV == 100000.0
    _press(kp, "0", "FV")                   # store FV = 0
    # Solve PMT (no number just entered).
    kp.press(_BY_PRIMARY["PMT"])
    assert kp.PMT == pytest.approx(-599.5505251527569, abs=1e-6)
    assert kp.rpn.x == pytest.approx(-599.5505251527569, abs=1e-6)


def test_tvm_solve_fv():
    kp = Voyager12Keypad()
    _press(kp, "3", "6", "0", "n")
    _press(kp, "decimal", "5", "i")
    _press(kp, "1", "0", "0", "0", "0", "0", "PV")
    # Store the solved PMT directly to avoid re-deriving it here.
    kp.PMT = -599.5505251527569
    kp.press(_BY_PRIMARY["FV"])             # solve FV; consistent set -> ~0
    assert kp.FV == pytest.approx(0.0, abs=1e-4)


def test_tvm_solve_i_converges():
    """PV=-1000, FV=1100, n=1, PMT=0 -> i = 10%."""
    kp = Voyager12Keypad()
    _press(kp, "1", "n")
    _press(kp, "1", "0", "0", "0", "CHS", "PV")   # PV = -1000
    assert kp.PV == -1000.0
    _press(kp, "0", "PMT")
    _press(kp, "1", "1", "0", "0", "FV")          # FV = 1100
    assert kp.FV == 1100.0
    kp.press(_BY_PRIMARY["i"])                    # solve i
    assert kp.i_pct == pytest.approx(10.0, abs=1e-4)
    assert kp.rpn.x == pytest.approx(10.0, abs=1e-4)


def test_tvm_store_overwrites():
    kp = Voyager12Keypad()
    _press(kp, "5", "n")
    assert kp.n == 5.0
    _press(kp, "1", "2", "n")
    assert kp.n == 12.0


# -- unimplemented keys ----------------------------------------------------


def test_statistics_and_percent_now_work():
    # Sigma+ accumulates a point and shows n; percent computes y*x/100.
    kp = Voyager12Keypad()
    kp.press(_BY_PRIMARY["5"])
    kp.press(_BY_PRIMARY["ENTER"])
    kp.press(_BY_PRIMARY["6"])
    kp.press(_BY_PRIMARY["Sigma+"])
    assert kp.rpn.x == 1.0                   # n == 1 after the first point
    kp2 = Voyager12Keypad()
    for ch in "200":
        kp2.press(_BY_PRIMARY[ch])
    kp2.press(_BY_PRIMARY["ENTER"])
    for ch in "10":
        kp2.press(_BY_PRIMARY[ch])
    kp2.press(_BY_PRIMARY["%"])
    assert abs(kp2.rpn.x - 20.0) < 1e-9       # 200 ENTER 10 % == 20


def test_unimplemented_does_not_raise_under_shift():
    kp = Voyager12Keypad()
    kp.press(_BY_PRIMARY["f"])
    kp.press(11)                             # AMORT (gold) — still console-only
    assert kp.message
    assert "not implemented" in kp.message


def test_cashflow_npv_and_irr():
    # CF0=-1000, CFj=500 (x3); i=10 -> NPV>0 ; IRR ~ 23.4%
    kp = Voyager12Keypad()

    def entry(val):
        for ch in str(val):
            kp.press(_BY_PRIMARY[ch] if ch != "-" else _BY_PRIMARY["CHS"])

    def gold(primary):
        kp.press(_BY_PRIMARY["f"])
        kp.press(_BY_PRIMARY[primary])

    def blue(primary):
        kp.press(_BY_PRIMARY["g"])
        kp.press(_BY_PRIMARY[primary])

    entry(1000); kp.press(_BY_PRIMARY["CHS"]); blue("PV")     # CF0 = -1000
    entry(500); blue("PMT")                                   # CFj = 500
    entry(3); blue("FV")                                      # Nj  = 3
    entry(10); kp.press(_BY_PRIMARY["i"])                     # i = 10%
    gold("PV")                                                # NPV
    assert kp.rpn.x > 0
    gold("FV")                                                # IRR
    assert 20.0 < kp.rpn.x < 26.0


def test_depreciation_straight_line():
    # cost 10000 (PV), salvage 1000 (FV), life 5 (n); year 1 SL = 1800
    kp = Voyager12Keypad()
    for ch in "10000":
        kp.press(_BY_PRIMARY[ch])
    kp.press(_BY_PRIMARY["PV"])
    for ch in "1000":
        kp.press(_BY_PRIMARY[ch])
    kp.press(_BY_PRIMARY["FV"])
    kp.press(_BY_PRIMARY["5"])
    kp.press(_BY_PRIMARY["n"])
    kp.press(_BY_PRIMARY["1"])
    kp.press(_BY_PRIMARY["f"])
    kp.press(_BY_PRIMARY["%T"])               # f + %T = DEPR SL
    assert abs(kp.rpn.x - 1800.0) < 1e-6
