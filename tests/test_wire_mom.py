"""General 3-D multi-wire MoM: matches the dedicated dipole solver, gives the
right dipole pattern, and a Yagi that actually beams forward."""

from __future__ import annotations

import math

import pytest

from abax.core.science import mom
from abax.core.science import wire_mom as W


def _dipole_wire(length, segments):
    n = segments if segments % 2 == 0 else segments + 1
    half = length / 2.0
    dz = length / n
    return [(0.0, 0.0, -half + i * dz) for i in range(n + 1)], n


def test_general_solver_reproduces_dedicated_dipole():
    for length in (0.5, 0.3):
        zw = W.dipole(length, 1e-3, segments=12)
        zm = mom.solve_dipole(length, 1e-3, segments=12, quad=16)["input_impedance"]
        assert zw.real == pytest.approx(zm.real, abs=1e-4)
        assert zw.imag == pytest.approx(zm.imag, abs=1e-4)


def test_dipole_pattern_is_figure_eight():
    pts, n = _dipole_wire(0.5, 12)
    res = W.solve([pts], [(0, n // 2, 1.0)], radius=1e-3)
    broadside = W.far_field_intensity([pts], res, math.pi / 2, 0.0)
    endfire = W.far_field_intensity([pts], res, 0.02, 0.0)
    assert broadside > 1000 * endfire                     # deep end-fire null
    # axial symmetry: a z-directed dipole is independent of azimuth
    e0 = W.far_field_intensity([pts], res, math.pi / 2, 0.0)
    e90 = W.far_field_intensity([pts], res, math.pi / 2, math.pi / 2)
    assert e0 == pytest.approx(e90, rel=1e-9)


def test_symmetric_dipole_current_is_symmetric():
    pts, n = _dipole_wire(0.5, 12)
    res = W.solve([pts], [(0, n // 2, 1.0)], radius=1e-3)
    cur = res["current"]
    m = len(cur)
    for i in range(m // 2):
        assert cur[i] == pytest.approx(cur[m - 1 - i], rel=1e-6)


def test_yagi_beams_forward():
    # reflector behind (-x), driven at 0, one director ahead (+x)
    def elem(length, x, seg=8):
        n = seg if seg % 2 == 0 else seg + 1
        half = length / 2.0
        dz = length / n
        return [(x, 0.0, -half + i * dz) for i in range(n + 1)]

    wires = [elem(0.47, 0.0), elem(0.5, -0.25), elem(0.45, 0.15)]
    feed_node = 8 // 2
    res = W.solve(wires, [(0, feed_node, 1.0)], radius=1e-3)
    z = res["feed_impedance"][(0, feed_node)]
    assert 10.0 < z.real < 90.0                            # coupling pulls R down
    fb = W.front_to_back_db(wires, res, front_phi=0.0)     # +x is the director side
    assert fb > 3.0                                        # several dB forward gain


def test_validation_errors():
    with pytest.raises(ValueError):
        W.solve([[(0, 0, 0), (0, 0, 0.5)]], [], radius=0.0)
    with pytest.raises(ValueError):
        W.solve([[(0, 0, 0), (0, 0, 0.5)]], [(0, 0, 1.0)])   # no interior node
    with pytest.raises(ValueError):
        W.solve([[(0, 0, 0)]], [])                            # wire needs >= 2 pts
