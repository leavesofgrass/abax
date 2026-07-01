"""Tests for qcell.core.science.rf_math (pure stdlib, pytest)."""

from __future__ import annotations

import math

import pytest

from qcell.core.science import rf_math as rm

# --- reactance <-> component ----------------------------------------------

def test_capacitance_from_reactance():
    # Xc = 1/(2*pi*f*C); pick C=1nF at 1MHz -> Xc, then invert.
    f, c = 1e6, 1e-9
    xc = 1.0 / (2.0 * math.pi * f * c)
    assert math.isclose(rm.capacitance_from_reactance(xc, f), c, rel_tol=1e-9)


def test_capacitance_from_reactance_domain():
    with pytest.raises(ValueError):
        rm.capacitance_from_reactance(0.0, 1e6)
    with pytest.raises(ValueError):
        rm.capacitance_from_reactance(50.0, 0.0)


def test_inductance_from_reactance():
    f, l = 1e6, 1e-6
    xl = 2.0 * math.pi * f * l
    assert math.isclose(rm.inductance_from_reactance(xl, f), l, rel_tol=1e-9)


def test_inductance_from_reactance_domain():
    with pytest.raises(ValueError):
        rm.inductance_from_reactance(50.0, 0.0)


# --- resonance ------------------------------------------------------------

def test_resonant_capacitance():
    # 1 uH resonant at ~7.117 MHz -> ~500 pF.
    f, l = 7.117e6, 1e-6
    c = rm.resonant_capacitance(f, l)
    assert math.isclose(c, 1.0 / ((2 * math.pi * f) ** 2 * l), rel_tol=1e-9)
    # Round-trip: the reactance of that C at f equals the reactance of L at f.
    xc = 1.0 / (2 * math.pi * f * c)
    xl = 2 * math.pi * f * l
    assert math.isclose(xc, xl, rel_tol=1e-9)


def test_resonant_inductance():
    f, c = 7.117e6, 500e-12
    l = rm.resonant_inductance(f, c)
    assert math.isclose(l, 1.0 / ((2 * math.pi * f) ** 2 * c), rel_tol=1e-9)
    # Consistency: resonant_capacitance is the inverse of resonant_inductance.
    assert math.isclose(rm.resonant_capacitance(f, l), c, rel_tol=1e-9)


def test_resonant_domain():
    with pytest.raises(ValueError):
        rm.resonant_capacitance(0.0, 1e-6)
    with pytest.raises(ValueError):
        rm.resonant_inductance(1e6, 0.0)


# --- Q / bandwidth --------------------------------------------------------

def test_q_from_bandwidth():
    assert math.isclose(rm.q_from_bandwidth(14e6, 14e3), 1000.0, rel_tol=1e-9)


def test_bandwidth_from_q():
    assert math.isclose(rm.bandwidth_from_q(14e6, 1000.0), 14e3, rel_tol=1e-9)
    # Round-trip
    assert math.isclose(rm.bandwidth_from_q(14e6, rm.q_from_bandwidth(14e6, 14e3)),
                        14e3, rel_tol=1e-9)


def test_q_bw_domain():
    with pytest.raises(ValueError):
        rm.q_from_bandwidth(14e6, 0.0)
    with pytest.raises(ValueError):
        rm.bandwidth_from_q(14e6, 0.0)


# --- air-core solenoid ----------------------------------------------------

def test_air_core_inductance():
    # Wheeler check: d=1 in, len=1 in, N=10 -> L = (1*100)/(18+40) uH.
    d_m = 1.0 * 0.0254
    len_m = 1.0 * 0.0254
    expected_uh = (1.0 * 100.0) / (18.0 + 40.0)
    assert math.isclose(rm.air_core_inductance(d_m, len_m, 10.0),
                        expected_uh * 1e-6, rel_tol=1e-9)


def test_air_core_turns_roundtrip():
    d_m, len_m, n = 0.0254, 0.0254, 10.0
    l = rm.air_core_inductance(d_m, len_m, n)
    assert math.isclose(rm.air_core_turns(l, d_m, len_m), n, rel_tol=1e-9)


def test_air_core_domain():
    with pytest.raises(ValueError):
        rm.air_core_inductance(0.0, 0.0254, 10.0)
    with pytest.raises(ValueError):
        rm.air_core_turns(1e-6, 0.0254, 0.0)


# --- toroid ---------------------------------------------------------------

def test_toroid_inductance():
    # AL=49 nH/turn^2 (T50-6-ish), N=20 -> 49*400 = 19600 nH.
    assert math.isclose(rm.toroid_inductance(49.0, 20.0), 19600e-9, rel_tol=1e-9)


def test_toroid_turns_roundtrip():
    al, n = 49.0, 20.0
    l = rm.toroid_inductance(al, n)
    assert math.isclose(rm.toroid_turns(l, al), n, rel_tol=1e-9)


def test_toroid_domain():
    with pytest.raises(ValueError):
        rm.toroid_inductance(0.0, 20.0)
    with pytest.raises(ValueError):
        rm.toroid_turns(1e-6, 0.0)


# --- matching / SWR -------------------------------------------------------

def test_quarter_wave_z0():
    assert math.isclose(rm.quarter_wave_z0(50.0, 200.0), 100.0, rel_tol=1e-9)
    assert math.isclose(rm.quarter_wave_z0(50.0, 50.0), 50.0, rel_tol=1e-9)


def test_quarter_wave_z0_domain():
    with pytest.raises(ValueError):
        rm.quarter_wave_z0(0.0, 200.0)


def test_swr_from_power():
    assert math.isclose(rm.swr_from_power(100.0, 0.0), 1.0, rel_tol=1e-9)
    # gamma = 1/3 -> Pr = Pf/9 = 11.111 W -> SWR = 2.
    assert math.isclose(rm.swr_from_power(100.0, 100.0 / 9.0), 2.0, rel_tol=1e-9)


def test_swr_from_power_domain():
    with pytest.raises(ValueError):
        rm.swr_from_power(100.0, 100.0)  # equal -> infinite
    with pytest.raises(ValueError):
        rm.swr_from_power(0.0, 0.0)
    with pytest.raises(ValueError):
        rm.swr_from_power(100.0, -1.0)


# --- loop antenna ---------------------------------------------------------

def test_loop_length():
    # 306.3 / f_MHz metres; at 14.0 MHz.
    assert math.isclose(rm.loop_length(14.0e6), 306.3 / 14.0, rel_tol=1e-9)


def test_loop_length_domain():
    with pytest.raises(ValueError):
        rm.loop_length(0.0)


# --- parabolic dish -------------------------------------------------------

def test_parabolic_gain_dbi():
    g = rm.parabolic_gain_dbi(3.0, 10e9)
    assert 47.0 < g < 48.0
    assert math.isclose(g, 47.3526, rel_tol=1e-3)


def test_parabolic_gain_dbi_domain():
    with pytest.raises(ValueError):
        rm.parabolic_gain_dbi(3.0, 10e9, efficiency=0.0)
    with pytest.raises(ValueError):
        rm.parabolic_gain_dbi(3.0, 10e9, efficiency=1.5)
    with pytest.raises(ValueError):
        rm.parabolic_gain_dbi(0.0, 10e9)


def test_parabolic_beamwidth_deg():
    lam = 299_792_458.0 / 10e9
    assert math.isclose(rm.parabolic_beamwidth_deg(3.0, 10e9),
                        70.0 * lam / 3.0, rel_tol=1e-9)


def test_parabolic_beamwidth_domain():
    with pytest.raises(ValueError):
        rm.parabolic_beamwidth_deg(3.0, 0.0)


# --- Doppler --------------------------------------------------------------

def test_doppler_shift_hz():
    # 145.8 MHz, LEO closing at 7660 m/s -> ~3725 Hz.
    df = rm.doppler_shift_hz(145.8e6, 7660.0)
    assert math.isclose(df, 3725.0, rel_tol=1e-3)
    # Sign flips with opening velocity.
    assert math.isclose(rm.doppler_shift_hz(145.8e6, -7660.0), -df, rel_tol=1e-12)


def test_doppler_domain():
    with pytest.raises(ValueError):
        rm.doppler_shift_hz(0.0, 7660.0)
