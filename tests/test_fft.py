"""Tests for the pure-Python FFT/spectral module (:mod:`abax.core.science.fft`)."""

from __future__ import annotations

import math

import pytest

from abax.core.science.fft import (
    FFTError,
    convolve,
    dft,
    fft,
    frequencies,
    ifft,
    magnitude,
    rfft_magnitude,
)

TOL = 1e-9


def _close(got: list[complex], want: list[complex]) -> None:
    assert len(got) == len(want)
    for g, w in zip(got, want):
        assert abs(complex(g) - complex(w)) == pytest.approx(0.0, abs=TOL)


def test_dft_constant():
    _close(dft([1, 1, 1, 1]), [4, 0, 0, 0])


def test_dft_impulse():
    _close(dft([1, 0, 0, 0]), [1, 1, 1, 1])


def test_fft_matches_dft_power_of_two():
    samples = [1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0, 0.0]
    _close(fft(samples), dft(samples))


def test_fft_fallback_matches_dft_non_power_of_two():
    samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert len(samples) == 6
    _close(fft(samples), dft(samples))


def test_ifft_roundtrip_length_8():
    x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    _close(ifft(fft(x)), [complex(v) for v in x])


def test_ifft_roundtrip_length_6():
    x = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0]
    _close(ifft(fft(x)), [complex(v) for v in x])


def test_cosine_peaks_symmetric_pair():
    samples = [math.cos(2 * math.pi * 3 * k / 16) for k in range(16)]
    mags = magnitude(fft(samples))
    order = sorted(range(16), key=lambda k: mags[k], reverse=True)
    top_two = set(order[:2])
    assert top_two == {3, 13}


def test_frequencies():
    assert frequencies(4, 8.0) == pytest.approx([0.0, 2.0, 4.0, 6.0])


def test_rfft_magnitude_peak_and_length():
    n = 16
    samples = [math.cos(2 * math.pi * 3 * k / n) for k in range(n)]
    freqs, mags = rfft_magnitude(samples, sample_rate=16.0)
    assert len(freqs) == n // 2 + 1
    assert len(mags) == n // 2 + 1
    peak = max(range(len(mags)), key=lambda k: mags[k])
    assert freqs[peak] == pytest.approx(3.0)


def test_convolve():
    assert convolve([1, 1, 1], [1, 1]) == pytest.approx([1, 2, 2, 1])


def test_fft_empty_raises():
    with pytest.raises(FFTError):
        fft([])


def test_convolve_empty_raises():
    with pytest.raises(FFTError):
        convolve([], [1, 2])
    with pytest.raises(FFTError):
        convolve([1, 2], [])
