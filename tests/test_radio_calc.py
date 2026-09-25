"""Radio-system math (abax.core.science.radio_calc) — pure stdlib.

Most cases are the calculation questions of the FCC Amateur Extra (Element 4)
2024–2028 question pool; the ID is in each comment.
"""

from __future__ import annotations

import math

import pytest

from abax.core.science import radio_calc as R


@pytest.mark.parametrize("power, gain, losses, expected", [
    (150, 7, (2, 2.2), 286),            # E9A02 ERP
    (200, 10, (4, 3.2, 0.8), 317),      # E9A06 ERP
    (200, 7, (2, 2.8, 1.2), 252),       # E9A07 EIRP
])
def test_power_chain_pool(power, gain, losses, expected):
    assert round(R.power_through_chain(power, gain, losses)) == expected


def test_power_chain_rejects_negative_power():
    with pytest.raises(ValueError):
        R.power_through_chain(-1, 0)


def test_link_budget_pool_e4d12_e4d13():
    rx = R.received_level_dbm(40, 10, 0, 136, 3)
    assert rx == -89
    assert R.link_margin_db(rx, -103, 6) == 8          # E4D12: +8 dB
    assert R.received_level_dbm(40, 6, 3, 100) == -51  # E4D13


def test_noise_bandwidth_e4c06():
    assert round(R.noise_bandwidth_change_db(50, 1000)) == 13
    with pytest.raises(ValueError):
        R.noise_bandwidth_change_db(0, 1000)


@pytest.mark.parametrize("rf, rin, expected", [
    (470, 10, 47), (68_000, 1800, 38), (47_000, 3300, 14),   # E7G07, E7G10, E7G11
])
def test_opamp_inverting_gain_pool(rf, rin, expected):
    g = R.opamp_inverting_gain(rf, rin)
    assert g < 0 and round(abs(g)) == expected


def test_opamp_output_e7g09_and_noninverting():
    assert math.isclose(R.opamp_inverting_gain(10_000, 1000) * 0.23, -2.3)
    assert R.opamp_noninverting_gain(9000, 1000) == 10


@pytest.mark.parametrize("dev, fm, expected", [
    (3000, 1000, 3.0), (6000, 2000, 3.0), (5000, 3000, 1.67), (7500, 3500, 2.14),
])  # E8B03, E8B04, E8B05, E8B06
def test_modulation_index_pool(dev, fm, expected):
    assert round(R.modulation_index(dev, fm), 2) == expected


def test_carson_bandwidth():
    assert R.carson_bandwidth(5000, 3000) == 16_000   # 47 CFR 2.202 FM telephony, K=1


def test_cw_and_fsk_bandwidth():
    assert R.cw_bandwidth(13) == pytest.approx(52)          # E8C05
    assert R.cw_bandwidth(25) == pytest.approx(100)         # 47 CFR 2.202(g) example
    assert R.cw_bandwidth(25, 3) == pytest.approx(60)       # non-fading K = 3
    assert R.fsk_bandwidth(4800, 9600) == pytest.approx(15_360)   # E8C07
    assert R.fsk_bandwidth(170, 100) == pytest.approx(304)        # 47 CFR 2.202(g) example


def test_adc():
    assert R.adc_bits(1.0, 0.001) == 10         # E7F06
    assert R.adc_bits(1024, 1) == 10            # exact power of two: not 11
    assert R.adc_bits(1025, 1) == 11
    # a resolution typed as a rounded decimal (0.011 V / 2^20) must not tip
    # floating-point error into an extra bit
    assert R.adc_bits(0.011, 1.04904174804687e-08) == 20
    assert R.adc_bits(1, 2) == 0
    assert R.adc_levels(8) == 256               # E8A09
    assert R.adc_lsb(2.0, 8) == 2.0 / 256
    assert math.isclose(R.adc_ideal_snr_db(16), 98.09, abs_tol=0.01)
    with pytest.raises(ValueError):
        R.adc_levels(8.5)


def test_nyquist_e7f05():
    assert R.nyquist_rate(3000) == 6000


def test_sideband_edges_pool():
    # E1A01: 3 kHz USB at 14.348 MHz spills past 14.350 MHz
    assert R.usb_max_carrier(14.350e6) < 14.348e6
    # E1A03: 2.8 kHz USB data signal, top of 20 m data segment 14.150 MHz
    assert R.usb_max_carrier(14.150e6, 2800) == pytest.approx(14.1472e6)
    # E1A02: lowest LSB carrier is 3 kHz above the edge
    assert R.lsb_min_carrier(3.600e6) - 3.600e6 == pytest.approx(3000)
    # E1A04: 3.601 MHz LSB extends below the 3.600 MHz phone edge
    assert R.lsb_min_carrier(3.600e6) > 3.601e6


def test_line_length_e9f06():
    assert round(R.line_length(14.10e6, 0.5, 1.0), 1) == 10.6
    assert R.electrical_length_deg(R.line_length(7e6, 0.25, 0.66), 7e6, 0.66) == pytest.approx(90)


def test_stub_reactance_pool():
    z0 = 50.0
    assert R.stub_reactance(z0, 45) == pytest.approx(50)            # E9F10 shorted λ/8: inductive
    assert R.stub_reactance(z0, 45, True) == pytest.approx(-50)     # E9F11 open λ/8: capacitive
    assert abs(R.stub_reactance(z0, 180)) < 1e-9                    # E9F04 shorted λ/2: low
    assert abs(R.stub_reactance(z0, 90, True)) < 1e-9               # E9F12 open λ/4: low
    with pytest.raises(ValueError):                                 # E9F09 shorted λ/4: open circuit
        R.stub_reactance(z0, 90)
    with pytest.raises(ValueError):
        R.stub_reactance(z0, 180, True)


def test_antenna_efficiency():
    assert R.antenna_efficiency(36, 4) == 0.9
    with pytest.raises(ValueError):
        R.antenna_efficiency(0, 1)


def test_intermod_and_image():
    lo, hi = R.imd3_products(14.072e6, 14.070e6)
    assert (lo, hi) == (14.068e6, 14.074e6)
    assert R.third_order_intercept_dbm(-10, -70) == 20
    assert R.sfdr_db(20, -130) == 100
    assert R.image_frequency(14.2e6, 9e6) == 32.2e6
    assert R.image_frequency(14.2e6, 455e3, False) == pytest.approx(13.29e6)
    with pytest.raises(ValueError):
        R.image_frequency(1e6, 9e6, False)


@pytest.mark.parametrize("fn, args", [
    ("opamp_inverting_gain", (100, 0)), ("opamp_noninverting_gain", (-1, 10)),
    ("modulation_index", (1000, 0)), ("carson_bandwidth", (-1, 1000)),
    ("cw_bandwidth", (0,)), ("fsk_bandwidth", (170, 0)),
    ("adc_bits", (0, 1)), ("nyquist_rate", (-1,)),
    ("usb_max_carrier", (14.35e6, -1)), ("lsb_min_carrier", (3.6e6, -1)),
    ("line_length", (0, 0.5)), ("electrical_length_deg", (1, 0)),
    ("stub_reactance", (0, 45)), ("image_frequency", (0, 9e6)),
])
def test_domain_guards_raise(fn, args):
    with pytest.raises(ValueError):
        getattr(R, fn)(*args)
