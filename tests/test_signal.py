"""Tests for abax.core.science.signal (no-numpy signal/data-processing module)."""

from __future__ import annotations

import math

import pytest

from abax.core.science.signal import (
    SignalError,
    apply_window,
    autocorrelation,
    blackman,
    cumulative_sum,
    detrend,
    diff,
    exponential_smoothing,
    hamming,
    hann,
    moving_average,
    normalize,
    rms,
)


def test_moving_average_centred_same_length():
    out = moving_average([1, 2, 3, 4, 5], 3)
    assert len(out) == 5
    assert out[1:4] == pytest.approx([2.0, 3.0, 4.0])
    assert out[0] == pytest.approx(1.5)
    assert out[-1] == pytest.approx(4.5)


def test_moving_average_errors():
    with pytest.raises(SignalError):
        moving_average([1, 2, 3], 0)
    with pytest.raises(SignalError):
        moving_average([], 3)


def test_exponential_smoothing_constant():
    assert exponential_smoothing([1, 1, 1], 0.5) == pytest.approx([1.0, 1.0, 1.0])


def test_exponential_smoothing_errors():
    with pytest.raises(SignalError):
        exponential_smoothing([1, 2, 3], 0.0)
    with pytest.raises(SignalError):
        exponential_smoothing([1, 2, 3], 1.5)
    with pytest.raises(SignalError):
        exponential_smoothing([], 0.5)


def test_cumulative_sum():
    assert cumulative_sum([1, 2, 3]) == pytest.approx([1.0, 3.0, 6.0])


def test_diff():
    assert diff([1, 4, 9]) == pytest.approx([3.0, 5.0])
    with pytest.raises(SignalError):
        diff([1])


def test_windows():
    assert hann(1) == [1.0]
    w = hann(4)
    assert len(w) == 4
    assert w == pytest.approx(list(reversed(w)))  # symmetric
    assert w[0] == pytest.approx(0.0)
    assert w[-1] == pytest.approx(0.0)
    assert len(hamming(8)) == 8
    assert len(blackman(5)) == 5
    assert hamming(1) == [1.0]
    assert blackman(1) == [1.0]


def test_apply_window():
    out = apply_window([1.0, 1.0, 1.0, 1.0], "hann")
    assert out == pytest.approx([x * w for x, w in zip([1, 1, 1, 1], hann(4))])
    with pytest.raises(SignalError):
        apply_window([1, 2, 3], "nope")
    with pytest.raises(SignalError):
        apply_window([], "hann")


def test_normalize_minmax():
    assert normalize([0, 5, 10], "minmax") == pytest.approx([0.0, 0.5, 1.0])


def test_normalize_zscore():
    out = normalize([1, 2, 3, 4, 5], "zscore")
    mu = math.fsum(out) / len(out)
    var = math.fsum((v - mu) ** 2 for v in out) / len(out)
    assert mu == pytest.approx(0.0)
    assert math.sqrt(var) == pytest.approx(1.0)


def test_normalize_peak():
    assert normalize([-2, 1], "peak") == pytest.approx([-1.0, 0.5])


def test_normalize_errors():
    with pytest.raises(SignalError):
        normalize([3, 3, 3], "minmax")
    with pytest.raises(SignalError):
        normalize([3, 3, 3], "zscore")
    with pytest.raises(SignalError):
        normalize([0, 0, 0], "peak")
    with pytest.raises(SignalError):
        normalize([1, 2, 3], "bogus")
    with pytest.raises(SignalError):
        normalize([], "minmax")


def test_detrend():
    out = detrend([1, 2, 3, 4])
    assert out == pytest.approx([0.0, 0.0, 0.0, 0.0])
    with pytest.raises(SignalError):
        detrend([])


def test_rms():
    assert rms([3, 4]) == pytest.approx(3.5355339, abs=1e-6)
    assert rms([3, 4]) == pytest.approx(math.sqrt(12.5))
    with pytest.raises(SignalError):
        rms([])


def test_autocorrelation():
    r = autocorrelation([1, 2, 1, 2, 1, 2])
    assert r[0] == pytest.approx(1.0)
    assert r[2] > 0.5  # lag-2 highly correlated
    assert r[1] < 0.0  # lag-1 anti-correlated
    with pytest.raises(SignalError):
        autocorrelation([5, 5, 5])
    with pytest.raises(SignalError):
        autocorrelation([])
