"""Pure-Python FFT and spectral analysis: no numpy, stdlib only.

A small, dependency-free toolkit for discrete spectral analysis inside abax.
Everything works in Python :class:`complex` via the stdlib :mod:`math` and
:mod:`cmath` modules only — no numpy, no third-party code (abax ``core`` is
stdlib-only).

Transforms: :func:`dft` (direct O(n^2) DFT, any length), :func:`fft`
(Cooley-Tukey radix-2 decimation-in-time when the length is a power of two,
falling back to :func:`dft` otherwise), and :func:`ifft` (inverse transform via
the conjugate trick with ``1/n`` scaling).

Spectral helpers: :func:`magnitude`, :func:`phase`, :func:`power_spectrum`,
:func:`frequencies` (bin centre frequencies), and :func:`rfft_magnitude` (the
one-sided magnitude spectrum of a real signal, ready to plot against Hz).

Convolution: :func:`convolve` (direct linear convolution).

Bad arguments (empty input) raise :class:`FFTError` rather than returning a
bogus result.
"""

from __future__ import annotations

import cmath
import math


class FFTError(Exception):
    """Raised when a spectral routine cannot produce a valid result."""


def dft(samples: list[complex]) -> list[complex]:
    """Direct O(n^2) discrete Fourier transform for any length ``n >= 1``.

    Accepts real or complex input; returns ``n`` complex bins where
    ``X_k = sum_j x_j * exp(-2*pi*i*j*k/n)``.
    """
    n = len(samples)
    if n == 0:
        raise FFTError("dft of empty input")
    out: list[complex] = []
    for k in range(n):
        acc = 0j
        for j, x in enumerate(samples):
            acc += complex(x) * cmath.exp(-2j * math.pi * j * k / n)
        out.append(acc)
    return out


def fft(samples: list[complex]) -> list[complex]:
    """Fast Fourier transform.

    Uses recursive radix-2 Cooley-Tukey decimation-in-time when ``len(samples)``
    is a power of two; otherwise falls back to :func:`dft`. Raises
    :class:`FFTError` on empty input.
    """
    n = len(samples)
    if n == 0:
        raise FFTError("fft of empty input")
    if n & (n - 1) != 0:
        return dft(samples)
    return _fft_radix2([complex(x) for x in samples])


def _fft_radix2(x: list[complex]) -> list[complex]:
    """Recursive radix-2 DIT FFT; ``len(x)`` must be a power of two."""
    n = len(x)
    if n == 1:
        return [x[0]]
    even = _fft_radix2(x[0::2])
    odd = _fft_radix2(x[1::2])
    out: list[complex] = [0j] * n
    half = n // 2
    for k in range(half):
        twiddle = cmath.exp(-2j * math.pi * k / n) * odd[k]
        out[k] = even[k] + twiddle
        out[k + half] = even[k] - twiddle
    return out


def ifft(spectrum: list[complex]) -> list[complex]:
    """Inverse transform such that ``ifft(fft(x)) ~= x``.

    Implemented with the conjugate trick: conjugate the input, run :func:`fft`,
    conjugate the result, and divide by ``n``. Raises :class:`FFTError` on empty
    input.
    """
    n = len(spectrum)
    if n == 0:
        raise FFTError("ifft of empty input")
    conj = [complex(c).conjugate() for c in spectrum]
    transformed = fft(conj)
    return [c.conjugate() / n for c in transformed]


def magnitude(spectrum: list[complex]) -> list[float]:
    """Return ``abs(X_k)`` for each bin."""
    return [abs(complex(c)) for c in spectrum]


def phase(spectrum: list[complex]) -> list[float]:
    """Return the phase angle in radians (:func:`cmath.phase`) of each bin."""
    return [cmath.phase(complex(c)) for c in spectrum]


def power_spectrum(spectrum: list[complex]) -> list[float]:
    """Return ``|X_k|^2 / n`` for each bin."""
    n = len(spectrum)
    if n == 0:
        raise FFTError("power_spectrum of empty input")
    return [abs(complex(c)) ** 2 / n for c in spectrum]


def frequencies(n: int, sample_rate: float = 1.0) -> list[float]:
    """Bin centre frequencies of an ``n``-point transform: ``k*sample_rate/n``."""
    if n <= 0:
        raise FFTError("frequencies requires n >= 1")
    return [k * sample_rate / n for k in range(n)]


def rfft_magnitude(
    samples: list[float], sample_rate: float = 1.0
) -> tuple[list[float], list[float]]:
    """One-sided magnitude spectrum of a real signal.

    Returns ``(freqs, mags)`` for bins ``0 .. n//2`` inclusive, where
    ``freqs[k] = k*sample_rate/n`` and ``mags[k] = abs(X_k)``. Suitable for
    plotting magnitude against Hz. Raises :class:`FFTError` on empty input.
    """
    n = len(samples)
    if n == 0:
        raise FFTError("rfft_magnitude of empty input")
    spectrum = fft([complex(x) for x in samples])
    half = n // 2
    freqs = [k * sample_rate / n for k in range(half + 1)]
    mags = [abs(spectrum[k]) for k in range(half + 1)]
    return freqs, mags


def convolve(a: list[float], b: list[float]) -> list[float]:
    """Linear convolution of ``a`` and ``b`` (direct sum).

    Returns a list of length ``len(a) + len(b) - 1``. Raises :class:`FFTError`
    if either input is empty.
    """
    if not a or not b:
        raise FFTError("convolve of empty input")
    na, nb = len(a), len(b)
    out = [0.0] * (na + nb - 1)
    for i, ai in enumerate(a):
        for j, bj in enumerate(b):
            out[i + j] += ai * bj
    return out
