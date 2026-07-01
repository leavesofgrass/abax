"""Pure-Python signal and data-processing routines (no numpy).

A small, dependency-free toolkit of one-dimensional signal/data operations for
use inside abax. Everything works on plain ``list[float]`` in IEEE doubles via
the stdlib :mod:`math` module only; sequence outputs are always plain lists.

Smoothing/cumulative: :func:`moving_average` (centred, shrinking-window edges),
:func:`exponential_smoothing` (EWMA), :func:`cumulative_sum`, :func:`diff`.
Windowing: :func:`hann`, :func:`hamming`, :func:`blackman` coefficient windows
and :func:`apply_window` to multiply a signal by a named window. Scaling/shape:
:func:`normalize` (minmax/zscore/peak), :func:`detrend` (remove best-fit linear
trend). Statistics: :func:`rms`, :func:`autocorrelation`.

Every routine raises :class:`SignalError` rather than returning a bogus result
when its arguments are invalid (empty input, bad window size, out-of-range
parameters, zero range/variance, unknown mode/name).

NOTE: this module is ``abax.core.science.signal`` -- a package submodule, so it does
not shadow the stdlib :mod:`signal` module. Nothing here imports ``signal``.
"""

from __future__ import annotations

import math


class SignalError(Exception):
    """Raised when a signal routine cannot produce a valid result."""


def _mean(xs: list[float]) -> float:
    """Arithmetic mean of a non-empty sequence."""
    return math.fsum(xs) / len(xs)


def _variance(xs: list[float], mu: float) -> float:
    """Population variance of ``xs`` about the given mean ``mu``."""
    return math.fsum((x - mu) ** 2 for x in xs) / len(xs)


def moving_average(xs: list[float], window: int) -> list[float]:
    """Centred moving average of ``xs``, the SAME length as ``xs``.

    ``window`` must be at least 1 (an odd window is preferred so the average is
    truly centred). At the edges the window shrinks to the available samples.
    Raises :class:`SignalError` if ``window < 1`` or ``xs`` is empty.
    """
    if window < 1:
        raise SignalError("window must be at least 1")
    if not xs:
        raise SignalError("xs must be non-empty")
    n = len(xs)
    half = window // 2
    out: list[float] = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        chunk = xs[lo:hi]
        out.append(math.fsum(chunk) / len(chunk))
    return out


def exponential_smoothing(xs: list[float], alpha: float) -> list[float]:
    """Exponentially weighted moving average of ``xs``, same length.

    ``s[0] = xs[0]`` and ``s[i] = alpha*xs[i] + (1-alpha)*s[i-1]``. Raises
    :class:`SignalError` if ``alpha`` is not in ``(0, 1]`` or ``xs`` is empty.
    """
    if not xs:
        raise SignalError("xs must be non-empty")
    if not (0.0 < alpha <= 1.0):
        raise SignalError("alpha must be in (0, 1]")
    out: list[float] = [float(xs[0])]
    for i in range(1, len(xs)):
        out.append(alpha * xs[i] + (1.0 - alpha) * out[i - 1])
    return out


def cumulative_sum(xs: list[float]) -> list[float]:
    """Running total of ``xs``, same length. Raises if ``xs`` is empty."""
    if not xs:
        raise SignalError("xs must be non-empty")
    out: list[float] = []
    total = 0.0
    for x in xs:
        total += x
        out.append(total)
    return out


def diff(xs: list[float]) -> list[float]:
    """Successive differences of ``xs`` (length ``n-1``).

    Raises :class:`SignalError` if ``xs`` has fewer than two elements.
    """
    if len(xs) < 2:
        raise SignalError("diff needs at least two elements")
    return [xs[i] - xs[i - 1] for i in range(1, len(xs))]


def hann(n: int) -> list[float]:
    """Hann window coefficients of length ``n``.

    ``w[k] = 0.5 - 0.5*cos(2*pi*k/(n-1))``. ``n == 1`` returns ``[1.0]``.
    Raises :class:`SignalError` for ``n < 1``.
    """
    if n < 1:
        raise SignalError("window length must be at least 1")
    if n == 1:
        return [1.0]
    return [0.5 - 0.5 * math.cos(2.0 * math.pi * k / (n - 1)) for k in range(n)]


def hamming(n: int) -> list[float]:
    """Hamming window coefficients of length ``n``.

    ``w[k] = 0.54 - 0.46*cos(2*pi*k/(n-1))``. ``n == 1`` returns ``[1.0]``.
    Raises :class:`SignalError` for ``n < 1``.
    """
    if n < 1:
        raise SignalError("window length must be at least 1")
    if n == 1:
        return [1.0]
    return [0.54 - 0.46 * math.cos(2.0 * math.pi * k / (n - 1)) for k in range(n)]


def blackman(n: int) -> list[float]:
    """Blackman window coefficients of length ``n``.

    ``w[k] = 0.42 - 0.5*cos(2*pi*k/(n-1)) + 0.08*cos(4*pi*k/(n-1))``.
    ``n == 1`` returns ``[1.0]``. Raises :class:`SignalError` for ``n < 1``.
    """
    if n < 1:
        raise SignalError("window length must be at least 1")
    if n == 1:
        return [1.0]
    return [
        0.42
        - 0.5 * math.cos(2.0 * math.pi * k / (n - 1))
        + 0.08 * math.cos(4.0 * math.pi * k / (n - 1))
        for k in range(n)
    ]


_WINDOWS = {"hann": hann, "hamming": hamming, "blackman": blackman}


def apply_window(xs: list[float], name: str) -> list[float]:
    """Multiply ``xs`` elementwise by the named window.

    ``name`` is one of ``"hann"``, ``"hamming"`` or ``"blackman"``; a window of
    length ``len(xs)`` is built and applied. Raises :class:`SignalError` on an
    unknown window name or empty input.
    """
    if not xs:
        raise SignalError("xs must be non-empty")
    builder = _WINDOWS.get(name)
    if builder is None:
        raise SignalError(f"unknown window: {name!r}")
    win = builder(len(xs))
    return [x * w for x, w in zip(xs, win)]


def normalize(xs: list[float], mode: str = "minmax") -> list[float]:
    """Normalise ``xs`` according to ``mode``, same length.

    - ``"minmax"`` scales linearly to ``[0, 1]``.
    - ``"zscore"`` centres to zero mean and scales to unit (population) stdev.
    - ``"peak"`` divides by ``max(abs(x))``.

    Raises :class:`SignalError` for an unknown mode, empty input, or a degenerate
    range (zero min-max range, zero stdev, or all-zero input for ``"peak"``).
    """
    if not xs:
        raise SignalError("xs must be non-empty")
    if mode == "minmax":
        lo = min(xs)
        hi = max(xs)
        rng = hi - lo
        if rng == 0.0:
            raise SignalError("cannot minmax-normalize a zero-range signal")
        return [(x - lo) / rng for x in xs]
    if mode == "zscore":
        mu = _mean(xs)
        sd = math.sqrt(_variance(xs, mu))
        if sd == 0.0:
            raise SignalError("cannot zscore-normalize a zero-stdev signal")
        return [(x - mu) / sd for x in xs]
    if mode == "peak":
        peak = max(abs(x) for x in xs)
        if peak == 0.0:
            raise SignalError("cannot peak-normalize an all-zero signal")
        return [x / peak for x in xs]
    raise SignalError(f"unknown normalize mode: {mode!r}")


def detrend(xs: list[float]) -> list[float]:
    """Remove the best-fit linear trend from ``xs`` (same length).

    A least-squares line is fitted over indices ``0..n-1`` and subtracted.
    Raises :class:`SignalError` if ``xs`` is empty.
    """
    if not xs:
        raise SignalError("xs must be non-empty")
    n = len(xs)
    if n == 1:
        return [0.0]
    mean_x = (n - 1) / 2.0
    mean_y = _mean(xs)
    sxx = math.fsum((i - mean_x) ** 2 for i in range(n))
    sxy = math.fsum((i - mean_x) * (xs[i] - mean_y) for i in range(n))
    slope = sxy / sxx if sxx != 0.0 else 0.0
    intercept = mean_y - slope * mean_x
    return [xs[i] - (slope * i + intercept) for i in range(n)]


def rms(xs: list[float]) -> float:
    """Root-mean-square of ``xs``. Raises :class:`SignalError` if empty."""
    if not xs:
        raise SignalError("xs must be non-empty")
    return math.sqrt(math.fsum(x * x for x in xs) / len(xs))


def autocorrelation(xs: list[float]) -> list[float]:
    """Normalised autocorrelation of ``xs`` for lags ``0..n-1`` (length ``n``).

    The mean is subtracted first; ``r[lag] = sum(x[i]*x[i+lag]) / sum(x[i]^2)``
    so that ``r[0] == 1.0`` for any non-constant input. Raises
    :class:`SignalError` if ``xs`` is empty or has zero variance.
    """
    if not xs:
        raise SignalError("xs must be non-empty")
    n = len(xs)
    mu = _mean(xs)
    centred = [x - mu for x in xs]
    denom = math.fsum(c * c for c in centred)
    if denom == 0.0:
        raise SignalError("cannot autocorrelate a constant signal")
    out: list[float] = []
    for lag in range(n):
        acc = math.fsum(centred[i] * centred[i + lag] for i in range(n - lag))
        out.append(acc / denom)
    return out
