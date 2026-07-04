"""PyNEC radiation-pattern read-back (necpy.pattern_cut): validation order and
graceful absence.

These tests must pass WITHOUT PyNEC installed. They mirror the solve_deck tests:
the stdlib parse/validate path always runs and the real read-back raises
PyNecUnavailable when PyNEC is absent. If PyNEC is present, the returned samples
have the built-in cut's ``[(angle, value)]`` shape.
"""

from __future__ import annotations

import math

import pytest

from abax.engine import necpy

DIPOLE_DECK = """CM dipole
CE
GW 1 9 -0.25 0 0 0.25 0 0 0.001
GE 0
EX 0 1 5 0 1 0
FR 0 1 0 0 300 0
EN
"""


def test_pattern_cut_exposed():
    assert hasattr(necpy, "pattern_cut")


def test_pattern_cut_requires_pynec_or_returns_samples():
    if not necpy.available():
        with pytest.raises(necpy.PyNecUnavailable):
            necpy.pattern_cut(DIPOLE_DECK, plane="azimuth", count=37)
    else:
        samples = necpy.pattern_cut(DIPOLE_DECK, plane="azimuth", count=37)
        assert len(samples) == 37
        assert all(len(s) == 2 for s in samples)
        angles = [a for a, _v in samples]
        vals = [v for _a, v in samples]
        assert angles[0] == pytest.approx(0.0)
        assert angles[-1] == pytest.approx(2.0 * math.pi, abs=1e-9)
        assert max(vals) == pytest.approx(1.0, abs=1e-6)   # normalised peak
        assert min(vals) >= 0.0


def test_pattern_cut_validation_before_pynec():
    # Bad plane / count are caught up front regardless of PyNEC presence.
    with pytest.raises(ValueError):
        necpy.pattern_cut(DIPOLE_DECK, plane="broadside")
    with pytest.raises(ValueError):
        necpy.pattern_cut(DIPOLE_DECK, plane="azimuth", count=1)


def test_pattern_cut_empty_deck_raises_valueerror():
    # Geometry validation happens before the PyNEC availability check.
    with pytest.raises(ValueError):
        necpy.pattern_cut("", plane="azimuth")


def test_pattern_cut_without_excitation_raises_valueerror():
    no_ex = """CM no feed
CE
GW 1 9 -0.25 0 0 0.25 0 0 0.001
GE 0
FR 0 1 0 0 300 0
EN
"""
    with pytest.raises(ValueError):
        necpy.pattern_cut(no_ex, plane="azimuth")


def test_flatten_gain_helpers():
    # The grid flatteners are pure and testable without PyNEC.
    flat = necpy._flatten_gain([[0.0, -3.0, -6.0]], 3)
    assert flat == [0.0, -3.0, -6.0]
    # A single value pads out to length.
    padded = necpy._flatten_gain([-2.0], 4)
    assert len(padded) == 4


def test_gain_db_to_samples_normalises_peak():
    # 0 dBi peak -> value 1.0; -40 dB -> 0.0 with the default floor.
    gain_db = [0.0, -40.0, -20.0]
    samples = necpy._gain_db_to_samples(gain_db, "azimuth", 3, 0.0,
                                        decibels=True, floor_db=-40.0)
    vals = [v for _a, v in samples]
    assert vals[0] == pytest.approx(1.0)
    assert vals[1] == pytest.approx(0.0)
    assert vals[2] == pytest.approx(0.5)
