"""General thin-wire Method of Moments for arbitrary 3-D wire structures.

Pure stdlib. This generalizes :mod:`abax.core.science.mom` (a single straight
center-fed dipole) to any collection of **polyline wires** in 3-D: bent wires,
V / inverted-V antennas, and multi-element arrays such as a Yagi-Uda (a driven
dipole plus parasitic directors/reflectors).

Each wire is a list of node points (in wavelengths); consecutive nodes define
straight segments. The current is expanded in overlapping piecewise-sinusoidal
basis functions, one per interior node of each wire (so the current is zero at
free wire ends and continuous through bends). The EFIE is tested Galerkin-style
with the mixed-potential element

    Z_mn = (j 30 / k) * sum_{seg p in m} sum_{seg q in n} integral integral
              [ k^2 (t_p . t_q) f_m f_n  -  f_m' f_n' ] * exp(-jkR)/R  ds' ds

where ``t_p . t_q`` is the dot product of the two segment tangents (this is the
only new ingredient versus the collinear case, where it is always 1) and
``R = sqrt(|r - r'|^2 + a^2)``. Delta-gap voltage sources drive chosen nodes; the
feed-point impedance is ``V / I(feed)``.

Distinct wires do not share nodes (no multi-wire junctions), which covers dipoles,
bent wires and parasitic arrays. The straight dipole is the special case and is
used to validate this solver against :mod:`mom`.
"""

from __future__ import annotations

import cmath
import math

from .mom import _gauss_legendre, _solve_complex

_TWO_PI = 2.0 * math.pi


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _lerp(p, q, t):
    return (p[0] + (q[0] - p[0]) * t,
            p[1] + (q[1] - p[1]) * t,
            p[2] + (q[2] - p[2]) * t)


class _Seg:
    """One straight segment of a wire: endpoints, length, unit tangent."""
    __slots__ = ("p", "q", "length", "tangent")

    def __init__(self, p, q):
        self.p = p
        self.q = q
        d = _norm(_sub(q, p))
        if d == 0.0:
            raise ValueError("zero-length wire segment")
        self.length = d
        self.tangent = tuple(c / d for c in _sub(q, p))


def _wire_segments(points):
    if len(points) < 2:
        raise ValueError("a wire needs at least two points")
    pts = [tuple(float(c) for c in p) for p in points]
    return [_Seg(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


class _Basis:
    """A piecewise-sinusoidal basis at an interior node: a rising arm on the
    segment before the node and a falling arm on the segment after it.

    Each arm is ``(seg, mode)`` with ``mode`` "rise" (0 at the far end -> 1 at the
    node) or "fall" (1 at the node -> 0 at the far end). ``s`` runs 0..length from
    the segment's stored ``p`` endpoint, which is the far node for the rise arm and
    the basis node for the fall arm.
    """
    __slots__ = ("arms",)

    def __init__(self, seg_before, seg_after):
        # seg_before goes far-node -> basis-node (rise), seg_after basis-node ->
        # far-node (fall); both already oriented that way by construction.
        self.arms = ((seg_before, "rise"), (seg_after, "fall"))


def _f_and_df(mode, s, length, k):
    """PWS amplitude and its arc-length derivative on one arm."""
    sk = math.sin(k * length)
    if mode == "rise":
        return math.sin(k * s) / sk, k * math.cos(k * s) / sk
    # fall
    return math.sin(k * (length - s)) / sk, -k * math.cos(k * (length - s)) / sk


def _build_bases(wires):
    """Return (segments-per-wire unused) the global list of `_Basis` plus an index
    map ``(wire_index, node_index) -> basis_index``."""
    bases = []
    index = {}
    for wi, points in enumerate(wires):
        segs = _wire_segments(points)
        for node in range(1, len(segs)):           # interior nodes
            # segment before ends at `node` (p->q = node-1 -> node): rise toward node
            before = segs[node - 1]
            # segment after starts at `node`: fall away from node
            after = segs[node]
            index[(wi, node)] = len(bases)
            bases.append(_Basis(before, after))
    return bases, index


def solve(wires, feeds, radius: float = 1e-3, quad: int = 16) -> dict:
    """Solve a thin-wire structure and return currents and feed impedances.

    ``wires`` is a list of polylines (each a list of >=2 ``(x, y, z)`` points in
    wavelengths). ``feeds`` is a list of ``(wire_index, node_index, voltage)``
    delta-gap sources at interior nodes. ``radius`` is the wire radius
    (wavelengths); ``quad`` the Gauss-Legendre order per segment per dimension.

    Returns ``{"current": [complex...], "feed_impedance": {(wi,node): complex},
    "n_basis": int}``. ``current[b]`` is the current at the b-th interior node
    (global basis order).
    """
    if radius <= 0.0:
        raise ValueError("radius must be > 0")
    k = _TWO_PI
    a2 = radius * radius
    bases, index = _build_bases(wires)
    nb = len(bases)
    if nb == 0:
        raise ValueError("no interior nodes: each wire needs >= 3 points")
    gl, gw = _gauss_legendre(quad)
    pref = 1j * 30.0 / k

    def arm_arm(obs_seg, obs_mode, src_seg, src_mode):
        tdot = _dot(obs_seg.tangent, src_seg.tangent)
        lo, ls = obs_seg.length, src_seg.length
        ho, hs = 0.5 * lo, 0.5 * ls
        total = 0j
        for io in range(quad):
            so = ho * (gl[io] + 1.0)               # 0..lo
            fo, dfo = _f_and_df(obs_mode, so, lo, k)
            ro = _lerp(obs_seg.p, obs_seg.q, so / lo)
            wo = gw[io] * ho
            for js in range(quad):
                ss = hs * (gl[js] + 1.0)
                fs, dfs = _f_and_df(src_mode, ss, ls, k)
                rs = _lerp(src_seg.p, src_seg.q, ss / ls)
                dr = _sub(ro, rs)
                R = math.sqrt(dr[0] * dr[0] + dr[1] * dr[1] + dr[2] * dr[2] + a2)
                green = cmath.exp(-1j * k * R) / R
                total += wo * gw[js] * hs * (k * k * tdot * fo * fs - dfo * dfs) * green
        return total

    Z = [[0j] * nb for _ in range(nb)]
    for m in range(nb):
        for n in range(m, nb):
            acc = 0j
            for (oseg, omode) in bases[m].arms:
                for (sseg, smode) in bases[n].arms:
                    acc += arm_arm(oseg, omode, sseg, smode)
            Z[m][n] = Z[n][m] = pref * acc          # reciprocal

    V = [0j] * nb
    for (wi, node, volts) in feeds:
        if (wi, node) not in index:
            raise ValueError(f"feed at ({wi},{node}) is not an interior node")
        V[index[(wi, node)]] = complex(volts)
    current = _solve_complex([row[:] for row in Z], V[:])

    feed_imp = {}
    for (wi, node, volts) in feeds:
        ib = index[(wi, node)]
        if current[ib] != 0:
            feed_imp[(wi, node)] = complex(volts) / current[ib]
    return {"current": current, "feed_impedance": feed_imp, "n_basis": nb}


def radiation_vector(wires, result, theta: float, phi: float):
    """The far-field radiation vector ``N`` (complex 3-vector) and the observation
    unit vector ``rhat`` for the solved currents, by the midpoint rule over every
    segment. ``theta`` is measured from +z, ``phi`` from +x."""
    k = _TWO_PI
    rhat = (math.sin(theta) * math.cos(phi),
            math.sin(theta) * math.sin(phi),
            math.cos(theta))
    _, index = _build_bases(wires)
    cur = result["current"]
    N = [0j, 0j, 0j]
    for wi, points in enumerate(wires):
        segs = _wire_segments(points)
        for j, seg in enumerate(segs):
            ln = seg.length
            mid = 0.5 * ln
            i_seg = 0j
            ib_lo = index.get((wi, j))            # node j interior -> fall arm here
            if ib_lo is not None:
                f, _ = _f_and_df("fall", mid, ln, k)
                i_seg += cur[ib_lo] * f
            ib_hi = index.get((wi, j + 1))        # node j+1 interior -> rise arm here
            if ib_hi is not None:
                f, _ = _f_and_df("rise", mid, ln, k)
                i_seg += cur[ib_hi] * f
            rmid = _lerp(seg.p, seg.q, 0.5)
            weight = i_seg * ln * cmath.exp(1j * k * _dot(rhat, rmid))
            N[0] += weight * seg.tangent[0]
            N[1] += weight * seg.tangent[1]
            N[2] += weight * seg.tangent[2]
    return N, rhat


def far_field_intensity(wires, result, theta: float, phi: float) -> float:
    """Relative radiation intensity ``|N_perp|^2`` in direction (theta, phi).

    Only the component of the radiation vector transverse to the line of sight
    radiates, so the on-axis component is projected out. Absolute scale is
    arbitrary; ratios (front/back, pattern shape) are meaningful.
    """
    N, rhat = radiation_vector(wires, result, theta, phi)
    ndotr = N[0] * rhat[0] + N[1] * rhat[1] + N[2] * rhat[2]
    perp = [N[i] - ndotr * rhat[i] for i in range(3)]
    return sum(abs(c) ** 2 for c in perp)


def front_to_back_db(wires, result, theta: float = math.pi / 2,
                     front_phi: float = 0.0) -> float:
    """Front-to-back ratio in dB: intensity toward ``front_phi`` over the opposite
    azimuth (both at elevation ``theta``). Positive means the array beams forward."""
    front = far_field_intensity(wires, result, theta, front_phi)
    back = far_field_intensity(wires, result, theta, front_phi + math.pi)
    if back <= 0.0:
        return float("inf")
    return 10.0 * math.log10(front / back)


def dipole(length_wl: float, radius_wl: float = 1e-3, segments: int = 20):
    """Convenience: a straight center-fed dipole along z, returning its feed
    impedance (ohms). Mirrors :func:`abax.core.science.mom.dipole_input_impedance`
    and is used to validate this general solver against the dedicated one."""
    n = max(2, segments + (segments & 1))
    half = length_wl / 2.0
    dz = length_wl / n
    points = [(0.0, 0.0, -half + i * dz) for i in range(n + 1)]
    res = solve([points], [(0, n // 2, 1.0)], radius=radius_wl)
    return res["feed_impedance"][(0, n // 2)]


def yagi(driven_len: float, parasitics, spacing_wl: float, radius_wl: float = 1e-3,
         segments: int = 12):
    """Build and solve a Yagi-Uda along the x-axis (elements parallel to z).

    ``driven_len`` is the driven element length (wavelengths). ``parasitics`` is a
    list of ``(length_wl, x_offset_wl)`` for reflectors (negative offset) and
    directors (positive offset). Returns the solver result dict plus the driven
    feed impedance under ``"driven_impedance"``.
    """
    def element(length, x):
        n = max(2, segments + (segments & 1))
        half = length / 2.0
        dz = length / n
        return [(x, 0.0, -half + i * dz) for i in range(n + 1)]

    wires = [element(driven_len, 0.0)]
    for (plen, px) in parasitics:
        wires.append(element(plen, px))
    n = max(2, segments + (segments & 1))
    feeds = [(0, n // 2, 1.0)]                       # only the driven element is fed
    res = solve(wires, feeds, radius=radius_wl)
    res["driven_impedance"] = res["feed_impedance"][(0, n // 2)]
    return res
