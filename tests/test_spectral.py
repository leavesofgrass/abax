"""Tests for :mod:`qcell.core.science.spectral`: next_pow2, STFT/spectrogram, fft_convolve."""

from __future__ import annotations

import math
import random

import pytest

from qcell.core.science import fft as core_fft
from qcell.core.science import spectral

# --- next_pow2 -------------------------------------------------------------


def test_next_pow2_values():
    assert spectral.next_pow2(1) == 1
    assert spectral.next_pow2(5) == 8
    assert spectral.next_pow2(8) == 8
    assert spectral.next_pow2(9) == 16


def test_next_pow2_rejects_below_one():
    with pytest.raises(spectral.SpectralError):
        spectral.next_pow2(0)
    with pytest.raises(spectral.SpectralError):
        spectral.next_pow2(-3)


# --- fft_convolve ----------------------------------------------------------


def test_fft_convolve_small():
    out = spectral.fft_convolve([1, 1, 1], [1, 1])
    assert out == pytest.approx([1, 2, 2, 1], abs=1e-6)


def test_fft_convolve_matches_direct():
    random.seed(1234)
    a = [random.uniform(-5, 5) for _ in range(9)]
    b = [random.uniform(-5, 5) for _ in range(5)]
    fast = spectral.fft_convolve(a, b)
    direct = core_fft.convolve(a, b)
    assert len(fast) == len(direct) == len(a) + len(b) - 1
    for f, d in zip(fast, direct):
        assert f == pytest.approx(d, abs=1e-6)


def test_fft_convolve_empty():
    with pytest.raises(spectral.SpectralError):
        spectral.fft_convolve([], [1, 2])
    with pytest.raises(spectral.SpectralError):
        spectral.fft_convolve([1, 2], [])


# --- stft ------------------------------------------------------------------


def _sine(n: int, freq: float, sr: float) -> list[float]:
    return [math.sin(2.0 * math.pi * freq * k / sr) for k in range(n)]


def test_stft_shape_and_peak():
    sr = 256.0
    f = 16.0
    frame_size = 64
    samples = _sine(512, f, sr)
    times, freqs, mags = spectral.stft(
        samples, frame_size=frame_size, sample_rate=sr
    )
    nbins = frame_size // 2 + 1
    assert len(freqs) == nbins == 33
    # expected number of frames given default hop = frame_size // 2
    hop = frame_size // 2
    last_start = len(samples) - frame_size
    num_frames = last_start // hop + 1
    assert len(times) == num_frames
    assert len(mags) == num_frames
    for frame in mags:
        assert len(frame) == nbins
    # times strictly increasing
    for i in range(1, len(times)):
        assert times[i] > times[i - 1]
    assert times[0] == 0.0
    # peak bin of each frame maps to ~16 Hz
    for frame in mags:
        peak = max(range(nbins), key=lambda k: frame[k])
        assert freqs[peak] == pytest.approx(f, abs=sr / frame_size)


def test_stft_errors():
    samples = _sine(128, 16.0, 256.0)
    with pytest.raises(spectral.SpectralError):
        spectral.stft(samples, frame_size=1)
    with pytest.raises(spectral.SpectralError):
        spectral.stft(samples, frame_size=64, hop=0)
    with pytest.raises(spectral.SpectralError):
        spectral.stft(samples, frame_size=64, window="bogus")
    with pytest.raises(spectral.SpectralError):
        spectral.stft([1.0, 2.0, 3.0], frame_size=64)


# --- spectrogram -----------------------------------------------------------


def test_spectrogram_shape_and_db():
    sr = 256.0
    f = 16.0
    frame_size = 64
    samples = _sine(512, f, sr)
    s_times, s_freqs, s_mags = spectral.stft(
        samples, frame_size=frame_size, sample_rate=sr
    )
    times, freqs, db = spectral.spectrogram(
        samples, frame_size=frame_size, sample_rate=sr
    )
    assert times == s_times
    assert freqs == s_freqs
    assert len(db) == len(s_mags)
    nbins = frame_size // 2 + 1
    for frame in db:
        assert len(frame) == nbins
        for v in frame:
            assert math.isfinite(v)
    # peak bin towers over the noise floor
    frame0 = db[0]
    peak_bin = max(range(nbins), key=lambda k: frame0[k])
    floor = sorted(frame0)[0]
    assert frame0[peak_bin] - floor > 40.0


def test_spectrogram_errors():
    with pytest.raises(spectral.SpectralError):
        spectral.spectrogram([1.0, 2.0], frame_size=64)


# --- welch_psd -------------------------------------------------------------


def test_welch_psd_real_peak_and_shape():
    sr = 256.0
    f = 40.0
    samples = _sine(2048, f, sr)
    freqs, psd = spectral.welch_psd(samples, sample_rate=sr, nperseg=256)
    # one-sided: 0 .. Nyquist inclusive
    assert len(freqs) == 256 // 2 + 1
    assert len(psd) == len(freqs)
    assert freqs[0] == 0.0
    assert abs(freqs[-1] - sr / 2) < 1e-9
    assert all(p >= 0.0 for p in psd)
    # the estimate peaks at the tone's bin
    peak = max(range(len(psd)), key=lambda k: psd[k])
    assert abs(freqs[peak] - f) <= sr / 256  # within one bin


def test_welch_psd_complex_is_two_sided_and_sorted():
    sr = 1000.0
    f = 125.0  # a positive-frequency-only complex exponential
    samples = [complex(math.cos(2 * math.pi * f * n / sr),
                       math.sin(2 * math.pi * f * n / sr)) for n in range(2048)]
    freqs, psd = spectral.welch_psd(samples, sample_rate=sr, nperseg=256)
    assert len(freqs) == 256                      # full two-sided spectrum
    assert freqs == sorted(freqs)                 # monotonic -fs/2 .. +fs/2
    assert freqs[0] < 0 < freqs[-1]
    peak = max(range(len(psd)), key=lambda k: psd[k])
    assert abs(freqs[peak] - f) <= sr / 256       # energy on the +f side only
    # the mirror (-f) bin is far weaker for an analytic signal
    neg = min(range(len(freqs)), key=lambda k: abs(freqs[k] + f))
    assert psd[neg] < psd[peak] / 10


def test_welch_psd_validates():
    with pytest.raises(spectral.SpectralError):
        spectral.welch_psd([1.0], sample_rate=1.0)
    with pytest.raises(spectral.SpectralError):
        spectral.welch_psd([1.0, 2.0, 3.0], sample_rate=0.0)
    with pytest.raises(spectral.SpectralError):
        spectral.welch_psd([1.0, 2.0, 3.0], overlap=1.0)
