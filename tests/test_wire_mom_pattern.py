"""Radiation-pattern read-back for the general wire MoM (wire_mom.pattern_cut).

A dipole azimuth cut is (near-)omnidirectional; a 3-element Yagi has a clear
forward lobe; pattern_to_rows produces a well-shaped table.
"""

from __future__ import annotations

import math

import pytest

from abax.core.science import wire_mom as W


def _dipole_wire(length, segments):
    n = segments if segments % 2 == 0 else segments + 1
    half = length / 2.0
    dz = length / n
    return [(0.0, 0.0, -half + i * dz) for i in range(n + 1)], n


def test_azimuth_cut_of_dipole_is_omnidirectional():
    # A z-directed dipole is independent of azimuth: the azimuth cut (theta=90)
    # is a circle, so every normalised sample sits at the peak.
    pts, n = _dipole_wire(0.5, 12)
    res = W.solve([pts], [(0, n // 2, 1.0)], radius=1e-3)
    samples = W.pattern_cut([pts], res, plane="azimuth", count=73, decibels=False)
    assert len(samples) == 73
    vals = [v for _a, v in samples]
    assert max(vals) == pytest.approx(1.0, abs=1e-9)
    # Omnidirectional: the spread between min and max is negligible.
    assert max(vals) - min(vals) < 1e-6


def test_elevation_cut_of_dipole_has_endfire_nulls():
    # The elevation cut (sweep theta) of a z dipole nulls along the axis
    # (theta = 0 and pi) and peaks broadside (theta = pi/2).
    pts, n = _dipole_wire(0.5, 12)
    res = W.solve([pts], [(0, n // 2, 1.0)], radius=1e-3)
    samples = W.pattern_cut([pts], res, plane="elevation", count=361, decibels=False)
    by_deg = {round(math.degrees(a)): v for a, v in samples}
    assert by_deg[90] == pytest.approx(1.0, abs=1e-6)      # broadside peak
    assert by_deg[0] < 0.05                                # axial null
    assert by_deg[180] < 0.05


def test_yagi_azimuth_cut_has_forward_lobe():
    def elem(length, x, seg=8):
        n = seg if seg % 2 == 0 else seg + 1
        half = length / 2.0
        dz = length / n
        return [(x, 0.0, -half + i * dz) for i in range(n + 1)]

    # reflector behind (-x), driven at 0, director ahead (+x): beams toward +x
    wires = [elem(0.47, 0.0), elem(0.5, -0.25), elem(0.45, 0.15)]
    feed = 8 // 2
    res = W.solve(wires, [(0, feed, 1.0)], radius=1e-3)
    samples = W.pattern_cut(wires, res, plane="azimuth", count=361, decibels=False)
    by_deg = {round(math.degrees(a)): v for a, v in samples}
    # +x is phi = 0 (forward); -x is phi = 180 (back). Forward should dominate.
    assert by_deg[0] == pytest.approx(1.0, abs=1e-6)       # peak points forward
    assert by_deg[0] > 1.5 * by_deg[180]                   # real front/back ratio


def test_pattern_to_rows_shape():
    pts, n = _dipole_wire(0.5, 8)
    res = W.solve([pts], [(0, n // 2, 1.0)], radius=1e-3)
    samples = W.pattern_cut([pts], res, plane="azimuth", count=19, decibels=True)
    headers, rows = W.pattern_to_rows(samples, decibels=True)
    assert headers[0] == "Angle (deg)"
    assert "dB" in headers[1]
    assert len(rows) == len(samples) == 19
    assert all(len(r) == 2 for r in rows)
    # First angle is 0 deg; every cell is a string.
    assert rows[0][0] == "0.0"
    assert all(isinstance(c, str) for r in rows for c in r)


def test_pattern_to_rows_linear_header():
    samples = [(0.0, 1.0), (math.pi, 0.5)]
    headers, rows = W.pattern_to_rows(samples, decibels=False)
    assert headers[1] == "Gain (norm)"
    assert rows[1][0] == "180.0"


def test_pattern_cut_validation():
    pts, n = _dipole_wire(0.5, 8)
    res = W.solve([pts], [(0, n // 2, 1.0)], radius=1e-3)
    with pytest.raises(ValueError):
        W.pattern_cut([pts], res, plane="broadside")
    with pytest.raises(ValueError):
        W.pattern_cut([pts], res, plane="azimuth", count=1)


def test_decibels_mapping_is_zero_to_one():
    pts, n = _dipole_wire(0.5, 8)
    res = W.solve([pts], [(0, n // 2, 1.0)], radius=1e-3)
    samples = W.pattern_cut([pts], res, plane="elevation", count=181, decibels=True)
    vals = [v for _a, v in samples]
    assert max(vals) == pytest.approx(1.0, abs=1e-9)       # peak maps to 1
    assert min(vals) >= 0.0                                # floor clamps at 0
