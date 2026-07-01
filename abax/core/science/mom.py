"""Minimal thin-wire Method of Moments for a straight, center-fed dipole.

Pure stdlib. A genuine multi-segment MoM (not an assumed-current model): the wire
current is expanded in overlapping **piecewise-sinusoidal** (PWS) basis functions,
the electric-field integral equation is tested Galerkin-style, and the resulting
complex linear system ``[Z]{I} = {V}`` is solved for the current distribution. The
input impedance is ``1 / I(feed)`` for a 1-volt delta-gap source.

The EFIE Galerkin element uses the mixed-potential ("k^2 f f' minus f' f'") form

    Z_ij = (j * 30 / k) * integral integral
              [ k^2 f_i(z) f_j(z') - f_i'(z) f_j'(z') ] * exp(-jkR)/R  dz' dz

with ``R = sqrt((z - z')^2 + a^2)`` and ``30 = eta / 4pi`` (eta = 120pi). The
finite wire radius ``a`` keeps the kernel bounded, so the double integral is
evaluated by ordinary Gauss-Legendre quadrature -- no singularity extraction.

Everything is in wavelengths (lambda = 1, k = 2pi), so impedances come out in
ohms directly.

This generalizes the closed-form
:func:`abax.core.science.antenna_impedance.dipole_input_impedance`. With a single
basis (``segments=2``) the current is forced to the half-wave cosine and the MoM
reproduces the induced-EMF value almost exactly (73.1 + 42j for a thin half-wave
dipole) -- a rigorous check of the kernel and constants. As segments increase the
solver relaxes that assumption and converges to ~85 + 45j ohms, which is the
*physically correct* input impedance of a real 0.5 lambda dipole: it sits just
above its natural resonance (~0.47 lambda), so the resistance rises above the
idealized 73 ohms and the reactance is inductive -- in agreement with NEC.
"""

from __future__ import annotations

import cmath
import math

_TWO_PI = 2.0 * math.pi


def _gauss_legendre(n: int) -> tuple[list[float], list[float]]:
    """Gauss-Legendre nodes and weights on [-1, 1] (Newton on the Legendre roots)."""
    nodes = [0.0] * n
    weights = [0.0] * n
    m = (n + 1) // 2
    for i in range(m):
        # initial guess for the i-th root
        x = math.cos(math.pi * (i + 0.75) / (n + 0.5))
        for _ in range(100):
            p0, p1 = 1.0, 0.0
            for j in range(n):
                p0, p1 = ((2 * j + 1) * x * p0 - j * p1) / (j + 1), p0
            # p0 = P_n(x), derivative dp via recurrence
            dp = n * (x * p0 - p1) / (x * x - 1.0)
            dx = p0 / dp
            x -= dx
            if abs(dx) < 1e-15:
                break
        nodes[i] = -x
        nodes[n - 1 - i] = x
        w = 2.0 / ((1.0 - x * x) * dp * dp)
        weights[i] = w
        weights[n - 1 - i] = w
    return nodes, weights


def _solve_complex(a: list[list[complex]], b: list[complex]) -> list[complex]:
    """Solve the complex linear system ``a x = b`` by Gaussian elimination with
    partial pivoting. ``a`` is modified in place."""
    n = len(b)
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) == 0.0:
            raise ValueError("singular MoM matrix")
        if pivot != col:
            a[col], a[pivot] = a[pivot], a[col]
            b[col], b[pivot] = b[pivot], b[col]
        piv = a[col][col]
        for r in range(col + 1, n):
            factor = a[r][col] / piv
            if factor != 0.0:
                for c in range(col, n):
                    a[r][c] -= factor * a[col][c]
                b[r] -= factor * b[col]
    x = [0j] * n
    for r in range(n - 1, -1, -1):
        s = b[r] - sum(a[r][c] * x[c] for c in range(r + 1, n))
        x[r] = s / a[r][r]
    return x


def _pws(z: float, z_i: float, dz: float, k: float) -> float:
    """Piecewise-sinusoidal basis: sin(k(dz-|z-z_i|))/sin(k dz) on |z-z_i|<dz."""
    d = abs(z - z_i)
    if d >= dz:
        return 0.0
    return math.sin(k * (dz - d)) / math.sin(k * dz)


def _pws_deriv(z: float, z_i: float, dz: float, k: float) -> float:
    """d/dz of the PWS basis (sign flips across the centre node)."""
    d = abs(z - z_i)
    if d >= dz:
        return 0.0
    mag = k * math.cos(k * (dz - d)) / math.sin(k * dz)
    return -mag if z > z_i else mag


def solve_dipole(length_wl: float, radius_wl: float = 1e-3,
                 segments: int = 20, quad: int = 24) -> dict:
    """Run the MoM for a center-fed dipole and return a result dict.

    ``length_wl`` total length and ``radius_wl`` wire radius are in wavelengths;
    ``segments`` (forced even, so a node sits at the feed) sets the number of
    expansion functions; ``quad`` is the Gauss-Legendre order per segment per
    dimension. Returns ``{"input_impedance": complex, "feed_current": complex,
    "z_nodes": [...], "current": [complex...]}`` where ``current`` is the current
    at each interior node.
    """
    if length_wl <= 0.0:
        raise ValueError("length must be > 0")
    if radius_wl <= 0.0:
        raise ValueError("radius must be > 0")
    # even, >= 2 (a node sits at the feed). n_seg == 2 is the single full-length
    # PWS mode, which reproduces the induced-EMF / assumed-sinusoidal-current model.
    n_seg = max(2, segments + (segments & 1))
    k = _TWO_PI
    a = radius_wl
    dz = length_wl / n_seg                          # segment length
    half = length_wl / 2.0
    nodes_z = [-half + m * dz for m in range(n_seg + 1)]
    interior = list(range(1, n_seg))                # basis-function node indices
    nb = len(interior)
    feed = interior.index(n_seg // 2)               # basis centred at z = 0

    gl, gw = _gauss_legendre(quad)

    def seg_quad(zc_obs, zo, src_lo, src_hi, obs_lo, obs_hi):
        """Double GL integral of the EFIE integrand over one obs x src segment
        rectangle, for the bases centred at zo (obs) and zc_obs is the src
        centre; returns the complex contribution."""
        ho = 0.5 * (obs_hi - obs_lo)
        co = 0.5 * (obs_hi + obs_lo)
        hs = 0.5 * (src_hi - src_lo)
        cs = 0.5 * (src_hi + src_lo)
        total = 0j
        for io in range(quad):
            z = co + ho * gl[io]
            fo = _pws(z, zo, dz, k)
            fo_d = _pws_deriv(z, zo, dz, k)
            wo = gw[io] * ho
            for is_ in range(quad):
                zp = cs + hs * gl[is_]
                fs = _pws(zp, zc_obs, dz, k)
                fs_d = _pws_deriv(zp, zc_obs, dz, k)
                r = math.sqrt((z - zp) ** 2 + a * a)
                green = cmath.exp(-1j * k * r) / r
                kernel = (k * k * fo * fs - fo_d * fs_d) * green
                total += wo * gw[is_] * hs * kernel
        return total

    pref = 1j * 30.0 / k
    Z = [[0j] * nb for _ in range(nb)]
    for ii, ni in enumerate(interior):
        zo = nodes_z[ni]
        obs_segs = ((nodes_z[ni - 1], nodes_z[ni]), (nodes_z[ni], nodes_z[ni + 1]))
        for jj, nj in enumerate(interior):
            zs = nodes_z[nj]
            src_segs = ((nodes_z[nj - 1], nodes_z[nj]),
                        (nodes_z[nj], nodes_z[nj + 1]))
            acc = 0j
            for (olo, ohi) in obs_segs:
                for (slo, shi) in src_segs:
                    acc += seg_quad(zs, zo, slo, shi, olo, ohi)
            Z[ii][jj] = pref * acc

    V = [0j] * nb
    V[feed] = 1.0 + 0j                              # 1 V delta-gap at the feed node
    current = _solve_complex(Z, V)
    feed_current = current[feed]
    if feed_current == 0:
        raise ValueError("zero feed current")
    return {
        "input_impedance": 1.0 / feed_current,
        "feed_current": feed_current,
        "z_nodes": [nodes_z[n] for n in interior],
        "current": current,
    }


def dipole_input_impedance(length_wl: float, radius_wl: float = 1e-3,
                           segments: int = 20) -> complex:
    """Convenience wrapper: just the MoM input impedance (ohms, complex)."""
    return solve_dipole(length_wl, radius_wl, segments)["input_impedance"]
