"""NEC .nec deck I/O: round-trip, hand-written parsing, and frequency scaling."""

from __future__ import annotations

import math

import pytest

from abax.core.science import nec
from abax.core.science import wire_mom as W


def _dipole_pts(segments=16, length=0.5):
    half = length / 2.0
    dz = length / segments
    return [(0.0, 0.0, -half + i * dz) for i in range(segments + 1)]


def test_roundtrip_write_parse_solve():
    pts = _dipole_pts(16)
    deck = nec.to_nec([pts], [(0, 8, 1.0)], 14.0, radii_wl=[1e-3])
    assert "GW 1 16" in deck and "EX 0 1 8" in deck and "FR 0 1 0 0 14" in deck

    model = nec.parse_nec(deck)
    assert len(model.wires) == 1
    assert model.frequency_mhz == 14.0
    assert model.feeds == [(0, 8, 1 + 0j)]
    assert model.radii_wl[0] == pytest.approx(1e-3, rel=1e-4)   # %.6g round-trip
    # geometry scaled back to wavelengths: total length ~0.5 wl
    span = model.wires[0][-1][2] - model.wires[0][0][2]
    assert span == pytest.approx(0.5, rel=1e-4)

    z = list(nec.solve(model)["feed_impedance"].values())[0]
    direct = W.dipole(0.5, 1e-3, segments=16)
    assert z.real == pytest.approx(direct.real, abs=1e-3)
    assert z.imag == pytest.approx(direct.imag, abs=1e-3)


def test_parse_handwritten_deck_with_comments_and_ignored_cards():
    deck = """CM Half-wave dipole, 21 MHz
CE
GW 1, 21, 0, 0, -3.4, 0, 0, 3.4, 0.01
GE 0
GN 1
EX 0 1 11 0 1.0 0
FR 0 1 0 0 21.0 0
EN
"""
    m = nec.parse_nec(deck)
    assert len(m.wires) == 1
    assert m._seg_counts[0] == 21
    assert m.frequency_mhz == 21.0
    assert m.feeds[0][0] == 0 and m.feeds[0][2] == 1 + 0j
    assert "GN" in m.ignored                       # ground card noted, not fatal
    assert m.comments and "dipole" in m.comments[0]


def test_frequency_scaling_to_wavelengths():
    # lambda = 1 m exactly at this frequency, so a 1 m wire is 1 wavelength
    f = 299.792458
    deck = f"CM\nCE\nGW 1 10 0 0 -0.5 0 0 0.5 0.001\nGE 0\nEX 0 1 5 0 1 0\nFR 0 1 0 0 {f} 0\nEN\n"
    m = nec.parse_nec(deck)
    span = m.wires[0][-1][2] - m.wires[0][0][2]
    assert span == pytest.approx(1.0, rel=1e-9)    # 1 m / 1 m wavelength


def test_to_nec_splits_bent_wire_into_straight_runs():
    # an inverted-V: down one side, up the other -> two straight GW runs
    bent = [(-0.2, 0.0, -0.1), (0.0, 0.0, 0.0), (0.2, 0.0, -0.1)]
    deck = nec.to_nec([bent], [(0, 1, 1.0)], 50.0)
    gw = [ln for ln in deck.splitlines() if ln.startswith("GW")]
    assert len(gw) == 2                            # one GW per straight arm
    # parsing it back reconstructs two segments meeting at the apex
    m = nec.parse_nec(deck)
    assert len(m.wires) == 2


def test_solve_requires_frequency_and_excitation():
    no_fr = "CM\nCE\nGW 1 8 0 0 -0.25 0 0 0.25 0.001\nGE 0\nEX 0 1 4 0 1 0\nEN\n"
    with pytest.raises(ValueError):
        nec.solve(nec.parse_nec(no_fr))
    no_ex = "CM\nCE\nGW 1 8 0 0 -0.25 0 0 0.25 0.001\nGE 0\nFR 0 1 0 0 14 0\nEN\n"
    with pytest.raises(ValueError):
        nec.solve(nec.parse_nec(no_ex))


def test_pattern_from_parsed_deck():
    pts = _dipole_pts(16)
    deck = nec.to_nec([pts], [(0, 8, 1.0)], 28.0, radii_wl=[1e-3])
    m = nec.parse_nec(deck)
    res = nec.solve(m)
    broad = W.far_field_intensity(m.wires, res, math.pi / 2, 0.0)
    end = W.far_field_intensity(m.wires, res, 0.02, 0.0)
    assert broad > 1000 * end
