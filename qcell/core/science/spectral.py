"""Spectral analysis: STFT / spectrogram and FFT-based fast convolution.

A small, dependency-free extension of qcell's spectral toolkit built on top of
:mod:`qcell.core.science.fft` (transforms) and :mod:`qcell.core.science.signal` (windows).
Everything works on plain ``list[float]`` in IEEE doubles via the stdlib
:mod:`math` and :mod:`cmath` modules only -- no numpy, no third-party code
(qcell ``core`` is stdlib-only).

Time-frequency: :func:`stft` (short-time Fourier transform -- a sequence of
one-sided magnitude spectra over sliding, windowed frames) and
:func:`spectrogram` (the same surface expressed as power in dB).

Convolution: :func:`fft_convolve` (linear convolution of two real signals via
the FFT, matching :func:`qcell.core.science.fft.convolve` numerically).

Helper: :func:`next_pow2` (smallest power of two ``>= n``).

Bad arguments raise :class:`SpectralError` rather than returning a bogus result.
"""

from __future__ import annotations

import math

from qcell.core.science import fft as _fft
from qcell.core.science import signal as _signal


class SpectralError(Exception):
    """Raised when a spectral routine cannot produce a valid result."""


def next_pow2(n: int) -> int:
    """Smallest power of two ``>= n`` (with a floor of 1).

    ``next_pow2(1) == 1``, ``next_pow2(5) == 8``, ``next_pow2(8) == 8``. Raises
    :class:`SpectralError` for ``n < 1``.
    """
    if n < 1:
        raise SpectralError("next_pow2 requires n >= 1")
    p = 1
    while p < n:
        p <<= 1
    return p


def _onesided_magnitude(frame: list[float]) -> list[float]:
    """One-sided magnitude spectrum (bins ``0 .. len(frame)//2``) of a frame."""
    spectrum = _fft.fft([complex(x) for x in frame])
    half = len(frame) // 2
    return [abs(spectrum[k]) for k in range(half + 1)]


def stft(
    samples: list[float],
    frame_size: int = 256,
    hop: int | None = None,
    window: str = "hann",
    sample_rate: float = 1.0,
) -> tuple[list[float], list[float], list[list[float]]]:
    """Short-time Fourier transform of a real signal.

    Slide a window of ``frame_size`` over ``samples`` stepping by ``hop`` (which
    defaults to ``frame_size // 2``); window each frame with the named window
    (:func:`qcell.core.science.signal.apply_window`) and take the one-sided magnitude
    spectrum (``frame_size // 2 + 1`` bins).

    Returns ``(times, freqs, mags)`` where ``times[i]`` is the start of frame
    ``i`` in seconds (``frame_start_i / sample_rate``), ``freqs`` are the
    one-sided bin-centre frequencies in Hz (length ``frame_size // 2 + 1``), and
    ``mags`` is one magnitude list per frame (each of length ``len(freqs)``).
    Frames that run past the end of ``samples`` are zero-padded.

    Raises :class:`SpectralError` if ``frame_size < 2``, ``hop < 1``, the window
    name is unknown, or there are fewer than ``frame_size`` samples in total.
    """
    if frame_size < 2:
        raise SpectralError("frame_size must be at least 2")
    if hop is None:
        hop = frame_size // 2
    if hop < 1:
        raise SpectralError("hop must be at least 1")
    if window not in _signal._WINDOWS:
        raise SpectralError(f"unknown window: {window!r}")
    n = len(samples)
    if n < frame_size:
        raise SpectralError("need at least frame_size samples")

    half = frame_size // 2
    freqs = [k * sample_rate / frame_size for k in range(half + 1)]
    last_start = n - frame_size
    times: list[float] = []
    mags: list[list[float]] = []
    start = 0
    while start <= last_start:
        frame = list(samples[start : start + frame_size])
        if len(frame) < frame_size:
            frame.extend([0.0] * (frame_size - len(frame)))
        windowed = _signal.apply_window(frame, window)
        mags.append(_onesided_magnitude(windowed))
        times.append(start / sample_rate)
        start += hop
    return times, freqs, mags


def spectrogram(
    samples: list[float],
    frame_size: int = 256,
    hop: int | None = None,
    window: str = "hann",
    sample_rate: float = 1.0,
) -> tuple[list[float], list[float], list[list[float]]]:
    """Power spectrogram: like :func:`stft` but values are power in decibels.

    Returns ``(times, freqs, mags)`` with the same shape and meaning as
    :func:`stft`, except each magnitude ``m`` is converted to
    ``20 * log10(m + 1e-12)`` decibels (the ``1e-12`` floor keeps zero
    magnitudes finite). Argument validation matches :func:`stft`.
    """
    times, freqs, mags = stft(
        samples, frame_size=frame_size, hop=hop, window=window, sample_rate=sample_rate
    )
    db = [[20.0 * math.log10(m + 1e-12) for m in frame] for frame in mags]
    return times, freqs, db


def fft_convolve(a: list[float], b: list[float]) -> list[float]:
    """Linear convolution of two real lists via the FFT.

    Both inputs are zero-padded to ``next_pow2(len(a) + len(b) - 1)``,
    transformed, multiplied pointwise, inverse-transformed, and the real parts
    are taken and truncated to ``len(a) + len(b) - 1``. The result matches
    :func:`qcell.core.science.fft.convolve` numerically. Raises :class:`SpectralError`
    if either input is empty.
    """
    if not a or not b:
        raise SpectralError("fft_convolve of empty input")
    out_len = len(a) + len(b) - 1
    size = next_pow2(out_len)
    pa = [complex(x) for x in a] + [0j] * (size - len(a))
    pb = [complex(x) for x in b] + [0j] * (size - len(b))
    fa = _fft.fft(pa)
    fb = _fft.fft(pb)
    product = [fa[k] * fb[k] for k in range(size)]
    inverse = _fft.ifft(product)
    return [inverse[k].real for k in range(out_len)]


def welch_psd(
    samples,
    sample_rate: float = 1.0,
    nperseg: int = 256,
    overlap: float = 0.5,
) -> tuple[list[float], list[float]]:
    """Power spectral density by Welch's method (averaged windowed periodograms).

    The signal is split into Hann-windowed segments of ``nperseg`` samples that
    overlap by ``overlap`` (0..1, default 50%); each segment's periodogram is
    averaged. Returns ``(freqs, psd)`` with the density scaled as ``|X|^2 /
    (fs * sum(win^2))`` (the SciPy ``scaling="density"`` convention).

    Real input yields a **one-sided** PSD over ``0 .. fs/2`` (interior bins
    doubled to conserve power). Complex (I/Q) input yields a **two-sided** PSD
    sorted monotonically over ``-fs/2 .. +fs/2`` -- the natural view for a
    quadrature-sampled radio signal where positive and negative offsets differ.

    ``nperseg`` is clamped to ``len(samples)``. Raises :class:`SpectralError`
    for fewer than two samples, a non-positive ``sample_rate``, or ``overlap``
    outside ``[0, 1)``.
    """
    n = len(samples)
    if n < 2:
        raise SpectralError("welch_psd needs at least two samples")
    if sample_rate <= 0:
        raise SpectralError("welch_psd requires sample_rate > 0")
    if not 0.0 <= overlap < 1.0:
        raise SpectralError("welch_psd overlap must be in [0, 1)")

    nperseg = max(2, min(int(nperseg), n))
    step = max(1, int(round(nperseg * (1.0 - overlap))))
    win = _signal.hann(nperseg)
    winpow = sum(w * w for w in win) or 1.0
    is_complex = any(isinstance(s, complex) for s in samples)

    acc = [0.0] * nperseg
    count = 0
    start = 0
    while start + nperseg <= n:
        seg = samples[start:start + nperseg]
        windowed = [complex(seg[i]) * win[i] for i in range(nperseg)]
        spec = _fft.fft(windowed)
        for k in range(nperseg):
            mag = abs(spec[k])
            acc[k] += mag * mag
        count += 1
        start += step

    denom = count * winpow * sample_rate
    psd = [a / denom for a in acc]
    df = sample_rate / nperseg

    if is_complex:
        # Two-sided, wrapped to negative frequencies and sorted ascending.
        freqs = [k * df if k <= nperseg // 2 else (k - nperseg) * df
                 for k in range(nperseg)]
        pairs = sorted(zip(freqs, psd))
        return ([f for f, _ in pairs], [p for _, p in pairs])

    # One-sided: bins 0..Nyquist, interior bins doubled to conserve power.
    half = nperseg // 2 + 1
    out = []
    for k in range(half):
        p = psd[k]
        if 0 < k < nperseg - k:
            p *= 2.0
        out.append(p)
    return ([k * df for k in range(half)], out)
