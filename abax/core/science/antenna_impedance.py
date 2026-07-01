"""Center-fed thin-wire dipole input impedance (induced-EMF method).

Pure stdlib. This is the classic closed-form impedance of a straight, center-fed
dipole carrying an assumed sinusoidal current, evaluated with the sine and cosine
integrals (Balanis, *Antenna Theory*, eqns 4-70 / 4-79). It reproduces the
textbook half-wave result **73.1 + j42.5 Ω** and the slight shortening to
resonance (X = 0 near 0.47-0.48 λ) caused by finite wire radius.

It is an *analytic* model -- it does not discretize the wire. A full
multi-segment Method-of-Moments solver (for arbitrary geometries) builds on this
as its validation oracle; see :mod:`abax.core.science.mom`.

Lengths are in wavelengths. Domain errors raise :class:`ValueError`.
"""

from __future__ import annotations

import math

ETA = 120.0 * math.pi          # free-space wave impedance used by the textbook form
_EULER = 0.5772156649015329    # Euler-Mascheroni constant
_SIMPSON_N = 2000              # even; Simpson panels for Si/Ci


def sine_integral(x: float) -> float:
    """Si(x) = integral_0^x sin(t)/t dt (Simpson quadrature; Si(0)=0)."""
    if x == 0.0:
        return 0.0
    if x < 0.0:
        return -sine_integral(-x)
    h = x / _SIMPSON_N
    total = 1.0 + math.sin(x) / x          # f(0)=1, f(x)
    for i in range(1, _SIMPSON_N):
        t = i * h
        total += (4.0 if i % 2 else 2.0) * (math.sin(t) / t)
    return total * h / 3.0


def cosine_integral(x: float) -> float:
    """Ci(x) = gamma + ln(x) + integral_0^x (cos(t)-1)/t dt (x > 0)."""
    if x <= 0.0:
        raise ValueError("cosine_integral requires x > 0")
    h = x / _SIMPSON_N
    total = 0.0 + (math.cos(x) - 1.0) / x   # g(0)=0 (limit), g(x)
    for i in range(1, _SIMPSON_N):
        t = i * h
        total += (4.0 if i % 2 else 2.0) * ((math.cos(t) - 1.0) / t)
    return _EULER + math.log(x) + total * h / 3.0


def _r_at_current_max(kL: float) -> float:
    """Radiation resistance referred to the current maximum (Balanis 4-70)."""
    sin_kl, cos_kl = math.sin(kL), math.cos(kL)
    bracket = (
        _EULER + math.log(kL) - cosine_integral(kL)
        + 0.5 * sin_kl * (sine_integral(2 * kL) - 2 * sine_integral(kL))
        + 0.5 * cos_kl * (_EULER + math.log(kL / 2.0)
                          + cosine_integral(2 * kL) - 2 * cosine_integral(kL))
    )
    return ETA / (2.0 * math.pi) * bracket


def _x_at_current_max(kL: float, radius_wl: float) -> float:
    """Reactance referred to the current maximum (Balanis 4-79)."""
    sin_kl, cos_kl = math.sin(kL), math.cos(kL)
    # Ci argument 2*k*a^2/L  ->  4*pi*radius_wl^2 / length_wl, with length_wl=kL/2pi
    length_wl = kL / (2.0 * math.pi)
    ci_arg = 4.0 * math.pi * radius_wl * radius_wl / length_wl
    bracket = (
        2.0 * sine_integral(kL)
        + cos_kl * (2.0 * sine_integral(kL) - sine_integral(2 * kL))
        - sin_kl * (2.0 * cosine_integral(kL) - cosine_integral(2 * kL)
                    - cosine_integral(ci_arg))
    )
    return ETA / (4.0 * math.pi) * bracket


def radiation_resistance(length_wl: float) -> float:
    """Radiation resistance (ohms) of a center-fed dipole, referred to the
    current maximum. ``length_wl`` is the total length in wavelengths."""
    if length_wl <= 0.0:
        raise ValueError("length must be > 0")
    return _r_at_current_max(2.0 * math.pi * length_wl)


def dipole_input_impedance(length_wl: float, radius_wl: float = 1e-4) -> complex:
    """Input impedance (ohms, complex) at the center feed of a thin dipole.

    Referred to the input terminals: the current-maximum impedance is divided by
    ``sin^2(kL/2)`` to move the reference to the feed. For a half-wave dipole the
    current maximum is at the feed, so the result is ``~73.1 + 42.5j``. Near a
    full wavelength ``sin(kL/2) -> 0`` and the model blows up (the assumed-current
    method is not valid there) -- raises :class:`ValueError` within 1% of n*lambda.
    """
    if length_wl <= 0.0:
        raise ValueError("length must be > 0")
    if radius_wl <= 0.0:
        raise ValueError("radius must be > 0")
    kL = 2.0 * math.pi * length_wl
    s = math.sin(kL / 2.0)
    if abs(s) < 0.01:
        raise ValueError("model singular near integer-wavelength dipoles")
    r = _r_at_current_max(kL) / (s * s)
    x = _x_at_current_max(kL, radius_wl) / (s * s)
    return complex(r, x)


def resonant_length(radius_wl: float = 1e-4,
                    lo: float = 0.40, hi: float = 0.499) -> float:
    """The dipole length (wavelengths) near a half wave where the reactance is
    zero -- i.e. the natural resonance, slightly under 0.5 lambda for real wire.

    Bisects the current-maximum reactance (whose sign matches the input
    reactance) between ``lo`` and ``hi``. Raises :class:`ValueError` if the
    reactance does not change sign across the bracket.
    """
    if radius_wl <= 0.0:
        raise ValueError("radius must be > 0")

    def x_of(length_wl: float) -> float:
        return _x_at_current_max(2.0 * math.pi * length_wl, radius_wl)

    f_lo, f_hi = x_of(lo), x_of(hi)
    if f_lo == 0.0:
        return lo
    if f_hi == 0.0:
        return hi
    if (f_lo > 0.0) == (f_hi > 0.0):
        raise ValueError("no reactance sign change in the bracket")
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        f_mid = x_of(mid)
        if f_mid == 0.0 or (hi - lo) < 1e-9:
            return mid
        if (f_mid > 0.0) == (f_lo > 0.0):
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
    return 0.5 * (lo + hi)
