"""Analytic antenna patterns — validated against antenna theory."""

from __future__ import annotations

import math

import pytest

from abax.core.science import antenna


def test_isotropic_is_unity_directivity():
    assert antenna.directivity(lambda _t: 1.0) == pytest.approx(1.0, abs=2e-3)
    assert antenna.gain_dbi(lambda _t: 1.0) == pytest.approx(0.0, abs=0.05)


def test_half_wave_dipole_gain_and_beamwidth():
    f = antenna.half_wave_dipole()
    assert antenna.gain_dbi(f) == pytest.approx(2.15, abs=0.05)        # 1.64 -> 2.15 dBi
    assert antenna.half_power_beamwidth(f) == pytest.approx(78.0, abs=2.0)


def test_full_wave_beats_half_wave_gain():
    assert antenna.gain_dbi(antenna.full_wave_dipole()) > antenna.gain_dbi(
        antenna.half_wave_dipole())


def test_array_factor_peak_is_n():
    assert antenna.array_factor(math.pi / 2, 4, 0.5, 0.0) == pytest.approx(4.0)
    assert antenna.array_factor(math.pi / 2, 8, 0.25, 0.0) == pytest.approx(8.0)
    with pytest.raises(ValueError):
        antenna.array_factor(1.0, 0, 0.5)


def test_array_directivity_increases_with_elements():
    g2 = antenna.gain_dbi(antenna.linear_array(2, 0.5))
    g4 = antenna.gain_dbi(antenna.linear_array(4, 0.5))
    assert g4 > g2 > 0.0


def test_pattern_samples_normalised():
    s = antenna.pattern_samples(antenna.half_wave_dipole(), count=181)
    assert len(s) == 181
    mags = [m for _, m in s]
    assert max(mags) == pytest.approx(1.0)
    assert all(0.0 <= m <= 1.0 for m in mags)
    sdb = antenna.pattern_samples(antenna.half_wave_dipole(), count=181, decibels=True)
    assert all(0.0 <= m <= 1.0 for _, m in sdb)


def test_polar_svg():
    from abax.core.science import antenna
    samples = antenna.pattern_samples(antenna.half_wave_dipole(), count=181)
    svg = antenna.polar_svg(samples, title="Half-wave dipole")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "<path" in svg                       # the pattern curve
    assert svg.count("<circle") == 4            # amplitude rings
    assert "Half-wave dipole" in svg
    assert antenna.polar_svg([], title="empty").count("<path") == 0
