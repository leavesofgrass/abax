"""Analytic antenna patterns — pure stdlib (Phase A of antenna modeling).

Closed-form far-field patterns for the canonical wire antennas and uniform linear
arrays, with numerically-integrated directivity / gain and half-power beamwidth.
This is the foundation the GUI polar-pattern plot draws, and the stepping stone
toward a Method-of-Moments / NEC solver (later phases). All angles in radians
unless noted; ``theta`` is measured from the antenna (z) axis.
"""

from __future__ import annotations

import math

_TWO_PI = 2.0 * math.pi


def dipole_field(theta: float, length_wl: float = 0.5) -> float:
    """Normalised |E(θ)| of a centre-fed dipole of length ``length_wl`` wavelengths.

    Uses the standard sinusoidal-current pattern
    ``[cos(βL/2·cosθ) − cos(βL/2)] / sinθ`` with β = 2π. For a half-wave dipole this
    reduces to ``cos(π/2·cosθ)/sinθ`` (max 1 at θ = 90°).
    """
    s = math.sin(theta)
    if abs(s) < 1e-12:
        return 0.0
    bl2 = math.pi * length_wl
    return abs((math.cos(bl2 * math.cos(theta)) - math.cos(bl2)) / s)


def array_factor(theta: float, n: int, spacing_wl: float, phase_deg: float = 0.0) -> float:
    """|AF(θ)| of an ``n``-element uniform linear array on the z axis.

    ``spacing_wl`` is the element spacing in wavelengths and ``phase_deg`` the
    progressive phase α (degrees): broadside = 0, end-fire ≈ ∓360·spacing. Peak
    value is ``n``.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    psi = _TWO_PI * spacing_wl * math.cos(theta) + math.radians(phase_deg)
    denom = math.sin(psi / 2.0)
    if abs(denom) < 1e-12:
        return float(n)
    return abs(math.sin(n * psi / 2.0) / denom)


def directivity(field_fn, samples: int = 1440) -> float:
    """Directivity (linear) of an axially-symmetric pattern ``field_fn(theta)``.

    D = 2·|F|²max / ∫₀^π |F|² sinθ dθ (trapezoidal). ``field_fn`` returns field
    magnitude; it is normalised internally.
    """
    fmax = max((abs(field_fn(math.pi * i / samples)) for i in range(samples + 1)), default=0.0)
    if fmax <= 0:
        return 0.0
    dt = math.pi / samples
    integ = 0.0
    for i in range(samples + 1):
        th = math.pi * i / samples
        f = abs(field_fn(th)) / fmax
        w = 0.5 if i in (0, samples) else 1.0
        integ += w * f * f * math.sin(th) * dt
    return 2.0 / integ if integ > 0 else 0.0


def gain_dbi(field_fn, samples: int = 1440) -> float:
    """Directivity in dBi (lossless gain) for an axially-symmetric pattern."""
    d = directivity(field_fn, samples)
    return 10.0 * math.log10(d) if d > 0 else float("-inf")


def half_power_beamwidth(field_fn, samples: int = 3600) -> float:
    """Half-power (−3 dB) beamwidth in degrees around the strongest lobe.

    Scans θ over (0, π), finds the peak, and measures the angular span where the
    normalised power stays above 0.5. Returns 0 if no clear main lobe is found.
    """
    angles = [math.pi * (i + 0.5) / samples for i in range(samples)]
    power = [abs(field_fn(a)) ** 2 for a in angles]
    pmax = max(power) if power else 0.0
    if pmax <= 0:
        return 0.0
    peak = max(range(samples), key=power.__getitem__)
    half = pmax / 2.0
    lo = peak
    while lo > 0 and power[lo] >= half:
        lo -= 1
    hi = peak
    while hi < samples - 1 and power[hi] >= half:
        hi += 1
    return math.degrees(angles[hi] - angles[lo])


def pattern_samples(field_fn, count: int = 361, decibels: bool = False,
                    floor_db: float = -40.0) -> list:
    """Sample a pattern over θ ∈ [0, 2π) for a polar plot.

    Returns ``[(theta, magnitude)]`` with magnitude normalised to a peak of 1
    (linear), or 0..1 mapped from ``floor_db``..0 dB when ``decibels`` is set.
    """
    vals = [(2.0 * math.pi * i / (count - 1), abs(field_fn(2.0 * math.pi * i / (count - 1))))
            for i in range(count)]
    peak = max((m for _, m in vals), default=0.0) or 1.0
    out = []
    for th, m in vals:
        lin = m / peak
        if decibels:
            db = 20.0 * math.log10(lin) if lin > 1e-6 else floor_db
            lin = max(0.0, (db - floor_db) / (-floor_db))
        out.append((th, lin))
    return out


def _svg_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def polar_svg(samples, title: str = "", size: int = 360, margin: int = 18) -> str:
    """A standalone SVG string of a polar pattern plot (pure stdlib).

    ``samples`` is the ``[(theta, magnitude 0..1)]`` list from
    :func:`pattern_samples`. Draws amplitude rings, angle spokes and the closed
    pattern curve, antenna axis vertical — the same view as the GUI, exportable.
    """
    cx = cy = size / 2.0
    radius = size / 2.0 - margin
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">',
        f'<rect width="{size}" height="{size}" fill="white"/>',
    ]
    for frac in (0.25, 0.5, 0.75, 1.0):
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius * frac:.1f}" '
                     'fill="none" stroke="#bbbbbb" stroke-width="1"/>')
    for deg in range(0, 360, 30):
        a = math.radians(deg)
        x = cx + radius * math.sin(a)
        y = cy - radius * math.cos(a)
        parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
                     'stroke="#dddddd" stroke-width="1"/>')
    if samples:
        d = []
        for i, (th, mag) in enumerate(samples):
            x = cx + mag * radius * math.sin(th)
            y = cy - mag * radius * math.cos(th)
            d.append(f'{"M" if i == 0 else "L"}{x:.2f} {y:.2f}')
        d.append("Z")
        parts.append(f'<path d="{" ".join(d)}" fill="none" stroke="#1565c0" '
                     'stroke-width="2"/>')
    if title:
        parts.append(f'<text x="{cx:.1f}" y="14" text-anchor="middle" '
                     f'font-family="sans-serif" font-size="12">{_svg_escape(title)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# Convenience pattern factories (return a one-arg field_fn) -----------------

def half_wave_dipole():
    return lambda theta: dipole_field(theta, 0.5)


def full_wave_dipole():
    return lambda theta: dipole_field(theta, 1.0)


def linear_array(n: int, spacing_wl: float, phase_deg: float = 0.0,
                 element=None):
    """Field pattern of an ``n``-element array; ``element`` is an optional
    per-element field pattern (default isotropic), multiplied by the array factor."""
    el = element or (lambda _theta: 1.0)
    return lambda theta: el(theta) * array_factor(theta, n, spacing_wl, phase_deg)
