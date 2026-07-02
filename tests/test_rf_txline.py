"""Transmission-line toolkit — validated against textbook values.

Covers the lossless-line input-impedance transform (quarter-/half-wave special
cases), the simple matched line-loss model, and the short-circuit shunt
single-stub match (Pozar's worked example). Exercises both the pure
``core.science.rf_math`` functions and the ZINLINER/ZINLINEX/LINELOSS formula
layer.
"""

from __future__ import annotations

import math

import pytest

from abax.core.science import rf_math as M
from abax.core.workbook import Workbook


def _val(formula):
    wb = Workbook()
    s = wb.sheets[0]
    s.set("A1", formula)
    return s.get("A1")


# --- pure functions: zin_line ---------------------------------------------

def test_quarter_wave_transforms_real_load():
    # lambda/4 (90 deg) maps a real ZL to Z0**2 / ZL.  Z0=50, ZL=100 -> 25 ohm.
    z = M.zin_line(complex(100, 0), 50.0, 90.0)
    assert z.real == pytest.approx(25.0, abs=1e-9)
    assert z.imag == pytest.approx(0.0, abs=1e-9)


def test_quarter_wave_general():
    # Z0**2 / ZL for a complex load.
    z0, zl = 75.0, complex(40, -30)
    z = M.zin_line(zl, z0, 90.0)
    expected = z0 ** 2 / zl
    assert z.real == pytest.approx(expected.real, abs=1e-9)
    assert z.imag == pytest.approx(expected.imag, abs=1e-9)


def test_half_wave_repeats_load():
    # lambda/2 (180 deg) repeats the load impedance (Zin == ZL).
    zl = complex(30, 40)
    z = M.zin_line(zl, 50.0, 180.0)
    assert z.real == pytest.approx(30.0, abs=1e-9)
    assert z.imag == pytest.approx(40.0, abs=1e-9)


def test_zero_length_line_is_load():
    zl = complex(73, 42.5)
    z = M.zin_line(zl, 50.0, 0.0)
    assert z.real == pytest.approx(73.0)
    assert z.imag == pytest.approx(42.5)


def test_zin_line_requires_positive_z0():
    with pytest.raises(ValueError):
        M.zin_line(complex(50, 0), 0.0, 45.0)


# --- pure functions: line_loss_db -----------------------------------------

def test_line_loss_hand_computation():
    # 4 dB/100 m rated cable, 50 m -> exactly 2 dB.
    assert M.line_loss_db(50.0, 100e6, 4.0) == pytest.approx(2.0)
    # 100 m -> the rated figure itself.
    assert M.line_loss_db(100.0, 100e6, 4.0) == pytest.approx(4.0)
    # zero length -> zero loss.
    assert M.line_loss_db(0.0, 100e6, 4.0) == pytest.approx(0.0)


def test_line_loss_monotonic_in_length():
    prev = -1.0
    for length in (0, 25, 50, 100, 200, 500):
        loss = M.line_loss_db(float(length), 100e6, 3.5)
        assert loss > prev
        prev = loss


def test_line_loss_rejects_bad_args():
    with pytest.raises(ValueError):
        M.line_loss_db(-1.0, 100e6, 4.0)
    with pytest.raises(ValueError):
        M.line_loss_db(50.0, 0.0, 4.0)
    with pytest.raises(ValueError):
        M.line_loss_db(50.0, 100e6, -1.0)


# --- pure functions: stub_match_short -------------------------------------

def test_stub_match_pozar_example():
    # Pozar, *Microwave Engineering*: ZL = 15 + j10 ohm on a 50-ohm line.
    # Shorted-stub solution d ~ 0.387 lambda, l ~ 0.103 lambda.
    d, l = M.stub_match_short(complex(15, 10), 50.0)
    assert d == pytest.approx(0.387, abs=2e-3)
    assert l == pytest.approx(0.103, abs=2e-3)


def test_stub_match_actually_matches():
    # The (d, l) pair must drive the total normalized input admittance to 1+0j.
    z0 = 50.0
    zl = complex(15, 10)
    d, l = M.stub_match_short(zl, z0)
    tb = math.tan(2 * math.pi * d)
    zin = z0 * (zl + 1j * z0 * tb) / (z0 + 1j * zl * tb)
    y_in = z0 / zin                              # normalized line admittance
    y_stub = z0 / (1j * z0 * math.tan(2 * math.pi * l))  # shorted-stub admittance
    ytot = y_in + y_stub
    assert ytot.real == pytest.approx(1.0, abs=1e-6)
    assert ytot.imag == pytest.approx(0.0, abs=1e-6)


# --- formula layer: ZINLINER / ZINLINEX / LINELOSS ------------------------

def test_formula_quarter_wave():
    # =ZINLINER(100, 0, 50, 90) -> 25 ; imag part ~ 0.
    assert _val("=ZINLINER(100,0,50,90)") == pytest.approx(25.0, abs=1e-9)
    assert _val("=ZINLINEX(100,0,50,90)") == pytest.approx(0.0, abs=1e-9)


def test_formula_half_wave_repeats():
    assert _val("=ZINLINER(30,40,50,180)") == pytest.approx(30.0, abs=1e-9)
    assert _val("=ZINLINEX(30,40,50,180)") == pytest.approx(40.0, abs=1e-9)


def test_formula_lineloss():
    assert _val("=LINELOSS(50,1e8,4)") == pytest.approx(2.0)
    assert _val("=LINELOSS(100,1e8,4)") == pytest.approx(4.0)
