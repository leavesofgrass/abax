"""Image-plane ground reflection for the wire MoM.

Oracle references (image theory over a perfect electric ground, e.g. Balanis,
*Antenna Theory*, ch. 4; Kraus, *Antennas*):

* A vertical monopole/vertical dipole over perfect ground radiates only in the
  upper hemisphere (the image reinforces along the horizon), so its elevation
  pattern peaks at the horizon (~0 deg take-off) and nulls at the zenith — it is
  NOT the free-space pattern, which is symmetric about the horizon.
* A horizontal half-wave dipole a half-wavelength above perfect ground has its
  elevation main lobe near 30 deg with a null straight up (the ground image is
  out of phase for horizontal polarization, giving a factor 2*sin(k h cos theta)).
* The perfect-ground reflection coefficient is -1 for horizontal polarization and
  +1 for vertical, at every incidence; a finite-ground Fresnel coefficient tends
  to those as the permittivity grows without bound.
"""

from __future__ import annotations

import math

import pytest

from abax.core.science import wire_mom as W


def _vertical_dipole(length=0.5, height=0.0, seg=12):
    n = seg if seg % 2 == 0 else seg + 1
    half = length / 2.0
    dz = length / n
    pts = [(0.0, 0.0, height + (-half + i * dz)) for i in range(n + 1)]
    return [pts], n // 2


def _horizontal_dipole(length=0.5, height=0.5, seg=12):
    n = seg if seg % 2 == 0 else seg + 1
    half = length / 2.0
    dy = length / n
    pts = [(0.0, -half + i * dy, height) for i in range(n + 1)]
    return [pts], n // 2


def _elevation_peak_deg(wires, res, ground, phi=0.0, lo=1, hi=90):
    """Zenith angle (deg) of peak intensity scanning the upper hemisphere."""
    best_u, best = -1.0, None
    for d in range(lo, hi + 1):
        u = W.far_field_intensity_ground(wires, res, math.radians(d), phi, ground)
        if u > best_u:
            best_u, best = u, d
    return best, best_u


# --- perfect-ground reflection coefficient ---------------------------------

def test_perfect_ground_reflection_coeffs():
    for th in (0.0, math.pi / 4, math.pi / 2 - 1e-3):
        assert W.perfect_ground_reflection("horizontal", th) == pytest.approx(-1.0)
        assert W.perfect_ground_reflection("vertical", th) == pytest.approx(1.0)


def test_fresnel_tends_to_perfect_as_epsilon_grows():
    theta = math.radians(60.0)          # 30 deg elevation
    gh = W.fresnel_reflection("horizontal", theta, epsilon_r=1e9)
    gv = W.fresnel_reflection("vertical", theta, epsilon_r=1e9)
    assert gh.real == pytest.approx(-1.0, abs=1e-3)
    assert gv.real == pytest.approx(1.0, abs=1e-3)


def test_ground_kind_validation():
    with pytest.raises(ValueError):
        W.Ground("swamp")


# --- vertical monopole over perfect ground: low take-off, not broadside -----

def test_vertical_monopole_main_lobe_is_low_elevation():
    wires, res, feed, ground = W.monopole_over_ground(0.25, segments=12)
    # The main lobe of a vertical monopole over perfect ground is at the horizon
    # (elevation ~0 deg), i.e. a LOW take-off angle. In zenith-angle terms the peak
    # is near 90 deg (the horizon), not at broadside-to-nothing / the zenith.
    peak_zenith, _ = _elevation_peak_deg(wires, res, ground)
    take_off_deg = 90 - peak_zenith
    assert take_off_deg < 15.0                          # low take-off angle

    # Low-angle radiation dominates high-angle radiation (a "DX" pattern), which a
    # free-space symmetric dipole cut would NOT show.
    low = W.far_field_intensity_ground(wires, res, math.radians(80), 0.0, ground)   # 10 deg elev
    high = W.far_field_intensity_ground(wires, res, math.radians(10), 0.0, ground)  # 80 deg elev
    assert low > 10.0 * high

    # Deep null toward the zenith (straight up), unlike free space.
    zenith = W.far_field_intensity_ground(wires, res, math.radians(0.5), 0.0, ground)
    horizon = W.far_field_intensity_ground(wires, res, math.radians(89.5), 0.0, ground)
    assert zenith < 0.01 * horizon


def test_no_field_below_the_horizon():
    wires, res, feed, ground = W.monopole_over_ground(0.25, segments=12)
    for zen in (91.0, 135.0, 179.0):                    # below the ground plane
        u = W.far_field_intensity_ground(wires, res, math.radians(zen), 0.0, ground)
        assert u == 0.0


def test_monopole_input_impedance_is_half_the_dipole():
    # A quarter-wave monopole over perfect ground has half the input impedance of
    # the equivalent half-wave dipole (image theory). Our model returns the
    # dipole-equivalent impedance; halved it lands near the textbook ~36 + j21 Ω.
    wires, res, feed, _ground = W.monopole_over_ground(0.25, segments=16)
    z_dipole = res["feed_impedance"][(0, feed)]
    z_monopole = z_dipole / 2.0
    assert 30.0 < z_monopole.real < 55.0
    assert 5.0 < z_monopole.imag < 40.0                 # inductive (near resonance)


# --- horizontal dipole at half-wave height: 30 deg lobe, zenith null --------

def test_horizontal_dipole_half_wave_height_peaks_off_zenith():
    wires, feed = _horizontal_dipole(length=0.5, height=0.5)
    res = W.solve(wires, [(0, feed, 1.0)], radius=1e-3)
    ground = W.Ground("perfect")
    # The elevation cut is taken in the plane perpendicular to the wire (phi=0,
    # the x-z plane). A half-wave-high horizontal dipole peaks near 30 deg
    # elevation with a null straight up.
    peak_zenith, _ = _elevation_peak_deg(wires, res, ground, phi=0.0)
    take_off = 90 - peak_zenith
    assert 20.0 < take_off < 40.0                       # ~30 deg, NOT broadside
    zenith = W.far_field_intensity_ground(wires, res, math.radians(0.5), 0.0, ground)
    peak = W.far_field_intensity_ground(
        wires, res, math.radians(peak_zenith), 0.0, ground)
    assert zenith < 0.02 * peak                         # deep zenith null


def test_low_horizontal_dipole_fires_straight_up():
    # A quarter-wave-high horizontal dipole (NVIS) instead peaks toward the zenith.
    wires, feed = _horizontal_dipole(length=0.5, height=0.25)
    res = W.solve(wires, [(0, feed, 1.0)], radius=1e-3)
    ground = W.Ground("perfect")
    peak_zenith, _ = _elevation_peak_deg(wires, res, ground, phi=0.0)
    assert (90 - peak_zenith) > 60.0                     # high-angle / straight up


# --- pattern_cut with a ground and the free-space invariance ----------------

def test_pattern_cut_ground_elevation_is_asymmetric_and_zero_below():
    wires, res, feed, ground = W.monopole_over_ground(0.25, segments=12)
    samples = W.pattern_cut(wires, res, plane="elevation", count=361,
                            decibels=False, ground=ground)
    by_deg = {round(math.degrees(a)): v for a, v in samples}
    # Peak near the horizon (theta ~ 90 deg), essentially nothing below it.
    assert by_deg[90] == pytest.approx(1.0, abs=1e-6)
    assert by_deg[135] < 1e-9                            # below the horizon
    assert by_deg[225] < 1e-9


def test_ground_none_matches_free_space_path():
    # Passing ground=None must reproduce the classic free-space cut byte-for-byte.
    wires, feed = _vertical_dipole(0.5, height=0.0)
    res = W.solve(wires, [(0, feed, 1.0)], radius=1e-3)
    a = W.pattern_cut(wires, res, plane="elevation", count=181, decibels=True)
    b = W.pattern_cut(wires, res, plane="elevation", count=181, decibels=True,
                      ground=None)
    assert a == b


def test_finite_ground_raises_take_off_angle():
    # Real earth (finite conductivity) pushes the vertical's take-off angle up off
    # the horizon (the vertical-polarization reflection collapses near grazing).
    wires, res, feed, _g = W.monopole_over_ground(0.25, segments=12)
    earth = W.Ground("finite", epsilon_r=13.0, conductivity=0.005,
                     frequency_mhz=14.0)
    peak_zenith, _ = _elevation_peak_deg(wires, res, earth)
    take_off = 90 - peak_zenith
    assert take_off > 10.0                               # lifted off the horizon
