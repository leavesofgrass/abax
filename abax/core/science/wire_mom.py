"""General thin-wire Method of Moments for arbitrary 3-D wire structures.

Pure stdlib. This generalizes :mod:`abax.core.science.mom` (a single straight
center-fed dipole) to any collection of **polyline wires** in 3-D: bent wires,
V / inverted-V antennas, multi-element arrays such as a Yagi-Uda (a driven
dipole plus parasitic directors/reflectors), and — via shared endpoints —
**multi-wire junctions** (a vertical with radials, a loop, a fed T).

Each wire is a list of node points (in wavelengths); consecutive nodes define
straight segments. The current is expanded in overlapping piecewise-sinusoidal
basis functions. At an ordinary interior node of one wire there is exactly one
basis (a rising arm on the segment before the node, a falling arm on the segment
after), so the current is zero at free wire ends and continuous through bends.
Where several segment-ends meet at one point — a **junction** of degree ``d`` —
there are ``d - 1`` independent bases: each pairs a rising arm on a reference arm
with a falling arm on one of the others. That count is exactly the junction's
degrees of freedom, and it enforces **Kirchhoff's current law** at the node: the
current the solution pushes into the reference arm equals the sum it draws out of
the rest, so current is genuinely continuous across the junction (it is *not*
forced to zero there as it would be for unconnected wire ends). A single wire's
interior node is the ``d = 2`` special case and reduces to exactly the old
before/after basis, so the free-space single-wire path is unchanged.

The EFIE is tested Galerkin-style with the mixed-potential element

    Z_mn = (j 30 / k) * sum_{arm p in m} sum_{arm q in n} integral integral
              [ k^2 (t_p . t_q) f_m f_n  -  f_m' f_n' ] * exp(-jkR)/R  ds' ds

where ``t_p . t_q`` is the dot product of the two arm tangents and
``R = sqrt(|r - r'|^2 + a^2)``. Delta-gap voltage sources drive chosen nodes; the
feed-point impedance is ``V / I(feed)``.

Ground: :func:`solve` and the free-space radiation helpers model the structure in
free space. :func:`radiation_vector_ground` / :func:`far_field_intensity_ground`
add a horizontal image-plane reflection (perfect ground, or a finite ground via a
Fresnel reflection coefficient), so an elevation cut over ground shows a real
take-off angle rather than the free-space pattern that is symmetric about the
horizon. The free-space path is left exactly as before.
"""

from __future__ import annotations

import cmath
import math

from .mom import _gauss_legendre, _solve_complex

_TWO_PI = 2.0 * math.pi

#: Endpoints closer than this (in wavelengths) are treated as the same node, so
#: two wires that share a coordinate form a junction. A hundredth of a millimetre
#: at HF scales is far below any meaningful wire spacing yet safely above float
#: round-off in the geometry builders.
_NODE_TOL = 1e-9


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


def _node_key(p):
    """Quantise a point to a lattice cell so coincident endpoints (across wires)
    hash together into one junction node."""
    inv = 1.0 / _NODE_TOL
    return (round(p[0] * inv), round(p[1] * inv), round(p[2] * inv))


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


class _Arm:
    """One arm of a basis: a segment, the sinusoid mode over it, and a current
    direction sign.

    ``mode`` is "rise" (0 at the segment's far end -> 1 at the basis node, i.e. the
    node is the segment's ``.q``) or "fall" (1 at the node -> 0 at the far end, the
    node is the segment's ``.p``); ``s`` runs 0..length from the stored ``.p``
    endpoint. ``sign`` (+/-1) orients the current so it flows the same physical way
    through every basis: the current density an arm carries is
    ``coeff * f(mode) * sign * tangent``. ``(wire, seg_index)`` locates the segment
    so the radiation integral can add every arm that lands on it.
    """
    __slots__ = ("seg", "mode", "sign", "wire", "seg_index")

    def __init__(self, seg, mode, sign, wire, seg_index):
        self.seg = seg
        self.mode = mode
        self.sign = sign
        self.wire = wire
        self.seg_index = seg_index


class _Basis:
    """A piecewise-sinusoidal basis: a rising arm into a node and a falling arm
    out of it. For an ordinary interior node the two arms are the segment before
    and the segment after; at a junction they are a reference arm and one of the
    other incident arms."""
    __slots__ = ("arms",)

    def __init__(self, arm_in, arm_out):
        self.arms = (arm_in, arm_out)


def _f_and_df(mode, s, length, k):
    """PWS amplitude and its arc-length derivative on one arm."""
    sk = math.sin(k * length)
    if mode == "rise":
        return math.sin(k * s) / sk, k * math.cos(k * s) / sk
    # fall
    return math.sin(k * (length - s)) / sk, -k * math.cos(k * (length - s)) / sk


def _incident_arms(wires):
    """Map each geometric node -> list of segment-ends incident to it.

    Each entry is ``(_Seg, node_mode, at_q, wire, seg_index)`` where ``node_mode``
    is the PWS mode that is amplitude 1 at the node ("rise" if the node is the
    segment's ``.q``, "fall" if it is the ``.p``) and ``at_q`` records which end
    touches. Returns ``(node_key -> [entries])`` plus the per-wire segment lists.
    """
    all_segs = []
    incident: dict = {}
    for wi, points in enumerate(wires):
        segs = _wire_segments(points)
        all_segs.append(segs)
        for si, seg in enumerate(segs):
            # "rise" peaks at s=length (seg.q); "fall" peaks at s=0 (seg.p).
            incident.setdefault(_node_key(seg.q), []).append(
                (seg, "rise", True, wi, si))
            incident.setdefault(_node_key(seg.p), []).append(
                (seg, "fall", False, wi, si))
    return incident, all_segs


def _build_bases(wires):
    """Build the global basis list plus a feed index map.

    Returns ``(bases, index, all_segs)`` where ``bases`` is the list of
    :class:`_Basis`, ``index`` maps ``(wire_index, node_index) -> [basis_index,
    ...]`` (the bases whose node is that wire node — one for an interior node,
    ``d-1`` for a junction), and ``all_segs`` is the per-wire segment lists.

    At a node where ``d`` segment-ends meet, ``d - 1`` bases are made: arm 0 is the
    reference arm carrying current *into* the node, and each other arm gives a
    basis carrying current from arm 0's far side, through the node, out that arm.
    A per-arm ``sign`` keeps the current flowing the same physical way regardless
    of how each segment happens to be oriented: for the into-node arm the current
    is +tangent when the node is the segment's ``.q`` and -tangent when it is the
    ``.p``; the out-of-node arm takes the opposite. Summing the solved
    coefficients, arm 0 conducts the total into the node and each other arm
    conducts its share out — Kirchhoff current continuity holds. A degree-2
    interior node yields one basis with signs (+1, +1), identical to the classic
    before/after PWS pair, so single-wire results are unchanged.
    """
    incident, all_segs = _incident_arms(wires)

    # Pre-compute node_key -> (wire, node_index) memberships for the feed map.
    key_members: dict = {}
    for wi, points in enumerate(wires):
        for ni in range(len(points)):
            p = tuple(float(c) for c in points[ni])
            key_members.setdefault(_node_key(p), []).append((wi, ni))

    bases = []
    index: dict = {}
    for key, arms in incident.items():
        if len(arms) < 2:
            continue                                # free wire end: no basis
        # Reference arm: current flows INTO the node. +tangent if it enters via
        # the segment's .q (node = .q), else -tangent.
        ref_seg, ref_mode, ref_at_q, ref_wi, ref_si = arms[0]
        ref_sign = 1 if ref_at_q else -1
        ref_in = _Arm(ref_seg, ref_mode, ref_sign, ref_wi, ref_si)
        node_bases = []
        for (seg, mode, at_q, wi, si) in arms[1:]:
            # Out arm: current flows OUT of the node = opposite of the into rule.
            out_sign = -1 if at_q else 1
            arm_out = _Arm(seg, mode, out_sign, wi, si)
            node_bases.append(len(bases))
            bases.append(_Basis(ref_in, arm_out))
        for member in key_members.get(key, []):
            index[member] = list(node_bases)
    return bases, index, all_segs


def solve(wires, feeds, radius: float = 1e-3, quad: int = 16) -> dict:
    """Solve a thin-wire structure and return currents and feed impedances.

    ``wires`` is a list of polylines (each a list of >=2 ``(x, y, z)`` points in
    wavelengths). ``feeds`` is a list of ``(wire_index, node_index, voltage)``
    delta-gap sources at nodes that carry a basis (an interior node, or a
    junction). ``radius`` is the wire radius (wavelengths); ``quad`` the
    Gauss-Legendre order per segment per dimension.

    Wires that share an endpoint (to within :data:`_NODE_TOL`) form a **junction**
    where current is continuous (Kirchhoff), so verticals-with-radials, loops and
    fed T-junctions solve correctly instead of pinning the shared point to zero
    current.

    Returns ``{"current": [complex...], "feed_impedance": {(wi,node): complex},
    "n_basis": int}``. ``current[b]`` is the coefficient of the b-th basis. For a
    fed node the feed impedance is ``V / I_node`` where ``I_node`` is the current
    flowing into that node (the sum of the node's basis coefficients).
    """
    if radius <= 0.0:
        raise ValueError("radius must be > 0")
    k = _TWO_PI
    a2 = radius * radius
    bases, index, _all_segs = _build_bases(wires)
    nb = len(bases)
    if nb == 0:
        raise ValueError(
            "no basis functions: a wire needs >= 3 points, or two wires must "
            "share an endpoint to form a junction")
    gl, gw = _gauss_legendre(quad)
    pref = 1j * 30.0 / k

    def arm_arm(obs_arm, src_arm):
        obs_seg, src_seg = obs_arm.seg, src_arm.seg
        obs_mode, src_mode = obs_arm.mode, src_arm.mode
        # The current direction signs multiply through both the k^2 (t.t) f f term
        # and the f' f' term, so fold them into the tangent dot product once.
        ssign = obs_arm.sign * src_arm.sign
        tdot = ssign * _dot(obs_seg.tangent, src_seg.tangent)
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
                total += (wo * gw[js] * hs
                          * (k * k * tdot * fo * fs - ssign * dfo * dfs) * green)
        return total

    Z = [[0j] * nb for _ in range(nb)]
    for m in range(nb):
        for n in range(m, nb):
            acc = 0j
            for oarm in bases[m].arms:
                for sarm in bases[n].arms:
                    acc += arm_arm(oarm, sarm)
            Z[m][n] = Z[n][m] = pref * acc          # reciprocal

    V = [0j] * nb
    fed_keys = []
    for (wi, node, volts) in feeds:
        if (wi, node) not in index:
            raise ValueError(
                f"feed at ({wi},{node}) is not a basis node (interior or junction)")
        fed_keys.append((wi, node, complex(volts)))
        # Drive every basis sharing the fed node with the delta-gap voltage; each
        # basis's reference arm reaches the node, so this excites the node.
        for ib in index[(wi, node)]:
            V[ib] = complex(volts)
    current = _solve_complex([row[:] for row in Z], V[:])

    feed_imp = {}
    for (wi, node, volts) in fed_keys:
        i_node = sum(current[ib] for ib in index[(wi, node)])
        if i_node != 0:
            feed_imp[(wi, node)] = volts / i_node
    return {"current": current, "feed_impedance": feed_imp, "n_basis": nb}


def _segment_currents(wires, result):
    """Per-segment sampled current, as ``seg_i(s_fraction)`` closures are not
    needed — instead return, for every segment, the list of ``(mode, coeff)``
    arms contributing to it. The midpoint current is ``sum coeff * f(mode)``.

    Returns ``(all_segs, seg_arms)`` where ``seg_arms[wi][si]`` is a list of
    ``(mode, signed_coefficient)``; the signed coefficient already folds in the
    arm's current-direction sign, so the segment current at ``s`` is
    ``sum signed_coeff * f(mode, s)`` and its vector is that times the tangent."""
    bases, _index, all_segs = _build_bases(wires)
    cur = result["current"]
    seg_arms = [[[] for _ in segs] for segs in all_segs]
    for bi, basis in enumerate(bases):
        coeff = cur[bi]
        for arm in basis.arms:
            seg_arms[arm.wire][arm.seg_index].append((arm.mode, arm.sign * coeff))
    return all_segs, seg_arms


def radiation_vector(wires, result, theta: float, phi: float):
    """The far-field radiation vector ``N`` (complex 3-vector) and the observation
    unit vector ``rhat`` for the solved currents, by the midpoint rule over every
    segment. ``theta`` is measured from +z, ``phi`` from +x. Free space."""
    k = _TWO_PI
    rhat = (math.sin(theta) * math.cos(phi),
            math.sin(theta) * math.sin(phi),
            math.cos(theta))
    all_segs, seg_arms = _segment_currents(wires, result)
    N = [0j, 0j, 0j]
    for wi, segs in enumerate(all_segs):
        for si, seg in enumerate(segs):
            ln = seg.length
            mid = 0.5 * ln
            i_seg = 0j
            for (mode, coeff) in seg_arms[wi][si]:
                f, _ = _f_and_df(mode, mid, ln, k)
                i_seg += coeff * f
            if i_seg == 0j:
                continue
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
    arbitrary; ratios (front/back, pattern shape) are meaningful. Free space.
    """
    N, rhat = radiation_vector(wires, result, theta, phi)
    return _perp_intensity(N, rhat)


def _perp_intensity(N, rhat) -> float:
    ndotr = N[0] * rhat[0] + N[1] * rhat[1] + N[2] * rhat[2]
    perp = [N[i] - ndotr * rhat[i] for i in range(3)]
    return sum(abs(c) ** 2 for c in perp)


# --- ground reflection (image plane) ---------------------------------------

def perfect_ground_reflection(polarization: str, theta: float) -> complex:
    """Reflection coefficient of a *perfect* electric ground: -1 for horizontal
    polarization, +1 for vertical, at any incidence. ``theta`` is unused (kept for
    a common signature with :func:`fresnel_reflection`)."""
    del theta
    return -1.0 + 0j if polarization == "horizontal" else 1.0 + 0j


def fresnel_reflection(polarization: str, theta: float,
                       epsilon_r: float, conductivity: float = 0.0,
                       frequency_mhz: float = 0.0) -> complex:
    """Fresnel reflection coefficient of a finite ground for a wave arriving at
    zenith angle ``theta`` (measured from +z; the grazing/elevation angle is
    ``90° - theta``).

    ``epsilon_r`` is the ground's relative permittivity and ``conductivity`` its
    conductivity (S/m); when a conductivity and ``frequency_mhz`` are given the
    complex permittivity ``eps = epsilon_r - j*sigma/(omega eps0)`` is used, else
    a lossless dielectric. ``polarization`` is "horizontal" or "vertical". As
    ``epsilon_r -> inf`` (or with a huge conductivity) this tends to the
    perfect-ground values -1 / +1.
    """
    eps0 = 8.854_187_8128e-12
    eps = complex(epsilon_r)
    if conductivity > 0.0 and frequency_mhz > 0.0:
        omega = _TWO_PI * frequency_mhz * 1e6
        eps = epsilon_r - 1j * conductivity / (omega * eps0)
    # Grazing angle psi from the horizon; sin/cos of the incidence measured from
    # the surface. cos of the zenith angle is the vertical component.
    cz = math.cos(theta)                # = sin(grazing angle)
    sz = math.sin(theta)                # = cos(grazing angle)
    root = cmath.sqrt(eps - sz * sz)
    if polarization == "horizontal":
        return (cz - root) / (cz + root)
    # vertical
    return (eps * cz - root) / (eps * cz + root)


class Ground:
    """A horizontal reflecting ground plane at ``z = 0`` for the image model.

    ``kind`` is "perfect" (PEC image, Gamma = -/+1) or "finite" (Fresnel Gamma
    from ``epsilon_r`` / ``conductivity``). :meth:`gamma` returns the reflection
    coefficient for a given polarization and observation zenith angle ``theta``.
    """
    __slots__ = ("kind", "epsilon_r", "conductivity", "frequency_mhz")

    def __init__(self, kind: str = "perfect", epsilon_r: float = 13.0,
                 conductivity: float = 0.005, frequency_mhz: float = 0.0):
        if kind not in ("perfect", "finite"):
            raise ValueError("ground kind must be 'perfect' or 'finite'")
        self.kind = kind
        self.epsilon_r = float(epsilon_r)
        self.conductivity = float(conductivity)
        self.frequency_mhz = float(frequency_mhz)

    def gamma(self, polarization: str, theta: float) -> complex:
        if self.kind == "perfect":
            return perfect_ground_reflection(polarization, theta)
        return fresnel_reflection(polarization, theta, self.epsilon_r,
                                  self.conductivity, self.frequency_mhz)


def radiation_vector_ground(wires, result, theta: float, phi: float,
                            ground: Ground):
    """Radiation vector over a horizontal ground at ``z = 0`` by image theory.

    The real structure (assumed at ``z >= 0``) is superposed with its image in the
    ground plane: every source element at ``(x, y, z)`` gets an image at
    ``(x, y, -z)`` whose horizontal current is negated and vertical current kept,
    scaled by the ground reflection coefficient (``-1`` horizontal / ``+1``
    vertical for a perfect ground; Fresnel for a finite one). Only the upper
    hemisphere (``theta <= pi/2``) has a field; below ground the total is zero.

    Returns ``(N, rhat)`` like :func:`radiation_vector`.
    """
    k = _TWO_PI
    rhat = (math.sin(theta) * math.cos(phi),
            math.sin(theta) * math.sin(phi),
            math.cos(theta))
    # Below the horizon there is no field over a ground plane.
    if theta > math.pi / 2.0 + 1e-12:
        return [0j, 0j, 0j], rhat
    gamma_h = ground.gamma("horizontal", theta)
    gamma_v = ground.gamma("vertical", theta)
    all_segs, seg_arms = _segment_currents(wires, result)
    N = [0j, 0j, 0j]
    for wi, segs in enumerate(all_segs):
        for si, seg in enumerate(segs):
            ln = seg.length
            mid = 0.5 * ln
            i_seg = 0j
            for (mode, coeff) in seg_arms[wi][si]:
                f, _ = _f_and_df(mode, mid, ln, k)
                i_seg += coeff * f
            if i_seg == 0j:
                continue
            rmid = _lerp(seg.p, seg.q, 0.5)
            t = seg.tangent
            # real element
            phase = cmath.exp(1j * k * _dot(rhat, rmid))
            wr = i_seg * ln * phase
            N[0] += wr * t[0]
            N[1] += wr * t[1]
            N[2] += wr * t[2]
            # image element at z -> -z; horizontal current negated (x,x Gamma_h),
            # vertical current kept (Gamma_v). The phase uses the mirrored point.
            r_img = (rmid[0], rmid[1], -rmid[2])
            phase_i = cmath.exp(1j * k * _dot(rhat, r_img))
            wi_img = i_seg * ln * phase_i
            N[0] += wi_img * (gamma_h * t[0])
            N[1] += wi_img * (gamma_h * t[1])
            N[2] += wi_img * (gamma_v * t[2])
    return N, rhat


def far_field_intensity_ground(wires, result, theta: float, phi: float,
                               ground: Ground) -> float:
    """Relative radiation intensity over a ground plane (image model). Zero below
    the horizon; see :func:`radiation_vector_ground`."""
    N, rhat = radiation_vector_ground(wires, result, theta, phi, ground)
    return _perp_intensity(N, rhat)


def front_to_back_db(wires, result, theta: float = math.pi / 2,
                     front_phi: float = 0.0) -> float:
    """Front-to-back ratio in dB: intensity toward ``front_phi`` over the opposite
    azimuth (both at elevation ``theta``). Positive means the array beams forward.
    Free space."""
    front = far_field_intensity(wires, result, theta, front_phi)
    back = far_field_intensity(wires, result, theta, front_phi + math.pi)
    if back <= 0.0:
        return float("inf")
    return 10.0 * math.log10(front / back)


def pattern_cut(wires, result, plane: str = "azimuth", count: int = 361,
                decibels: bool = True, fixed_phi: float = 0.0,
                floor_db: float = -40.0, ground: Ground | None = None):
    """A principal-plane radiation cut as ``[(angle_rad, value)]`` samples.

    Sweeps the field over one plane and returns normalised values suitable for a
    polar plot (see :func:`abax.core.science.antenna`):

    * ``plane="azimuth"`` sweeps ``phi`` in [0, 2π) at ``theta = π/2`` (the array
      plane), so ``angle`` is the azimuth.
    * ``plane="elevation"`` sweeps ``theta`` in [0, 2π) at ``phi = fixed_phi``, so
      ``angle`` is measured from the antenna (z) axis.

    ``value`` is field magnitude (√intensity) normalised to a peak of 1 when
    ``decibels`` is False, otherwise 0..1 mapped from ``floor_db``..0 dB (matching
    :func:`antenna.pattern_samples`).

    With ``ground=None`` this is **free space**: the elevation cut is symmetric
    about the horizon and is *not* an over-ground take-off pattern. Pass a
    :class:`Ground` to fold in the image-plane reflection; the elevation cut then
    shows a real take-off angle (and is zero below the horizon).
    """
    if plane not in ("azimuth", "elevation"):
        raise ValueError("plane must be 'azimuth' or 'elevation'")
    if count < 2:
        raise ValueError("count must be >= 2")

    def intensity(theta, phi):
        if ground is None:
            return far_field_intensity(wires, result, theta, phi)
        return far_field_intensity_ground(wires, result, theta, phi, ground)

    raw = []
    peak = 0.0
    for i in range(count):
        angle = _TWO_PI * i / (count - 1)
        if plane == "azimuth":
            u = intensity(math.pi / 2.0, angle)
        else:
            u = intensity(angle, fixed_phi)
        mag = math.sqrt(max(0.0, u))
        peak = max(peak, mag)
        raw.append((angle, mag))
    if peak <= 0.0:
        return [(angle, 0.0) for angle, _ in raw]
    out = []
    for angle, mag in raw:
        lin = mag / peak
        if decibels:
            db = 20.0 * math.log10(lin) if lin > 1e-6 else floor_db
            lin = max(0.0, (db - floor_db) / (-floor_db))
        out.append((angle, lin))
    return out


def pattern_to_rows(samples, decibels: bool = True):
    """Turn ``pattern_cut`` samples into ``(headers, rows)`` of cell text.

    ``headers`` is ``["Angle (deg)", "Gain (norm)"]`` (or ``"Gain (0..1 dB)"`` when
    ``decibels``); each row is ``(angle_deg, value)`` as strings ready to drop into
    a sheet. The angle is the sample angle converted to degrees."""
    label = "Gain (0..1 dB)" if decibels else "Gain (norm)"
    headers = ["Angle (deg)", label]
    rows = [(f"{math.degrees(angle):.1f}", f"{value:.4f}")
            for angle, value in samples]
    return headers, rows


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


def monopole_over_ground(length_wl: float, radius_wl: float = 1e-3,
                         segments: int = 12):
    """Build and solve a base-fed vertical monopole standing on ``z = 0``.

    Returns ``(wires, result, feed_node, ground)`` where ``ground`` is a perfect
    :class:`Ground`. The monopole is modelled together with its image as a
    driven wire from ``z = -length`` to ``z = +length`` (a dipole whose lower half
    is the image), fed at the ``z = 0`` node; the upper half is the physical
    monopole and the pattern is read over the ground so the main lobe sits at a
    low take-off angle. ``feed_node`` is the centre (base) node.
    """
    n = max(2, segments + (segments & 1))
    dz = length_wl / (n // 2)
    # Nodes span -length .. +length with a node exactly at z = 0 (the base).
    half_nodes = n // 2
    zs = [(-half_nodes + i) * dz for i in range(2 * half_nodes + 1)]
    points = [(0.0, 0.0, z) for z in zs]
    feed_node = half_nodes                          # z = 0
    res = solve([points], [(0, feed_node, 1.0)], radius=radius_wl)
    return [points], res, feed_node, Ground("perfect")


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
