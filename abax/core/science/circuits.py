"""Circuit fundamentals for radio work — pure stdlib.

Ohm's law and power, series/parallel combination, RC/RL time constants,
complex impedance (phase angle, admittance, power factor), true/reactive/
apparent power, circuit Q, and the RLC resonance response used by the
Circuit calculator's graphs.

SI base units throughout: volts, amperes, ohms, watts, henries, farads,
seconds, hertz. Impedances are Python :class:`complex` values ``R + jX`` —
positive ``X`` is inductive, negative ``X`` capacitive. Domain errors raise
:class:`ValueError` so the formula layer can map them to ``#NUM!``.

References for the relationships used here are standard circuit theory; the
ones that the FCC Amateur Extra (Element 4, 2024–2028) question pool tests are
noted with their question IDs so the worked examples can be checked against
the pool's answer key.
"""

from __future__ import annotations

import cmath
import math
from typing import Iterable

_TWO_PI = 2.0 * math.pi


# --- Ohm's law & power ------------------------------------------------------

def ohm_voltage(current_a: float, resistance_ohm: float) -> float:
    """E = I·R (volts)."""
    return current_a * resistance_ohm


def ohm_current(voltage_v: float, resistance_ohm: float) -> float:
    """I = E / R (amperes). Requires R ≠ 0."""
    if resistance_ohm == 0:
        raise ValueError("resistance must be nonzero")
    return voltage_v / resistance_ohm


def ohm_resistance(voltage_v: float, current_a: float) -> float:
    """R = E / I (ohms). Requires I ≠ 0."""
    if current_a == 0:
        raise ValueError("current must be nonzero")
    return voltage_v / current_a


def power_vi(voltage_v: float, current_a: float) -> float:
    """P = E·I (watts)."""
    return voltage_v * current_a


def power_ir(current_a: float, resistance_ohm: float) -> float:
    """P = I²·R (watts). Pool: E5D11."""
    return current_a * current_a * resistance_ohm


def power_vr(voltage_v: float, resistance_ohm: float) -> float:
    """P = E² / R (watts). Requires R ≠ 0."""
    if resistance_ohm == 0:
        raise ValueError("resistance must be nonzero")
    return voltage_v * voltage_v / resistance_ohm


def solve_ohms_law(voltage_v: float | None = None, current_a: float | None = None,
                   resistance_ohm: float | None = None,
                   power_w: float | None = None) -> dict:
    """Given exactly two of E, I, R and P, return all four as a dict with keys
    ``voltage``, ``current``, ``resistance`` and ``power`` (the "Ohm's law wheel").

    Pass ``None`` for the two unknowns. Resistance and power must be >= 0 when
    given, and the pair must determine the rest (e.g. E = 0 with P given is
    ambiguous and raises ValueError).
    """
    known = {k: v for k, v in (("v", voltage_v), ("i", current_a),
                               ("r", resistance_ohm), ("p", power_w)) if v is not None}
    if len(known) != 2:
        raise ValueError("give exactly two of voltage, current, resistance, power")
    if known.get("r", 0.0) < 0 or known.get("p", 0.0) < 0:
        raise ValueError("resistance and power must be >= 0")
    v, i, r, p = (known.get(k) for k in ("v", "i", "r", "p"))
    pair = frozenset(known)
    try:
        if pair == {"v", "i"}:
            r, p = v / i, v * i
        elif pair == {"v", "r"}:
            i = v / r
            p = v * i
        elif pair == {"v", "p"}:
            i = p / v
            r = v / i
        elif pair == {"i", "r"}:
            v = i * r
            p = i * v
        elif pair == {"i", "p"}:
            v = p / i
            r = v / i
        else:  # r, p
            v = math.sqrt(p * r)
            i = math.sqrt(p / r)
    except ZeroDivisionError as exc:
        raise ValueError("those two values do not determine the other two") from exc
    return {"voltage": v, "current": i, "resistance": r, "power": p}


# --- series / parallel combination ------------------------------------------

def _positive(values: Iterable[float], what: str) -> list[float]:
    vals = [float(v) for v in values]
    if not vals:
        raise ValueError(f"at least one {what} is required")
    if any(v <= 0 for v in vals):
        raise ValueError(f"every {what} must be > 0")
    return vals


def series_sum(values: Iterable[float]) -> float:
    """Straight sum — resistors or inductors in series, capacitors in parallel."""
    return math.fsum(_positive(values, "value"))


def reciprocal_sum(values: Iterable[float]) -> float:
    """1 / Σ(1/xᵢ) — resistors or inductors in parallel, capacitors in series.

    Every value must be > 0. (Two equal parts give half; ``n`` equal parts give
    one ``n``-th.) Pool: E5B04 combines two resistors and two capacitors this way.
    """
    return 1.0 / math.fsum(1.0 / v for v in _positive(values, "value"))


# --- time constants -----------------------------------------------------------

def tau_rc(resistance_ohm: float, capacitance_f: float) -> float:
    """RC time constant τ = R·C (seconds). Pool: E5B04."""
    if resistance_ohm <= 0 or capacitance_f <= 0:
        raise ValueError("resistance and capacitance must be > 0")
    return resistance_ohm * capacitance_f


def tau_rl(resistance_ohm: float, inductance_h: float) -> float:
    """RL time constant τ = L / R (seconds)."""
    if resistance_ohm <= 0 or inductance_h <= 0:
        raise ValueError("resistance and inductance must be > 0")
    return inductance_h / resistance_ohm


def charge_fraction(t_s: float, tau_s: float) -> float:
    """Fraction of the final value reached after ``t`` while charging:
    1 − e^(−t/τ). One τ gives 0.632 (63.2 %). Pool: E5B01."""
    if tau_s <= 0 or t_s < 0:
        raise ValueError("tau must be > 0 and t must be >= 0")
    return -math.expm1(-t_s / tau_s)


def decay_fraction(t_s: float, tau_s: float) -> float:
    """Fraction of the starting value left after ``t`` while discharging:
    e^(−t/τ). One τ leaves 0.368 (36.8 %). Pool: E5B01."""
    if tau_s <= 0 or t_s < 0:
        raise ValueError("tau must be > 0 and t must be >= 0")
    return math.exp(-t_s / tau_s)


def time_to_fraction(fraction: float, tau_s: float) -> float:
    """Time for a charging RC/RL circuit to reach ``fraction`` (0 ≤ f < 1) of
    its final value: t = −τ·ln(1 − f)."""
    if tau_s <= 0:
        raise ValueError("tau must be > 0")
    if not 0.0 <= fraction < 1.0:
        raise ValueError("fraction must be in [0, 1)")
    return -tau_s * math.log1p(-fraction)


# --- impedance, admittance, phase -------------------------------------------

def series_rlc_impedance(freq_hz: float, r_ohm: float, l_h: float, c_f: float) -> complex:
    """Impedance of R, L and C in series at ``freq_hz``:
    Z = R + j(ωL − 1/(ωC)).

    Pass 0 for ``l_h`` or ``c_f`` to leave that part out (a series circuit
    with no capacitor is the same as one with an infinite capacitor).
    """
    if freq_hz <= 0:
        raise ValueError("frequency must be > 0")
    if r_ohm < 0 or l_h < 0 or c_f < 0:
        raise ValueError("R, L and C must be >= 0")
    w = _TWO_PI * freq_hz
    x = w * l_h - (1.0 / (w * c_f) if c_f > 0 else 0.0)
    return complex(r_ohm, x)


def parallel_rlc_impedance(freq_hz: float, r_ohm: float, l_h: float, c_f: float) -> complex:
    """Impedance of R, L and C in parallel at ``freq_hz``:
    Y = 1/R + 1/(jωL) + jωC,  Z = 1/Y.

    Pass 0 for any part to leave it out (an absent parallel branch is an open
    circuit). At least one part is required.
    """
    if freq_hz <= 0:
        raise ValueError("frequency must be > 0")
    if r_ohm < 0 or l_h < 0 or c_f < 0:
        raise ValueError("R, L and C must be >= 0")
    w = _TWO_PI * freq_hz
    y = complex(0.0, 0.0)
    if r_ohm > 0:
        y += 1.0 / r_ohm
    if l_h > 0:
        y += 1.0 / complex(0.0, w * l_h)
    if c_f > 0:
        y += complex(0.0, w * c_f)
    if y == 0:
        raise ValueError("at least one of R, L, C must be > 0 (or the circuit is resonant with no R)")
    return 1.0 / y


def phase_angle_deg(z: complex) -> float:
    """Phase angle of an impedance, degrees: θ = atan2(X, R).

    Positive θ: the circuit is inductive and voltage **leads** current.
    Negative θ: capacitive, voltage **lags** current. Pool: E5B07, E5B08, E5B11.
    """
    z = complex(z)
    if z == 0:
        raise ValueError("impedance must be nonzero")
    return math.degrees(math.atan2(z.imag, z.real))


def admittance(z: complex) -> complex:
    """Y = 1/Z = G + jB (siemens). In polar form the magnitude is 1/|Z| and the
    angle changes sign. Pool: E5B03, E5B05."""
    z = complex(z)
    if z == 0:
        raise ValueError("impedance must be nonzero")
    return 1.0 / z


def polar_to_rect(magnitude: float, angle_deg: float) -> complex:
    """|Z|∠θ → R + jX."""
    return cmath.rect(magnitude, math.radians(angle_deg))


def power_factor(z: complex) -> float:
    """cos θ = R / |Z| for a load impedance (0 … 1 for a passive load)."""
    z = complex(z)
    if z == 0:
        raise ValueError("impedance must be nonzero")
    return z.real / abs(z)


def real_power(v_rms: float, i_rms: float, phase_deg: float) -> float:
    """True power P = E·I·cos θ (watts)."""
    return v_rms * i_rms * math.cos(math.radians(phase_deg))


def reactive_power(v_rms: float, i_rms: float, phase_deg: float) -> float:
    """Reactive power Q = E·I·sin θ (volt-amperes reactive, VAR). Positive for an
    inductive load. It is stored and returned each cycle, not dissipated
    ("wattless" power). Pool: E5D03, E5D09, E5D12."""
    return v_rms * i_rms * math.sin(math.radians(phase_deg))


def apparent_power(v_rms: float, i_rms: float) -> float:
    """Apparent power S = E·I (volt-amperes)."""
    return v_rms * i_rms


# --- circuit Q ----------------------------------------------------------------

def q_series(r_ohm: float, x_ohm: float) -> float:
    """Q of a series RLC circuit (or a reactance with series loss): Q = |X| / R."""
    if r_ohm <= 0:
        raise ValueError("resistance must be > 0")
    return abs(x_ohm) / r_ohm


def q_parallel(r_ohm: float, x_ohm: float) -> float:
    """Q of a parallel RLC circuit: Q = R / |X| (X of L or C at resonance).
    Pool: E5A09."""
    if x_ohm == 0:
        raise ValueError("reactance must be nonzero")
    if r_ohm <= 0:
        raise ValueError("resistance must be > 0")
    return r_ohm / abs(x_ohm)


# --- RLC resonance response (for the Circuit calculator graph) ---------------

def rlc_resonance(r_ohm: float, l_h: float, c_f: float, topology: str = "series") -> dict:
    """Resonance summary of an RLC circuit.

    Returns ``f0`` (Hz), ``x0`` (the reactance of L or C at f0, Ω), ``q``,
    ``bandwidth`` (−3 dB, Hz) and the exact half-power frequencies ``f_low`` /
    ``f_high``. For an ideal series or parallel RLC circuit the half-power
    frequencies are f0·(√(1 + 1/(4Q²)) ∓ 1/(2Q)), so their difference is
    exactly f0/Q. ``topology`` is ``"series"`` (Q = X0/R) or ``"parallel"``
    (Q = R/X0).
    """
    if r_ohm <= 0 or l_h <= 0 or c_f <= 0:
        raise ValueError("R, L and C must be > 0")
    f0 = 1.0 / (_TWO_PI * math.sqrt(l_h * c_f))
    x0 = _TWO_PI * f0 * l_h
    if topology == "series":
        q = x0 / r_ohm
    elif topology == "parallel":
        q = r_ohm / x0
    else:
        raise ValueError("topology must be 'series' or 'parallel'")
    root = math.sqrt(1.0 + 1.0 / (4.0 * q * q))
    half = 1.0 / (2.0 * q)
    return {
        "f0": f0,
        "x0": x0,
        "q": q,
        "bandwidth": f0 / q,
        "f_low": f0 * (root - half),
        "f_high": f0 * (root + half),
    }


def rlc_relative_response(freq_hz: float, r_ohm: float, l_h: float, c_f: float,
                          topology: str = "series") -> float:
    """Response relative to the peak at resonance, 0 … 1.

    Series: current relative to its peak, ``R/|Z|``. Parallel: impedance (so
    voltage for a constant-current drive) relative to its peak, ``|Z|/R``.
    Both equal 1 at f0 and 1/√2 (−3 dB) at the half-power frequencies.
    """
    if topology == "series":
        return r_ohm / abs(series_rlc_impedance(freq_hz, r_ohm, l_h, c_f))
    if topology == "parallel":
        return abs(parallel_rlc_impedance(freq_hz, r_ohm, l_h, c_f)) / r_ohm
    raise ValueError("topology must be 'series' or 'parallel'")
