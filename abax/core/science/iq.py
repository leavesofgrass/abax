"""I/Q (complex baseband) analysis for abax's DSP/RF toolkit.

A small, dependency-free set of routines for inspecting quadrature-sampled
(complex baseband) signals, where each sample is a Python ``complex`` carrying
the in-phase component in ``.real`` and the quadrature component in ``.imag``
(``I + jQ``). Everything runs on the stdlib :mod:`math` module only -- no numpy,
no third-party code (abax ``core`` is stdlib-only).

Contents:

* :func:`constellation_points` -- unpack samples into ``(I, Q)`` pairs, the
  natural form for scatter-plotting a constellation diagram.
* :func:`eye_diagram` -- slice the real part into overlapping two-symbol
  traces for an eye diagram.
* :func:`evm` -- error-vector-magnitude percentage against a reference.
* :func:`power_dbfs` -- average signal power in dBFS (magnitude 1.0 = 0 dBFS).

Bad arguments raise :class:`ValueError` rather than returning a bogus result.
"""

from __future__ import annotations

import math

_DBFS_FLOOR = -300.0


def constellation_points(samples) -> list[tuple[float, float]]:
    """Unpack complex baseband ``samples`` into ``(I, Q)`` pairs.

    Returns ``[(z.real, z.imag) for z in samples]`` -- the in-phase / quadrature
    coordinates used to scatter-plot a constellation diagram.
    """
    return [(z.real, z.imag) for z in samples]


def eye_diagram(samples, samples_per_symbol: int) -> list[list[float]]:
    """Slice the real part of ``samples`` into overlapping eye-diagram traces.

    Take the real part of each sample and cut it into windows of length
    ``2 * samples_per_symbol`` (a two-symbol span), stepping by
    ``samples_per_symbol`` so that consecutive two-symbol eyes overlap by one
    symbol. A trailing partial window (shorter than ``2 * samples_per_symbol``)
    is dropped. Returns the list of traces, each a ``list[float]`` of length
    ``2 * samples_per_symbol``.

    Raises :class:`ValueError` if ``samples_per_symbol < 1``.
    """
    if samples_per_symbol < 1:
        raise ValueError("samples_per_symbol must be at least 1")
    reals = [z.real for z in samples]
    window = 2 * samples_per_symbol
    step = samples_per_symbol
    traces: list[list[float]] = []
    start = 0
    while start + window <= len(reals):
        traces.append(reals[start : start + window])
        start += step
    return traces


def evm(measured, reference) -> float:
    """Error-vector-magnitude (EVM) percentage between two complex sequences.

    Computes ``sqrt(mean(|meas - ref|^2) / mean(|ref|^2)) * 100`` -- the RMS
    error vector normalised by the RMS reference magnitude, expressed as a
    percentage. ``measured`` and ``reference`` must be equal-length sequences of
    ``complex`` (real values are accepted and treated as ``I + 0j``).

    Raises :class:`ValueError` if the lengths differ, if the inputs are empty,
    or if the reference has zero average power (which would divide by zero).
    """
    if len(measured) != len(reference):
        raise ValueError("measured and reference must have equal length")
    n = len(reference)
    if n == 0:
        raise ValueError("evm requires a non-empty reference")
    err_power = 0.0
    ref_power = 0.0
    for m, r in zip(measured, reference):
        m = complex(m)
        r = complex(r)
        diff = m - r
        err_power += diff.real * diff.real + diff.imag * diff.imag
        ref_power += r.real * r.real + r.imag * r.imag
    if ref_power == 0.0:
        raise ValueError("evm requires a reference with non-zero power")
    return math.sqrt((err_power / n) / (ref_power / n)) * 100.0


def power_dbfs(samples) -> float:
    """Average power of ``samples`` in dBFS (magnitude 1.0 == 0 dBFS).

    Computes ``10 * log10(mean(|z|^2))`` where a sample of magnitude ``1.0``
    corresponds to full scale (0 dBFS). For all-zero (or empty) input the power
    is zero and the logarithm is undefined, so a finite floor of ``-300.0`` dBFS
    is returned instead of ``-inf``.
    """
    n = len(samples)
    if n == 0:
        return _DBFS_FLOOR
    total = 0.0
    for z in samples:
        z = complex(z)
        total += z.real * z.real + z.imag * z.imag
    mean_power = total / n
    if mean_power <= 0.0:
        return _DBFS_FLOOR
    return 10.0 * math.log10(mean_power)
