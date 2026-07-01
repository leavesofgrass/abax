"""Short-time Fourier transform analysis/resynthesis (pure stdlib).

A small, dependency-free STFT toolkit for abax ``core`` (stdlib only — no
numpy). It builds on :mod:`abax.core.science.fft` (FFT/IFFT/magnitude) and
:mod:`abax.core.science.signal` (analysis windows) to offer:

- :func:`stft_complex` — the full complex STFT: slide an analysis window over the
  signal, window each frame and FFT it into a length-``frame_size`` complex
  spectrum.
- :func:`istft` — inverse STFT by weighted overlap-add (WOLA) with COLA
  normalisation: IFFT each frame, re-apply the synthesis window, overlap-add, and
  divide by the overlap-added window-squared envelope.
- :func:`reconstruct` — analysis followed by synthesis; returns ``~= samples``
  for a COLA-satisfying window/hop.
- :func:`griffin_lim` — recover a real time-domain signal from magnitude-only
  spectra by alternating projection (Griffin & Lim, 1984).

Hops default to ``frame_size // 4`` everywhere. Phase is carried as a plain
list-of-lists of radians; complex frames are rebuilt via :func:`cmath.rect`.

Invalid arguments raise :class:`ResynthError` rather than returning a bogus
result.
"""

from __future__ import annotations

import cmath

from abax.core.science import fft
from abax.core.science.signal import _WINDOWS

#: Floor used when dividing by the COLA window-squared envelope (avoid /0).
_EPS = 1e-12


class ResynthError(Exception):
    """Raised when an STFT analysis/resynthesis routine cannot proceed."""


def _resolve_hop(frame_size: int, hop: int | None) -> int:
    """Return ``hop`` or the default ``frame_size // 4`` (at least 1)."""
    if hop is None:
        return max(1, frame_size // 4)
    return hop


def _window(frame_size: int, window: str) -> list[float]:
    """Build the named analysis/synthesis window of length ``frame_size``.

    Raises :class:`ResynthError` for an unknown window name.
    """
    builder = _WINDOWS.get(window)
    if builder is None:
        raise ResynthError(f"unknown window: {window!r}")
    return builder(frame_size)


def _n_frames(n_samples: int, frame_size: int, hop: int) -> int:
    """Number of frames produced when sliding over ``n_samples``.

    Counts every start position ``0, hop, 2*hop, ...`` for which at least one
    sample of the frame falls inside the signal, i.e. ``start < n_samples``.
    """
    if n_samples <= 0:
        return 0
    return (n_samples - 1) // hop + 1


def stft_complex(
    samples,
    frame_size: int = 256,
    hop: int | None = None,
    window: str = "hann",
) -> list[list[complex]]:
    """Full complex short-time Fourier transform of ``samples``.

    Slides an analysis window of ``frame_size`` over the signal in steps of
    ``hop`` (default ``frame_size // 4``), multiplies each frame by the window
    and FFTs it into a length-``frame_size`` complex spectrum. Tail frames are
    zero-padded. Returns the list of complex frames.

    Raises :class:`ResynthError` if ``frame_size < 2``, ``hop < 1``, the window
    name is unknown, or there are too few samples for a single frame's start.
    """
    if frame_size < 2:
        raise ResynthError("frame_size must be at least 2")
    hop = _resolve_hop(frame_size, hop)
    if hop < 1:
        raise ResynthError("hop must be at least 1")
    win = _window(frame_size, window)
    xs = [float(s) for s in samples]
    n = len(xs)
    if n < 1:
        raise ResynthError("too few samples for an STFT")
    n_frames = _n_frames(n, frame_size, hop)
    if n_frames < 1:
        raise ResynthError("too few samples for an STFT")
    frames: list[list[complex]] = []
    for f in range(n_frames):
        start = f * hop
        block: list[complex] = []
        for k in range(frame_size):
            idx = start + k
            value = xs[idx] if idx < n else 0.0
            block.append(complex(value * win[k]))
        frames.append(fft.fft(block))
    return frames


def istft(
    frames: list[list[complex]],
    frame_size: int = 256,
    hop: int | None = None,
    window: str = "hann",
    length: int | None = None,
) -> list[float]:
    """Inverse STFT by weighted overlap-add with COLA normalisation.

    For each frame: IFFT it, take real parts, multiply by the synthesis window,
    and overlap-add into the output. In parallel accumulate the window-squared
    envelope; the final output is the windowed-signal sum divided elementwise by
    that envelope (guarded against division by zero with a small epsilon). If
    ``length`` is given the result is trimmed or zero-padded to it.

    Raises :class:`ResynthError` on empty ``frames`` or bad arguments.
    """
    if frame_size < 2:
        raise ResynthError("frame_size must be at least 2")
    hop = _resolve_hop(frame_size, hop)
    if hop < 1:
        raise ResynthError("hop must be at least 1")
    if not frames:
        raise ResynthError("istft of empty frames")
    win = _window(frame_size, window)
    n_frames = len(frames)
    out_len = (n_frames - 1) * hop + frame_size
    acc = [0.0] * out_len
    env = [0.0] * out_len
    for f, spectrum in enumerate(frames):
        if len(spectrum) != frame_size:
            raise ResynthError(
                f"frame {f} has length {len(spectrum)}, expected {frame_size}"
            )
        time_frame = fft.ifft(spectrum)
        start = f * hop
        for k in range(frame_size):
            w = win[k]
            acc[start + k] += time_frame[k].real * w
            env[start + k] += w * w
    out = [acc[i] / (env[i] if env[i] > _EPS else _EPS) for i in range(out_len)]
    if length is not None:
        if length < 0:
            raise ResynthError("length must be non-negative")
        if length < out_len:
            out = out[:length]
        elif length > out_len:
            out = out + [0.0] * (length - out_len)
    return out


def reconstruct(
    samples,
    frame_size: int = 256,
    hop: int | None = None,
    window: str = "hann",
) -> list[float]:
    """Analysis then synthesis: ``istft(stft_complex(samples))``.

    Returns a signal ``~= samples`` (exactly so in the interior) for a window/hop
    pair that satisfies the constant-overlap-add (COLA) condition. The output is
    trimmed to ``len(samples)``. Raises :class:`ResynthError` on bad arguments.
    """
    xs = [float(s) for s in samples]
    frames = stft_complex(xs, frame_size, hop, window)
    return istft(frames, frame_size, hop, window, length=len(xs))


def griffin_lim(
    magnitudes: list[list[float]],
    frame_size: int = 256,
    hop: int | None = None,
    window: str = "hann",
    iterations: int = 50,
    length: int | None = None,
    seed_phase: list[list[float]] | None = None,
) -> list[float]:
    """Reconstruct a real signal from magnitude-only STFT frames.

    Implements the Griffin-Lim alternating projection: starting from zero phase
    (or ``seed_phase``), repeatedly synthesise a time-domain signal via
    :func:`istft`, re-analyse it with :func:`stft_complex`, and keep the new
    phase while restoring the target magnitudes. After ``iterations`` rounds the
    synthesised signal is returned.

    Each magnitude frame must have length ``frame_size``. ``length`` defaults
    from the frame layout. Raises :class:`ResynthError` on empty input or bad
    arguments.
    """
    if frame_size < 2:
        raise ResynthError("frame_size must be at least 2")
    hop = _resolve_hop(frame_size, hop)
    if hop < 1:
        raise ResynthError("hop must be at least 1")
    if not magnitudes:
        raise ResynthError("griffin_lim of empty magnitudes")
    if iterations < 1:
        raise ResynthError("iterations must be at least 1")
    _window(frame_size, window)  # validate the window name early
    mags = [[float(m) for m in frame] for frame in magnitudes]
    for f, frame in enumerate(mags):
        if len(frame) != frame_size:
            raise ResynthError(
                f"magnitude frame {f} has length {len(frame)}, expected {frame_size}"
            )
    n_frames = len(mags)
    if seed_phase is not None:
        if len(seed_phase) != n_frames:
            raise ResynthError("seed_phase frame count mismatch")
        phase = [[float(p) for p in frame] for frame in seed_phase]
        for frame in phase:
            if len(frame) != frame_size:
                raise ResynthError("seed_phase frame length mismatch")
    else:
        phase = [[0.0] * frame_size for _ in range(n_frames)]

    out_len = length if length is not None else (n_frames - 1) * hop + frame_size
    signal: list[float] = []
    for _ in range(iterations):
        frames = [
            [cmath.rect(mags[f][k], phase[f][k]) for k in range(frame_size)]
            for f in range(n_frames)
        ]
        signal = istft(frames, frame_size, hop, window, length=out_len)
        analysis = stft_complex(signal, frame_size, hop, window)
        # Re-analysis may yield fewer/more frames if out_len differs; align by index.
        phase = [
            [
                cmath.phase(analysis[f][k]) if f < len(analysis) else phase[f][k]
                for k in range(frame_size)
            ]
            for f in range(n_frames)
        ]
    return signal
