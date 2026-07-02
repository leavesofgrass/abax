"""Standalone Smith-chart SVG generator — pure stdlib.

:func:`smith_svg` returns a complete ``<svg …>…</svg>`` string drawing a standard
Smith chart: the outer unit circle, a family of constant-resistance circles and
constant-reactance arcs (both clipped to the unit circle), the real axis, and each
supplied load impedance plotted at its reflection coefficient
``Γ = (z − 1) / (z + 1)`` where ``z = Z / Z0`` is the normalized impedance.
Optionally a constant-VSWR circle (radius ``|Γ|`` centred at the origin) is drawn.

Companion to :mod:`abax.core.science.antenna`'s ``polar_svg`` and
:mod:`abax.core.science.chartsvg` — same standalone, exportable, hex-colour style.
Reuses :mod:`abax.core.science.rf` for Γ and VSWR. Pure stdlib; no third-party.
"""

from __future__ import annotations

import math

from . import rf

# Normalized resistance/reactance grid values (same set the GUI canvas uses).
_R_CIRCLES = (0.2, 0.5, 1.0, 2.0, 5.0)
_X_ARCS = (0.2, 0.5, 1.0, 2.0, 5.0)

# Palette matching the sibling chart modules.
_GRID = "#bbbbbb"
_AXIS = "#888888"
_UNIT = "#333333"
_POINT = "#c62828"
_VSWR = "#1565c0"


def _svg_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _as_complex(z) -> complex:
    """Accept a load impedance as ``complex`` / real, or an ``(R, X)`` pair."""
    if isinstance(z, (tuple, list)):
        r, x = z
        return complex(float(r), float(x))
    return complex(z)


def gamma_to_xy(gamma: complex, cx: float, cy: float, radius: float) -> tuple:
    """Map a reflection coefficient Γ to SVG pixel coordinates.

    The Γ-plane unit disc maps onto the chart circle of ``radius`` centred at
    ``(cx, cy)``. The real axis runs left→right (Γ = −1 at the left edge, +1 at
    the right edge, 0 at the centre); the imaginary axis is flipped so +j Γ plots
    upward, as on a paper Smith chart.
    """
    return (cx + gamma.real * radius, cy - gamma.imag * radius)


def impedance_to_xy(z, z0, cx: float, cy: float, radius: float) -> tuple:
    """Convenience: full ``Z → Γ → (x, y)`` mapping for one load impedance."""
    gamma = rf.reflection_coefficient(_as_complex(z), complex(z0))
    return gamma_to_xy(gamma, cx, cy, radius)


def smith_svg(points, z0=50.0, *, show_vswr=None, size: int = 360,
              margin: int = 18, title: str = "") -> str:
    """A standalone SVG string of a standard Smith chart (pure stdlib).

    ``points`` is a list of load impedances, each a ``complex`` (or real) or an
    ``(R, X)`` pair, plotted at their reflection coefficient on the ``z0`` system
    impedance. If ``show_vswr`` is truthy a constant-VSWR circle is drawn: pass
    ``True`` to circle through the (last plotted) load, or a numeric ``|Γ|`` /
    VSWR-derived radius is used when the point list is empty.

    The chart draws the outer unit circle, constant-resistance circles, and
    constant-reactance arcs — all clipped to the unit disc — plus the real axis.
    """
    cx = cy = size / 2.0
    radius = size / 2.0 - margin
    z0c = complex(z0)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">',
        f'<rect width="{size}" height="{size}" fill="white"/>',
        # Clip everything grid-related to the unit disc.
        f'<clipPath id="smithdisc"><circle cx="{cx:.2f}" cy="{cy:.2f}" '
        f'r="{radius:.2f}"/></clipPath>',
        '<g clip-path="url(#smithdisc)">',
    ]

    # Constant-resistance circles: centre (r/(1+r), 0), radius 1/(1+r) in Γ-plane.
    for r in _R_CIRCLES:
        ccx = cx + (r / (1.0 + r)) * radius
        rad = radius / (1.0 + r)
        parts.append(f'<circle cx="{ccx:.2f}" cy="{cy:.2f}" r="{rad:.2f}" '
                     f'fill="none" stroke="{_GRID}" stroke-width="1"/>')
    # Constant-reactance arcs: centre (1, ±1/x), radius 1/x in Γ-plane (both signs).
    for x in _X_ARCS:
        rad = radius / x
        parts.append(f'<circle cx="{cx + radius:.2f}" cy="{cy - radius / x:.2f}" '
                     f'r="{rad:.2f}" fill="none" stroke="{_GRID}" stroke-width="1"/>')
        parts.append(f'<circle cx="{cx + radius:.2f}" cy="{cy + radius / x:.2f}" '
                     f'r="{rad:.2f}" fill="none" stroke="{_GRID}" stroke-width="1"/>')
    parts.append("</g>")

    # Real axis and the outer unit circle (drawn over the clipped grid).
    parts.append(f'<line x1="{cx - radius:.2f}" y1="{cy:.2f}" '
                 f'x2="{cx + radius:.2f}" y2="{cy:.2f}" '
                 f'stroke="{_AXIS}" stroke-width="1"/>')
    parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius:.2f}" '
                 f'fill="none" stroke="{_UNIT}" stroke-width="1.5"/>')

    # Constant-VSWR circle (radius |Γ| about the origin).
    gammas = [rf.reflection_coefficient(_as_complex(z), z0c) for z in points]
    if show_vswr:
        if isinstance(show_vswr, (int, float)) and not isinstance(show_vswr, bool):
            mag = float(show_vswr)
        elif gammas:
            mag = abs(gammas[-1])
        else:
            mag = 0.0
        mag = max(0.0, min(1.0, mag))
        if mag > 0.0:
            vswr = rf.vswr_from_gamma(mag)
            parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" '
                         f'r="{mag * radius:.2f}" fill="none" stroke="{_VSWR}" '
                         f'stroke-width="1.2" stroke-dasharray="4 3"/>')
            label = "VSWR = inf" if math.isinf(vswr) else f"VSWR = {vswr:.2f}:1"
            parts.append(f'<text x="{cx:.2f}" y="{cy - mag * radius - 4:.2f}" '
                         f'text-anchor="middle" font-family="sans-serif" '
                         f'font-size="10" fill="{_VSWR}">{_svg_escape(label)}</text>')

    # Plot each load impedance at its Γ.
    for gamma in gammas:
        px, py = gamma_to_xy(gamma, cx, cy, radius)
        parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="4" '
                     f'fill="{_POINT}" stroke="#7f1010" stroke-width="1"/>')
        parts.append(f'<line x1="{cx:.2f}" y1="{cy:.2f}" x2="{px:.2f}" y2="{py:.2f}" '
                     f'stroke="{_POINT}" stroke-width="1"/>')

    if title:
        parts.append(f'<text x="{cx:.2f}" y="14" text-anchor="middle" '
                     f'font-family="sans-serif" font-size="12">'
                     f'{_svg_escape(title)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)
