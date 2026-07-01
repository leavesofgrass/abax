"""Tests for the STFT analysis/resynthesis module (:mod:`abax.core.science.resynth`)."""

from __future__ import annotations

import math

import pytest

from abax.core.science import fft, resynth


def _tone(n: int = 512, freq: float = 5.0, period: float = 128.0) -> list[float]:
    """A simple sine tone for round-trip tests."""
    return [math.sin(2.0 * math.pi * freq * k / period) for k in range(n)]


def _mean_mag_error(
    a: list[list[float]], b: list[list[float]]
) -> float:
    """Mean absolute magnitude error between two equal-shaped frame lists."""
    total = 0.0
    count = 0
    for fa, fb in zip(a, b):
        for va, vb in zip(fa, fb):
            total += abs(va - vb)
            count += 1
    return total / count if count else 0.0


def test_stft_frame_shape_and_count():
    x = _tone(512)
    frames = resynth.stft_complex(x, 128, 32, "hann")
    assert all(len(f) == 128 for f in frames)
    # slide count: floor((512-1)/32) + 1
    assert len(frames) == (512 - 1) // 32 + 1


def test_cola_round_trip_hann_interior():
    x = _tone(512)
    y = resynth.reconstruct(x, 128, 32, "hann")
    assert len(y) == 512
    for i in range(128, 384):
        assert y[i] == pytest.approx(x[i], abs=1e-6)


def test_istft_round_trip_hamming_interior():
    x = _tone(512)
    frames = resynth.stft_complex(x, 128, None, "hamming")  # hop = 128//4 = 32
    y = resynth.istft(frames, 128, None, "hamming", length=512)
    assert len(y) == 512
    for i in range(128, 384):
        assert y[i] == pytest.approx(x[i], abs=1e-6)


def test_griffin_lim_recovers_magnitude():
    x = _tone(512)
    mags = [fft.magnitude(f) for f in resynth.stft_complex(x, 128, 32)]

    y1 = resynth.griffin_lim(mags, 128, 32, iterations=1, length=512)
    y60 = resynth.griffin_lim(mags, 128, 32, iterations=60, length=512)
    assert len(y60) == 512

    mags1 = [fft.magnitude(f) for f in resynth.stft_complex(y1, 128, 32)]
    mags60 = [fft.magnitude(f) for f in resynth.stft_complex(y60, 128, 32)]

    err1 = _mean_mag_error(mags, mags1)
    err60 = _mean_mag_error(mags, mags60)

    # Griffin-Lim recovers magnitude (phase/sign may differ); 60 iterations
    # land much closer than 1, and the residual is small relative to the
    # signal's magnitude scale.
    assert err60 < err1
    assert err60 < 0.5 * err1
    assert err60 < 0.2


def test_griffin_lim_zero_phase_seed_default():
    x = _tone(256)
    mags = [fft.magnitude(f) for f in resynth.stft_complex(x, 64, 16)]
    y = resynth.griffin_lim(mags, 64, 16, iterations=20, length=256)
    assert len(y) == 256


def test_error_frame_size_too_small():
    with pytest.raises(resynth.ResynthError):
        resynth.stft_complex(_tone(64), 1, 1, "hann")


def test_error_hop_too_small():
    with pytest.raises(resynth.ResynthError):
        resynth.stft_complex(_tone(64), 16, 0, "hann")


def test_error_unknown_window():
    with pytest.raises(resynth.ResynthError):
        resynth.stft_complex(_tone(64), 16, 4, "nope")


def test_error_empty_frames():
    with pytest.raises(resynth.ResynthError):
        resynth.istft([], 16, 4, "hann")


def test_error_griffin_lim_empty():
    with pytest.raises(resynth.ResynthError):
        resynth.griffin_lim([], 16, 4)
