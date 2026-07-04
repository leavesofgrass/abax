"""Multi-wire MoM junctions: wires that share an endpoint enforce Kirchhoff
current continuity at the shared node, so verticals-with-radials, loops and fed
T-junctions solve (no singular matrix) and conserve current at the junction.

The physics oracle here is Kirchhoff's current law: the net current flowing into
any junction node must be zero. We reconstruct the segment currents at the node
and check the signed sum vanishes to machine precision. We also check the classic
single-wire results are unchanged (the degree-2 interior node reduces to the old
before/after basis), so the junction machinery does not perturb a plain dipole.
"""

from __future__ import annotations

import math

import pytest

from abax.core.science import wire_mom as W


def _net_current_into_node(wires, result, node_point):
    """Signed sum of the segment currents flowing INTO ``node_point`` (KCL residual).

    For every segment end that touches the node, the current arriving is the
    segment's midpoint-free amplitude at the node (``f = 1`` there) times its
    into-node sign (+1 when the node is the segment's ``.q``, -1 when it is the
    ``.p``). KCL says this sums to zero."""
    key = W._node_key(node_point)
    incident, _ = W._incident_arms(wires)
    _all_segs, seg_arms = W._segment_currents(wires, result)
    net = 0j
    for (seg, mode, at_q, wi, si) in incident[key]:
        i_at_node = sum(sc for (m, sc) in seg_arms[wi][si] if m == mode)
        net += i_at_node * (1 if at_q else -1)
    return net


def test_t_junction_solves_without_singular_matrix():
    # A fed vertical wire whose top meets a horizontal crossbar: three wires share
    # the top node -> a degree-3 junction. It must solve (the old code would pin
    # the shared node to zero current; a genuine junction does not).
    vert = [(0.0, 0.0, z) for z in (0.0, 0.05, 0.10, 0.15, 0.20, 0.25)]
    bar_l = [(0.0, y, 0.25) for y in (-0.15, -0.10, -0.05, 0.0)]
    bar_r = [(0.0, y, 0.25) for y in (0.0, 0.05, 0.10, 0.15)]
    wires = [vert, bar_l, bar_r]
    res = W.solve(wires, [(0, 1, 1.0)], radius=1e-3)   # feed a vertical interior node
    assert res["n_basis"] > 0
    zin = res["feed_impedance"][(0, 1)]
    assert math.isfinite(zin.real) and math.isfinite(zin.imag)
    assert zin.real != 0.0


def test_t_junction_conserves_current_at_node():
    vert = [(0.0, 0.0, z) for z in (0.0, 0.05, 0.10, 0.15, 0.20, 0.25)]
    bar_l = [(0.0, y, 0.25) for y in (-0.15, -0.10, -0.05, 0.0)]
    bar_r = [(0.0, y, 0.25) for y in (0.0, 0.05, 0.10, 0.15)]
    wires = [vert, bar_l, bar_r]
    res = W.solve(wires, [(0, 1, 1.0)], radius=1e-3)
    # Kirchhoff current law at the shared top node: net current in ~ 0.
    net = _net_current_into_node(wires, res, (0.0, 0.0, 0.25))
    # There is real current flowing through the junction (it is not the trivial
    # all-zero solution), yet the node conserves it.
    _all_segs, seg_arms = W._segment_currents(wires, res)
    some_current = max(abs(sc) for row in seg_arms for arms in row for _m, sc in arms)
    assert some_current > 1e-6
    assert abs(net) < 1e-9 * max(1.0, some_current)


def test_vertical_with_radials_solves_and_conserves():
    # A base-fed vertical over four ground radials meeting at the base node (a
    # degree-5 junction: the vertical plus four radials). Solve at the base.
    n = 5
    dz = 0.25 / n
    vert = [(0.0, 0.0, i * dz) for i in range(n + 1)]        # base at (0,0,0)
    radials = []
    for (dx, dy) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        # radial runs outward from the base node (0,0,0)
        pts = [(0.0, 0.0, 0.0)] + [(dx * j * 0.05, dy * j * 0.05, 0.0)
                                   for j in range(1, 6)]
        radials.append(pts)
    wires = [vert, *radials]
    # feed the vertical just above the base (interior node 1)
    res = W.solve(wires, [(0, 1, 1.0)], radius=1e-3)
    zin = res["feed_impedance"][(0, 1)]
    assert math.isfinite(zin.real) and math.isfinite(zin.imag)
    net = _net_current_into_node(wires, res, (0.0, 0.0, 0.0))
    _all_segs, seg_arms = W._segment_currents(wires, res)
    some_current = max(abs(sc) for row in seg_arms for arms in row for _m, sc in arms)
    assert some_current > 1e-6
    assert abs(net) < 1e-9 * max(1.0, some_current)


def test_closed_loop_solves_and_conserves_at_every_node():
    # A one-wavelength square loop (a closed polyline whose last point equals the
    # first) is one wire that forms junctions with itself at the shared corner and
    # is fully connected: current is continuous all the way round. Feed one side.
    side = 0.25
    corners = [(0.0, 0.0, 0.0), (side, 0.0, 0.0), (side, side, 0.0),
               (0.0, side, 0.0)]
    # subdivide each side so there are interior nodes, and close the loop.
    pts = []
    ring = corners + [corners[0]]
    for a, b in zip(ring, ring[1:]):
        for t in (0.0, 0.25, 0.5, 0.75):
            pts.append((a[0] + (b[0] - a[0]) * t,
                        a[1] + (b[1] - a[1]) * t,
                        a[2] + (b[2] - a[2]) * t))
    pts.append(corners[0])                              # close the loop
    wires = [pts]
    res = W.solve(wires, [(0, 1, 1.0)], radius=1e-3)
    assert math.isfinite(res["feed_impedance"][(0, 1)].real)
    # The closing corner is a junction of the loop with itself: KCL must hold.
    net = _net_current_into_node(wires, res, corners[0])
    _all_segs, seg_arms = W._segment_currents(wires, res)
    some_current = max(abs(sc) for row in seg_arms for arms in row for _m, sc in arms)
    assert some_current > 1e-6
    assert abs(net) < 1e-9 * max(1.0, some_current)


def test_single_wire_dipole_unchanged_by_junction_machinery():
    # A lone dipole has no shared endpoints, so it must give exactly the same
    # impedance the dedicated collinear solver reports (the degree-2 interior node
    # reduces to the classic before/after basis).
    from abax.core.science import mom

    for length in (0.5, 0.3):
        zw = W.dipole(length, 1e-3, segments=12)
        zm = mom.solve_dipole(length, 1e-3, segments=12,
                              quad=16)["input_impedance"]
        assert zw.real == pytest.approx(zm.real, abs=1e-4)
        assert zw.imag == pytest.approx(zm.imag, abs=1e-4)


def test_disjoint_wires_have_no_junction():
    # Two dipoles that do NOT touch keep their own interior bases; each free end
    # carries no basis (current zero), so the node count is 2*(interior nodes).
    d1 = [(0.0, 0.0, z) for z in (-0.25, -0.125, 0.0, 0.125, 0.25)]
    d2 = [(0.5, 0.0, z) for z in (-0.25, -0.125, 0.0, 0.125, 0.25)]
    res = W.solve([d1, d2], [(0, 2, 1.0)], radius=1e-3)
    # 3 interior nodes per 4-segment wire -> 6 bases, no junction bases.
    assert res["n_basis"] == 6
