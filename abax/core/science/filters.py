"""Digital-filter design and application: Butterworth IIR, windowed-sinc FIR.

A pure-stdlib (``math``/``cmath``) toolkit for designing and applying digital
filters inside abax. No NumPy/SciPy: the analog Butterworth prototype, bilinear
transform, polynomial expansion, IIR/FIR filtering, and windowed-sinc design are
all implemented by hand in IEEE doubles.

IIR design (:func:`butter_lowpass`, :func:`butter_highpass`,
:func:`butter_bandpass`) places the analog Butterworth poles on the unit circle
in the left-half plane, pre-warps the cutoff frequency, builds the analog
transfer function, and applies the bilinear transform ``s = 2*sr*(z-1)/(z+1)``
to obtain digital ``(b, a)`` transfer-function coefficients (with ``a[0]``
normalised to ``1.0``). Polynomials are expanded from complex roots; the
imaginary parts cancel, so only the real parts are retained.

Filtering: :func:`lfilter` (direct-form-II transposed) and :func:`filtfilt`
(zero-phase, forward-then-reverse). FIR: :func:`fir_lowpass` (Hamming-windowed
sinc) and :func:`fir_filter` (linear convolution, centred to ``"same"`` length).

Bad arguments (non-positive cutoff, cutoff at or above Nyquist, inverted band,
non-positive order, empty/degenerate coefficients) raise :class:`FilterError`.
"""

from __future__ import annotations

import cmath
import math


class FilterError(Exception):
    """Raised when a filter cannot be designed or applied with valid arguments."""


# --- polynomial helpers --------------------------------------------------


def _poly_from_roots(roots: list[complex]) -> list[complex]:
    """Expand ``prod(z - r)`` into ascending-then-returned descending coeffs.

    Returns the polynomial coefficients in descending powers, i.e. ``[1, c1,
    c2, ...]`` for ``z**n + c1*z**(n-1) + ...``. An empty root list yields the
    constant polynomial ``[1]``.
    """
    coeffs: list[complex] = [1.0 + 0.0j]
    for r in roots:
        # Multiply existing polynomial by (z - r).
        new = [0.0j] * (len(coeffs) + 1)
        for i, c in enumerate(coeffs):
            new[i] += c
            new[i + 1] += -r * c
        coeffs = new
    return coeffs


def _real(coeffs: list[complex]) -> list[float]:
    """Take the real part of each (near-real) complex coefficient."""
    return [c.real for c in coeffs]


# --- Butterworth analog prototype + bilinear transform -------------------


def _butter_analog_poles(order: int) -> list[complex]:
    """Left-half-plane Butterworth poles on the unit circle (Wc = 1)."""
    poles: list[complex] = []
    for k in range(order):
        theta = math.pi * (2 * k + order + 1) / (2 * order)
        poles.append(cmath.exp(1j * theta))
    return poles


def _prewarp(fc: float, sr: float) -> float:
    """Pre-warp a digital cutoff ``fc`` to an analog frequency for bilinear."""
    return 2.0 * sr * math.tan(math.pi * fc / sr)


def _bilinear(zeros: list[complex], poles: list[complex], gain: complex,
              sr: float) -> tuple[list[float], list[float]]:
    """Bilinear-transform analog zeros/poles/gain into digital ``(b, a)``.

    Maps each analog root ``s`` to ``z = (2*sr + s) / (2*sr - s)``; analog zeros
    at infinity become digital zeros at ``z = -1``. The gain is corrected by the
    standard bilinear factor so the discrete transfer function matches.
    """
    fs2 = 2.0 * sr
    n_poles = len(poles)
    n_zeros = len(zeros)

    z_zeros = [(fs2 + z) / (fs2 - z) for z in zeros]
    z_poles = [(fs2 + p) / (fs2 - p) for p in poles]
    # Zeros at infinity map to z = -1.
    z_zeros += [-1.0 + 0.0j] * (n_poles - n_zeros)

    # Gain correction factor from the bilinear substitution.
    num_corr = 1.0 + 0.0j
    for z in zeros:
        num_corr *= (fs2 - z)
    den_corr = 1.0 + 0.0j
    for p in poles:
        den_corr *= (fs2 - p)
    k_digital = gain * num_corr / den_corr

    b = _poly_from_roots(z_zeros)
    a = _poly_from_roots(z_poles)
    b = [k_digital * c for c in b]

    b_real = _real(b)
    a_real = _real(a)

    a0 = a_real[0]
    if a0 == 0.0:
        raise FilterError("degenerate denominator after bilinear transform")
    b_real = [c / a0 for c in b_real]
    a_real = [c / a0 for c in a_real]
    return b_real, a_real


def _validate_cutoff(cutoff: float, sr: float) -> None:
    nyquist = sr / 2.0
    if sr <= 0.0:
        raise FilterError("sample_rate must be positive")
    if cutoff <= 0.0:
        raise FilterError("cutoff must be positive")
    if cutoff >= nyquist:
        raise FilterError("cutoff must be below the Nyquist frequency")


def butter_lowpass(cutoff: float, sample_rate: float,
                   order: int = 2) -> tuple[list[float], list[float]]:
    """Design a digital Butterworth low-pass filter.

    Returns ``(b, a)`` transfer-function coefficients with ``a[0] == 1.0``. The
    DC gain ``sum(b)/sum(a)`` is approximately 1. Raises :class:`FilterError`
    for ``order < 1`` or a cutoff that is non-positive or at/above Nyquist.
    """
    if order < 1:
        raise FilterError("order must be at least 1")
    _validate_cutoff(cutoff, sample_rate)

    wc = _prewarp(cutoff, sample_rate)
    proto = _butter_analog_poles(order)
    # Scale prototype (Wc = 1) to the analog cutoff wc.
    poles = [p * wc for p in proto]
    zeros: list[complex] = []
    gain = wc ** order  # so H(0) == 1 for the analog filter
    return _bilinear(zeros, poles, gain + 0.0j, sample_rate)


def butter_highpass(cutoff: float, sample_rate: float,
                    order: int = 2) -> tuple[list[float], list[float]]:
    """Design a digital Butterworth high-pass filter.

    Returns ``(b, a)`` with ``a[0] == 1.0`` and ~zero gain at DC. Raises
    :class:`FilterError` for ``order < 1`` or a bad cutoff.
    """
    if order < 1:
        raise FilterError("order must be at least 1")
    _validate_cutoff(cutoff, sample_rate)

    wc = _prewarp(cutoff, sample_rate)
    proto = _butter_analog_poles(order)
    # Low-pass -> high-pass: p -> wc / p, and add `order` zeros at the origin.
    poles = [wc / p for p in proto]
    zeros = [0.0 + 0.0j] * order
    # High-pass analog gain is unity at high frequency; bilinear correction
    # handles the rest, so the leading gain is 1.
    gain = 1.0 + 0.0j
    return _bilinear(zeros, poles, gain, sample_rate)


def butter_bandpass(low: float, high: float, sample_rate: float,
                    order: int = 2) -> tuple[list[float], list[float]]:
    """Design a digital Butterworth band-pass filter for ``[low, high]``.

    The analog low-pass prototype of the given ``order`` is transformed to a
    band-pass of order ``2*order`` (a pole pair per prototype pole) and bilinear
    transformed. Raises :class:`FilterError` for ``order < 1``, a non-positive
    or supra-Nyquist edge, or ``low >= high``.
    """
    if order < 1:
        raise FilterError("order must be at least 1")
    _validate_cutoff(low, sample_rate)
    _validate_cutoff(high, sample_rate)
    if low >= high:
        raise FilterError("low must be below high")

    wl = _prewarp(low, sample_rate)
    wh = _prewarp(high, sample_rate)
    w0_sq = wl * wh          # centre frequency squared
    bw = wh - wl             # bandwidth

    proto = _butter_analog_poles(order)
    poles: list[complex] = []
    for p in proto:
        # Low-pass -> band-pass: s -> (s^2 + w0^2) / (bw * s).
        # Each prototype pole p yields the roots of s^2 - (bw*p)*s + w0^2 = 0.
        half = p * bw / 2.0
        disc = cmath.sqrt(half * half - w0_sq)
        poles.append(half + disc)
        poles.append(half - disc)
    # Band-pass has `order` zeros at the origin (one per prototype pole order).
    zeros = [0.0 + 0.0j] * order
    gain = (bw ** order) + 0.0j
    return _bilinear(zeros, poles, gain, sample_rate)


# --- IIR filtering -------------------------------------------------------


def lfilter(b: list[float], a: list[float], xs: list[float]) -> list[float]:
    """Apply an IIR filter ``(b, a)`` to ``xs`` (direct-form-II transposed).

    Output length equals ``len(xs)``. Raises :class:`FilterError` if ``b`` is
    empty or ``a`` is empty or ``a[0] == 0``.
    """
    if not b:
        raise FilterError("numerator b must be non-empty")
    if not a:
        raise FilterError("denominator a must be non-empty")
    if a[0] == 0.0:
        raise FilterError("a[0] must be non-zero")

    a0 = a[0]
    bn = [c / a0 for c in b]
    an = [c / a0 for c in a]

    n = max(len(bn), len(an))
    # Pad to common length for the transposed-direct-form-II state recurrence.
    bn = bn + [0.0] * (n - len(bn))
    an = an + [0.0] * (n - len(an))
    z = [0.0] * (n - 1)  # filter state

    out: list[float] = []
    for x in xs:
        y = bn[0] * x + (z[0] if z else 0.0)
        for i in range(1, n - 1):
            z[i - 1] = bn[i] * x + z[i] - an[i] * y
        if n - 1 >= 1:
            z[n - 2] = bn[n - 1] * x - an[n - 1] * y
        out.append(y)
    return out


def filtfilt(b: list[float], a: list[float], xs: list[float]) -> list[float]:
    """Zero-phase filtering: forward, reverse, filter again, reverse back.

    Cancels phase distortion (at the cost of squaring the magnitude response).
    Output length equals ``len(xs)``.
    """
    if not xs:
        return []
    forward = lfilter(b, a, xs)
    backward = lfilter(b, a, forward[::-1])
    return backward[::-1]


# --- FIR design + filtering ----------------------------------------------


def fir_lowpass(cutoff: float, sample_rate: float,
                numtaps: int = 51) -> list[float]:
    """Design a windowed-sinc (Hamming) FIR low-pass filter.

    ``numtaps`` is bumped up by one if even so the filter is symmetric and has
    an integer group delay (linear phase). Coefficients are normalised to unit
    DC gain. Raises :class:`FilterError` for a bad cutoff or ``numtaps < 1``.
    """
    if numtaps < 1:
        raise FilterError("numtaps must be at least 1")
    _validate_cutoff(cutoff, sample_rate)

    if numtaps % 2 == 0:
        numtaps += 1

    fc = cutoff / sample_rate  # normalised cutoff (cycles/sample), 0..0.5
    m = numtaps - 1
    half = m / 2.0
    taps: list[float] = []
    for i in range(numtaps):
        k = i - half
        if k == 0.0:
            sinc = 2.0 * fc
        else:
            sinc = math.sin(2.0 * math.pi * fc * k) / (math.pi * k)
        # Hamming window.
        window = 0.54 - 0.46 * math.cos(2.0 * math.pi * i / m)
        taps.append(sinc * window)

    total = sum(taps)
    if total == 0.0:
        raise FilterError("degenerate FIR design (zero DC gain)")
    return [t / total for t in taps]


def fir_filter(taps: list[float], xs: list[float]) -> list[float]:
    """Apply an FIR filter ``taps`` to ``xs`` by linear convolution.

    The full convolution is centred and truncated to ``"same"`` length as
    ``xs``. Raises :class:`FilterError` for empty ``taps``.
    """
    if not taps:
        raise FilterError("taps must be non-empty")
    if not xs:
        return []

    n = len(xs)
    m = len(taps)
    full = [0.0] * (n + m - 1)
    for i, x in enumerate(xs):
        for j, t in enumerate(taps):
            full[i + j] += x * t
    # 'same' output: centre slice of length n.
    start = (m - 1) // 2
    return full[start:start + n]
