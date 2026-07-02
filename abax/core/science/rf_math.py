"""Additional amateur-radio / RF math: resonant-circuit component values, Q/bandwidth, air-core & toroid inductor design, matching, SWR-from-power, loop antennas, dish gain/beamwidth, and Doppler shift. Pure stdlib; SI base units (Hz, H, F, m, W, ohm). Domain errors raise ValueError."""

from __future__ import annotations

import math

_C = 299_792_458.0          # speed of light, m/s
_TWO_PI = 2.0 * math.pi


# --- reactance <-> component ----------------------------------------------

def capacitance_from_reactance(xc_ohms: float, freq_hz: float) -> float:
    """C = 1 / (2*pi*f*Xc). Farads. Requires xc_ohms>0 and freq_hz>0."""
    if xc_ohms <= 0 or freq_hz <= 0:
        raise ValueError("reactance and frequency must be > 0")
    return 1.0 / (_TWO_PI * freq_hz * xc_ohms)


def inductance_from_reactance(xl_ohms: float, freq_hz: float) -> float:
    """L = Xl / (2*pi*f). Henries. Requires freq_hz>0."""
    if freq_hz <= 0:
        raise ValueError("frequency must be > 0")
    return xl_ohms / (_TWO_PI * freq_hz)


# --- resonance ------------------------------------------------------------

def resonant_capacitance(freq_hz: float, inductance_h: float) -> float:
    """C to resonate with L at f:  C = 1 / ((2*pi*f)**2 * L). Farads.
    Requires freq_hz>0 and inductance_h>0."""
    if freq_hz <= 0 or inductance_h <= 0:
        raise ValueError("frequency and inductance must be > 0")
    return 1.0 / ((_TWO_PI * freq_hz) ** 2 * inductance_h)


def resonant_inductance(freq_hz: float, capacitance_f: float) -> float:
    """L to resonate with C at f:  L = 1 / ((2*pi*f)**2 * C). Henries.
    Requires freq_hz>0 and capacitance_f>0."""
    if freq_hz <= 0 or capacitance_f <= 0:
        raise ValueError("frequency and capacitance must be > 0")
    return 1.0 / ((_TWO_PI * freq_hz) ** 2 * capacitance_f)


# --- Q / bandwidth --------------------------------------------------------

def q_from_bandwidth(center_hz: float, bandwidth_hz: float) -> float:
    """Loaded Q = f0 / BW. Requires bandwidth_hz>0."""
    if bandwidth_hz <= 0:
        raise ValueError("bandwidth must be > 0")
    return center_hz / bandwidth_hz


def bandwidth_from_q(center_hz: float, q: float) -> float:
    """BW = f0 / Q (Hz). Requires q>0."""
    if q <= 0:
        raise ValueError("Q must be > 0")
    return center_hz / q


# --- air-core solenoid (Wheeler 1928) -------------------------------------

def air_core_inductance(diameter_m: float, length_m: float, turns: float) -> float:
    """Single-layer air-core solenoid inductance via Wheeler's 1928 formula.
    Wheeler (imperial): L[uH] = (d_in**2 * N**2) / (18*d_in + 40*len_in), where
    d_in and len_in are the coil diameter and length in INCHES. Convert the SI
    inputs (metres) to inches (/0.0254), apply Wheeler, return HENRIES (uH*1e-6).
    Requires diameter_m>0, length_m>0, turns>0."""
    if diameter_m <= 0 or length_m <= 0 or turns <= 0:
        raise ValueError("diameter, length and turns must be > 0")
    d_in = diameter_m / 0.0254
    len_in = length_m / 0.0254
    l_uh = (d_in ** 2 * turns ** 2) / (18.0 * d_in + 40.0 * len_in)
    return l_uh * 1e-6


def air_core_turns(inductance_h: float, diameter_m: float, length_m: float) -> float:
    """Turns N needed for a target inductance (inverse of Wheeler):
    N = sqrt( L_uH * (18*d_in + 40*len_in) ) / d_in. Return a float turn count.
    Requires all inputs > 0."""
    if inductance_h <= 0 or diameter_m <= 0 or length_m <= 0:
        raise ValueError("inductance, diameter and length must be > 0")
    d_in = diameter_m / 0.0254
    len_in = length_m / 0.0254
    l_uh = inductance_h * 1e6
    return math.sqrt(l_uh * (18.0 * d_in + 40.0 * len_in)) / d_in


# --- toroid / powdered-iron core (AL value) -------------------------------

def toroid_inductance(al_nh: float, turns: float) -> float:
    """Toroid/core inductance from the AL value (datasheet convention nH per
    turn^2):  L = AL * N**2 (nH), returned in HENRIES (*1e-9).
    Requires al_nh>0, turns>0."""
    if al_nh <= 0 or turns <= 0:
        raise ValueError("AL and turns must be > 0")
    return al_nh * turns ** 2 * 1e-9


def toroid_turns(inductance_h: float, al_nh: float) -> float:
    """Turns for a target inductance on a core of AL (nH/turn^2):
    N = sqrt( L_nH / AL ) = sqrt( (L_h*1e9) / al_nh ). Float turn count.
    Requires inductance_h>0, al_nh>0."""
    if inductance_h <= 0 or al_nh <= 0:
        raise ValueError("inductance and AL must be > 0")
    return math.sqrt((inductance_h * 1e9) / al_nh)


# --- matching / SWR -------------------------------------------------------

def quarter_wave_z0(z1_ohms: float, z2_ohms: float) -> float:
    """Characteristic impedance of a quarter-wave matching transformer between
    two real impedances:  Z0 = sqrt(Z1 * Z2). Ohms. Requires z1>0 and z2>0."""
    if z1_ohms <= 0 or z2_ohms <= 0:
        raise ValueError("both impedances must be > 0")
    return math.sqrt(z1_ohms * z2_ohms)


def swr_from_power(forward_w: float, reflected_w: float) -> float:
    """VSWR from forward & reflected power.  gamma = sqrt(Pr/Pf);
    SWR = (1+gamma)/(1-gamma). Requires forward_w>0 and 0<=reflected_w<forward_w
    (equal powers -> infinite SWR -> raise ValueError)."""
    if forward_w <= 0:
        raise ValueError("forward power must be > 0")
    if reflected_w < 0:
        raise ValueError("reflected power must be >= 0")
    if reflected_w >= forward_w:
        raise ValueError("reflected power must be < forward power (SWR would be infinite)")
    gamma = math.sqrt(reflected_w / forward_w)
    return (1.0 + gamma) / (1.0 - gamma)


# --- loop antenna ---------------------------------------------------------

def loop_length(freq_hz: float) -> float:
    """Total wire length of a full-wave (1 lambda) loop antenna, with the common
    amateur 'full-wave loop' factor: L_m = 306.3 / f_MHz  (i.e. 1005/f_MHz feet,
    converted to metres). Requires freq_hz>0."""
    if freq_hz <= 0:
        raise ValueError("frequency must be > 0")
    f_mhz = freq_hz / 1e6
    return 306.3 / f_mhz


# --- parabolic dish -------------------------------------------------------

def parabolic_gain_dbi(diameter_m: float, freq_hz: float, efficiency: float = 0.55) -> float:
    """Parabolic-dish gain:  G = 10*log10( efficiency * (pi*D/lambda)**2 ) dBi,
    lambda = c/f. Requires diameter_m>0, freq_hz>0, 0<efficiency<=1."""
    if diameter_m <= 0 or freq_hz <= 0:
        raise ValueError("diameter and frequency must be > 0")
    if not 0.0 < efficiency <= 1.0:
        raise ValueError("efficiency must be in (0, 1]")
    lam = _C / freq_hz
    return 10.0 * math.log10(efficiency * (math.pi * diameter_m / lam) ** 2)


def parabolic_beamwidth_deg(diameter_m: float, freq_hz: float) -> float:
    """Parabolic-dish -3 dB beamwidth (deg), HPBW ~= 70 * lambda / D.
    Requires diameter_m>0, freq_hz>0."""
    if diameter_m <= 0 or freq_hz <= 0:
        raise ValueError("diameter and frequency must be > 0")
    lam = _C / freq_hz
    return 70.0 * lam / diameter_m


# --- transmission line -----------------------------------------------------

def zin_line(z_load_complex: complex, z0: float, electrical_length_deg: float) -> complex:
    """Input impedance of a lossless transmission line terminated in ``Z_L``:

        Zin = Z0 * (ZL + j*Z0*tan(bl)) / (Z0 + j*ZL*tan(bl))

    where ``bl`` (beta*l) is the electrical length in radians. ``z_load_complex``
    is the (complex) load impedance and ``z0`` the (real) characteristic impedance
    in ohms; ``electrical_length_deg`` is the line length in electrical degrees
    (90 deg = quarter wave, 180 deg = half wave). Returns a complex impedance.

    A quarter-wave line (90 deg) transforms ZL to Z0**2/ZL; a half-wave line
    (180 deg) repeats the load (Zin = ZL). Requires z0 > 0.
    """
    if z0 <= 0:
        raise ValueError("characteristic impedance must be > 0")
    zl = complex(z_load_complex)
    bl = math.radians(electrical_length_deg)
    # cos(bl)==0 (odd multiples of 90 deg) -> tan diverges; use the cos/sin form
    # so the quarter-wave case is exact rather than an overflow.
    c = math.cos(bl)
    s = math.sin(bl)
    num = zl * c + 1j * z0 * s
    den = z0 * c + 1j * zl * s
    if den == 0:
        raise ValueError("degenerate line (division by zero)")
    return z0 * num / den


def line_loss_db(length_m: float, freq_hz: float, matched_loss_db_per_100m: float) -> float:
    """Matched (SWR = 1) transmission-line loss in dB.

    Textbook model: for a matched line the loss in dB scales linearly with the
    physical length, so ``loss = matched_loss_db_per_100m * (length_m / 100)``.
    ``matched_loss_db_per_100m`` is the cable's rated matched loss per 100 m at
    the frequency of interest (``freq_hz`` is carried for API symmetry with the
    frequency-dependent RF functions and validated as > 0 but does not otherwise
    enter this simple linear model). Requires length_m >= 0, freq_hz > 0 and
    matched_loss_db_per_100m >= 0.
    """
    if length_m < 0:
        raise ValueError("length must be >= 0")
    if freq_hz <= 0:
        raise ValueError("frequency must be > 0")
    if matched_loss_db_per_100m < 0:
        raise ValueError("matched loss must be >= 0")
    return matched_loss_db_per_100m * (length_m / 100.0)


def stub_match_short(z_load_complex: complex, z0: float) -> tuple[float, float]:
    """Shunt single-stub match with a SHORT-circuited stub.

    Standard closed-form for matching a complex load ``ZL`` to a real line of
    characteristic impedance ``Z0`` with a shorted shunt stub. Returns
    ``(distance_wl, stub_len_wl)`` — the distance from the load to the stub and
    the stub length, both in wavelengths (0 <= value < 0.5).

    Derivation (Pozar, *Microwave Engineering*): with normalized load admittance,
    pick the line length ``d`` so the real part of the normalized input admittance
    at the stub point equals 1; the shorted stub then cancels the residual
    (normalized) susceptance ``b``. For a shorted stub the input susceptance is
    ``-cot(bl)``, so ``l = atan2(-1, b) / (2*pi)`` in wavelengths (folded into
    ``[0, 0.5)``). Requires z0 > 0 and a load with a non-zero real part.
    """
    if z0 <= 0:
        raise ValueError("characteristic impedance must be > 0")
    zl = complex(z_load_complex)
    rl, xl = zl.real, zl.imag
    if rl <= 0:
        raise ValueError("load must have a positive real part")

    if abs(rl - z0) < 1e-12 and abs(xl) < 1e-12:
        # already matched: zero-length line, stub does nothing (half wavelength)
        return 0.0, 0.5

    # t = tan(beta*d); Pozar eqn (5.9): solve R(d)=Z0.
    if abs(rl - z0) < 1e-12:
        t = -xl / (2.0 * z0)
    else:
        disc = rl * ((z0 - rl) ** 2 + xl ** 2) / z0
        t = (xl + math.sqrt(disc)) / (rl - z0)

    d = math.atan(t) / _TWO_PI
    if d < 0:
        d += 0.5

    # Normalized input admittance at the stub point; by construction its
    # conductance is 1, and we read off the residual susceptance b to cancel.
    bl = _TWO_PI * d
    tb = math.tan(bl)
    zin = z0 * (zl + 1j * z0 * tb) / (z0 + 1j * zl * tb)
    b_norm = (z0 / zin).imag   # y_in * Z0 = 1 + j*b_norm

    # A short-circuited shunt stub presents normalized susceptance -cot(beta*l);
    # to cancel +b_norm we need cot(beta*l) = b_norm, i.e. tan(beta*l) = 1/b_norm.
    stub_len = math.atan2(1.0, b_norm) / _TWO_PI
    if stub_len < 0:
        stub_len += 0.5
    return d, stub_len


# --- Doppler --------------------------------------------------------------

def doppler_shift_hz(freq_hz: float, velocity_mps: float) -> float:
    """Non-relativistic Doppler shift:  df = f * v / c, where positive v means the
    source and observer are closing (received frequency higher). Requires freq_hz>0.
    velocity_mps may be negative (opening)."""
    if freq_hz <= 0:
        raise ValueError("frequency must be > 0")
    return freq_hz * velocity_mps / _C
