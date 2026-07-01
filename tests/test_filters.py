"""Tests for the digital-filter module (Butterworth IIR + windowed-sinc FIR)."""

from __future__ import annotations

import math

import pytest

from abax.core.science.filters import (
    FilterError,
    butter_bandpass,
    butter_highpass,
    butter_lowpass,
    filtfilt,
    fir_filter,
    fir_lowpass,
    lfilter,
)

# --- helpers -------------------------------------------------------------


def _rms(xs: list[float]) -> float:
    if not xs:
        return 0.0
    return math.sqrt(sum(x * x for x in xs) / len(xs))


def _corr(a: list[float], b: list[float]) -> float:
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n)))
    db = math.sqrt(sum((b[i] - mb) ** 2 for i in range(n)))
    if da == 0.0 or db == 0.0:
        return 0.0
    return num / (da * db)


def _signals(sr: float = 1000.0, n: int = 1000):
    t = [i / sr for i in range(n)]
    low = [math.sin(2 * math.pi * 20 * ti) for ti in t]
    high = [math.sin(2 * math.pi * 400 * ti) for ti in t]
    return low, high


# --- IIR design ----------------------------------------------------------


def test_butter_lowpass_shape_and_dc_gain():
    b, a = butter_lowpass(100, 1000, 2)
    assert len(a) == 3
    assert a[0] == 1.0
    assert math.isclose(sum(b) / sum(a), 1.0, abs_tol=1e-6)


def test_butter_lowpass_orders():
    for order in (1, 2, 3, 4):
        b, a = butter_lowpass(100, 1000, order)
        assert a[0] == 1.0
        assert len(a) == order + 1
        assert math.isclose(sum(b) / sum(a), 1.0, abs_tol=1e-6)


def test_butter_highpass_dc_gain_near_zero():
    b, a = butter_highpass(100, 1000, 2)
    assert a[0] == 1.0
    # DC gain ~ 0 for a high-pass.
    assert abs(sum(b) / sum(a)) < 1e-6


# --- functional filtering ------------------------------------------------


def test_lowpass_attenuates_high_freq():
    low, high = _signals()
    mixed = [low[i] + high[i] for i in range(len(low))]
    b, a = butter_lowpass(80, 1000, 4)
    out = filtfilt(b, a, mixed)
    assert len(out) == len(mixed)
    # 400 Hz strongly attenuated: the mixed RMS is ~1.0 (two orthogonal sines);
    # the result collapses to ~the 20 Hz component (RMS ~0.707).
    assert _rms(out) < 0.75 * _rms(mixed)
    # Preserves most of the 20 Hz energy.
    assert _rms(out) > 0.9 * _rms(low)
    # The 400 Hz component alone is almost entirely removed.
    assert _rms(filtfilt(b, a, high)) < 0.05


def test_filtfilt_zero_phase():
    low, _ = _signals()
    b, a = butter_lowpass(80, 1000, 4)
    out = filtfilt(b, a, low)
    assert _corr(out, low) > 0.9


def test_highpass_attenuates_low_freq():
    low, _ = _signals()
    b, a = butter_highpass(80, 1000, 4)
    out = filtfilt(b, a, low)
    assert _rms(out) < 0.3


def test_bandpass_passes_band():
    low, high = _signals()
    # Pass band around 20 Hz; should keep low, drop high.
    b, a = butter_bandpass(10, 40, 1000, 2)
    out_low = filtfilt(b, a, low)
    out_high = filtfilt(b, a, high)
    assert _rms(out_high) < 0.3
    assert _rms(out_low) > 0.4 * _rms(low)


# --- lfilter -------------------------------------------------------------


def test_lfilter_identity():
    xs = [1.0, 2.0, 3.0, -4.0, 5.0]
    out = lfilter([1, 0, 0], [1, 0, 0], xs)
    assert out == xs


def test_lfilter_length():
    xs = [float(i) for i in range(50)]
    b, a = butter_lowpass(100, 1000, 2)
    out = lfilter(b, a, xs)
    assert len(out) == len(xs)


# --- FIR -----------------------------------------------------------------


def test_fir_lowpass_taps():
    taps = fir_lowpass(100, 1000, 51)
    assert len(taps) == 51
    assert math.isclose(sum(taps), 1.0, abs_tol=1e-9)
    # Symmetric (linear phase).
    for i in range(len(taps)):
        assert math.isclose(taps[i], taps[-1 - i], abs_tol=1e-12)


def test_fir_lowpass_even_bumps_to_odd():
    taps = fir_lowpass(100, 1000, 50)
    assert len(taps) == 51


def test_fir_lowpass_attenuates_high_freq():
    low, high = _signals()
    taps = fir_lowpass(80, 1000, 101)
    out_high = fir_filter(taps, high)
    out_low = fir_filter(taps, low)
    assert len(out_high) == len(high)
    assert _rms(out_high) < 0.3
    assert _rms(out_low) > 0.4 * _rms(low)


# --- error paths ---------------------------------------------------------


def test_errors_order_too_low():
    with pytest.raises(FilterError):
        butter_lowpass(100, 1000, 0)


def test_errors_cutoff_at_nyquist():
    with pytest.raises(FilterError):
        butter_lowpass(500, 1000, 2)
    with pytest.raises(FilterError):
        butter_lowpass(600, 1000, 2)


def test_errors_cutoff_non_positive():
    with pytest.raises(FilterError):
        butter_lowpass(0, 1000, 2)


def test_errors_band_inverted():
    with pytest.raises(FilterError):
        butter_bandpass(40, 10, 1000, 2)


def test_errors_lfilter_a0_zero():
    with pytest.raises(FilterError):
        lfilter([1, 2], [0, 1], [1.0, 2.0])


def test_errors_lfilter_empty_b():
    with pytest.raises(FilterError):
        lfilter([], [1], [1.0])


def test_errors_fir_bad_numtaps():
    with pytest.raises(FilterError):
        fir_lowpass(100, 1000, 0)
