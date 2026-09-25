"""Circuit fundamentals (abax.core.science.circuits) — pure stdlib."""

from __future__ import annotations

import math

import pytest

from abax.core.science import circuits as C


def test_ohms_law_triangle():
    assert C.ohm_voltage(2.0, 50.0) == 100.0
    assert C.ohm_current(100.0, 50.0) == 2.0
    assert C.ohm_resistance(100.0, 2.0) == 50.0
    with pytest.raises(ValueError):
        C.ohm_current(1.0, 0.0)
    with pytest.raises(ValueError):
        C.ohm_resistance(1.0, 0.0)


def test_power_three_ways_agree():
    v, i, r = 100.0, 2.0, 50.0
    assert C.power_vi(v, i) == C.power_ir(i, r) == C.power_vr(v, r) == 200.0
    with pytest.raises(ValueError):
        C.power_vr(1.0, 0.0)


@pytest.mark.parametrize("given", [
    {"voltage_v": 100.0, "current_a": 2.0},
    {"voltage_v": 100.0, "resistance_ohm": 50.0},
    {"voltage_v": 100.0, "power_w": 200.0},
    {"current_a": 2.0, "resistance_ohm": 50.0},
    {"current_a": 2.0, "power_w": 200.0},
    {"resistance_ohm": 50.0, "power_w": 200.0},
])
def test_ohms_law_wheel_every_pair(given):
    out = C.solve_ohms_law(**given)
    for key, want in (("voltage", 100.0), ("current", 2.0),
                      ("resistance", 50.0), ("power", 200.0)):
        assert math.isclose(out[key], want), key


@pytest.mark.parametrize("given", [
    {"voltage_v": 1.0},                                              # only one
    {"voltage_v": 1.0, "current_a": 1.0, "power_w": 1.0},            # three
    {"voltage_v": 0.0, "power_w": 5.0},                              # undetermined
    {"resistance_ohm": -1.0, "power_w": 5.0},                        # negative R
])
def test_ohms_law_wheel_rejects(given):
    with pytest.raises(ValueError):
        C.solve_ohms_law(**given)


def test_series_and_parallel():
    assert C.series_sum([100, 220, 330]) == 650
    assert C.reciprocal_sum([100, 100]) == 50
    assert math.isclose(C.reciprocal_sum([100, 200, 300]), 54.5454545, rel_tol=1e-6)
    for bad in ([], [100, 0], [100, -5]):
        with pytest.raises(ValueError):
            C.reciprocal_sum(bad)


def test_time_constants_pool_e5b04_and_e5b01():
    # E5B04: two 220 µF and two 1 MΩ, all in parallel -> 220 s
    r = C.reciprocal_sum([1e6, 1e6])
    c = C.series_sum([220e-6, 220e-6])
    assert math.isclose(C.tau_rc(r, c), 220.0)
    # E5B01: one time constant -> 63.2 % charged / 36.8 % remaining
    assert math.isclose(C.charge_fraction(1.0, 1.0), 0.6321, abs_tol=1e-4)
    assert math.isclose(C.decay_fraction(1.0, 1.0), 0.3679, abs_tol=1e-4)
    assert math.isclose(C.tau_rl(10.0, 1e-3), 1e-4)
    # inverse: time to reach 63.2 % is one tau; 99.3 % is about 5 tau
    assert math.isclose(C.time_to_fraction(1 - math.exp(-1), 2.0), 2.0)
    assert math.isclose(C.time_to_fraction(C.charge_fraction(5, 1), 1), 5.0)
    with pytest.raises(ValueError):
        C.time_to_fraction(1.0, 1.0)


@pytest.mark.parametrize("r, x, expected", [
    (1000.0, 250.0 - 500.0, -14.04),   # E5B07: 14.0°, voltage lagging
    (100.0, 100.0 - 300.0, -63.43),    # E5B08: 63°, voltage lagging
    (100.0, 75.0 - 25.0, 26.57),       # E5B11: 27°, voltage leading
])
def test_phase_angle_pool(r, x, expected):
    assert math.isclose(C.phase_angle_deg(complex(r, x)), expected, abs_tol=0.01)


def test_series_rlc_impedance_pool_e5c10_to_e5c12():
    z = C.series_rlc_impedance(14e6, 400, 0, 38e-12)       # E5C10 -> 400 - j300
    assert math.isclose(z.real, 400) and math.isclose(z.imag, -299.16, abs_tol=0.01)
    z = C.series_rlc_impedance(3.505e6, 300, 18e-6, 0)      # E5C11 -> 300 + j400
    assert math.isclose(z.imag, 396.40, abs_tol=0.01)
    z = C.series_rlc_impedance(21.2e6, 300, 0, 19e-12)      # E5C12 -> 300 - j400
    assert math.isclose(z.imag, -395.13, abs_tol=0.01)


def test_series_rlc_is_resistive_at_resonance():
    l, c = 50e-6, 40e-12
    f0 = 1 / (2 * math.pi * math.sqrt(l * c))
    z = C.series_rlc_impedance(f0, 10, l, c)
    assert math.isclose(z.real, 10) and abs(z.imag) < 1e-6


def test_parallel_rlc_impedance():
    # R alone
    assert C.parallel_rlc_impedance(1e6, 50, 0, 0) == 50
    # L || C at resonance is an open circuit -> only R remains
    l, c = 1e-6, 1e-9
    f0 = 1 / (2 * math.pi * math.sqrt(l * c))
    z = C.parallel_rlc_impedance(f0, 1000, l, c)
    assert math.isclose(z.real, 1000, rel_tol=1e-9) and abs(z.imag) < 1e-6
    with pytest.raises(ValueError):
        C.parallel_rlc_impedance(1e6, 0, 0, 0)


def test_admittance_polar_rule_e5b03():
    # |Y| = 1/|Z| and the angle changes sign
    z = C.polar_to_rect(50.0, 30.0)
    y = C.admittance(z)
    assert math.isclose(abs(y), 1 / 50.0)
    assert math.isclose(math.degrees(math.atan2(y.imag, y.real)), -30.0)
    with pytest.raises(ValueError):
        C.admittance(0)


def test_power_factor_and_power_triangle():
    assert math.isclose(C.power_factor(complex(3, 4)), 0.6)
    v, i, theta = 120.0, 5.0, 36.87
    p, q, s = C.real_power(v, i, theta), C.reactive_power(v, i, theta), C.apparent_power(v, i)
    assert math.isclose(p * p + q * q, s * s, rel_tol=1e-12)
    assert math.isclose(p / s, math.cos(math.radians(theta)))


def test_q_series_and_parallel():
    assert C.q_series(10, 500) == 50
    assert C.q_parallel(10_000, 200) == 50         # E5A09: Q = R/X
    with pytest.raises(ValueError):
        C.q_parallel(1000, 0)


@pytest.mark.parametrize("topology", ["series", "parallel"])
def test_rlc_resonance_half_power_points(topology):
    r = 5.0 if topology == "series" else 20_000.0
    info = C.rlc_resonance(r, 10e-6, 100e-12, topology)
    assert math.isclose(info["f0"], 1 / (2 * math.pi * math.sqrt(10e-6 * 100e-12)))
    assert math.isclose(info["f_high"] - info["f_low"], info["bandwidth"], rel_tol=1e-9)
    assert math.isclose(info["bandwidth"], info["f0"] / info["q"])
    # The response is 1 at f0 and 1/sqrt(2) at both half-power frequencies.
    assert math.isclose(C.rlc_relative_response(info["f0"], r, 10e-6, 100e-12, topology), 1.0)
    for f in (info["f_low"], info["f_high"]):
        assert math.isclose(C.rlc_relative_response(f, r, 10e-6, 100e-12, topology),
                            1 / math.sqrt(2), rel_tol=1e-9)


def test_rlc_bad_topology():
    with pytest.raises(ValueError):
        C.rlc_resonance(1, 1e-6, 1e-9, "bridge")


@pytest.mark.parametrize("fn, args", [
    ("tau_rc", (0, 1e-6)), ("tau_rl", (10, 0)), ("charge_fraction", (1, 0)),
    ("decay_fraction", (-1, 1)), ("time_to_fraction", (0.5, 0)),
    ("series_rlc_impedance", (0, 1, 1, 1)), ("series_rlc_impedance", (1e6, -1, 0, 0)),
    ("parallel_rlc_impedance", (0, 1, 1, 1)), ("parallel_rlc_impedance", (1e6, 1, -1, 0)),
    ("phase_angle_deg", (0,)), ("power_factor", (0,)),
    ("q_series", (0, 100)), ("q_parallel", (0, 100)),
    ("rlc_resonance", (0, 1e-6, 1e-9)),
])
def test_domain_guards_raise(fn, args):
    with pytest.raises(ValueError):
        getattr(C, fn)(*args)


def test_relative_response_bad_topology():
    with pytest.raises(ValueError):
        C.rlc_relative_response(1e6, 1, 1e-6, 1e-9, "bridge")
