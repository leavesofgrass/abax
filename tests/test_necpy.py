"""PyNEC adapter (abax.engine.necpy): validation order and graceful absence.

These tests must pass WITHOUT PyNEC installed. They cover the always-on stdlib
parse/validate/serialise path and assert that the real solve path raises
PyNecUnavailable when PyNEC is absent (and, if PyNEC is somehow present, that the
result dict is well-formed).
"""

from __future__ import annotations

import pytest

from abax.core.science import nec
from abax.engine import necpy

DIPOLE_DECK = """CM dipole
CE
GW 1 9 -0.25 0 0 0.25 0 0 0.001
GE 0
EX 0 1 5 0 1 0
FR 0 1 0 0 300 0
EN
"""


def test_import_layering_without_pynec():
    # Module imports cleanly even with PyNEC absent, and exposes the API.
    import abax.engine.necpy as mod

    assert hasattr(mod, "solve_deck")
    assert hasattr(mod, "solve_model")
    assert hasattr(mod, "available")
    assert issubclass(mod.PyNecUnavailable, RuntimeError)


def test_available_returns_bool():
    result = necpy.available()
    assert isinstance(result, bool)


def test_solve_deck_requires_pynec_or_returns_result():
    if not necpy.available():
        with pytest.raises(necpy.PyNecUnavailable):
            necpy.solve_deck(DIPOLE_DECK)
    else:
        out = necpy.solve_deck(DIPOLE_DECK)
        assert out["source"] == "pynec"
        assert isinstance(out["feed_impedance"], complex)
        assert out["frequency_mhz"] == pytest.approx(300.0)
        assert isinstance(out["n_segments"], int)
        assert out["n_segments"] >= 1


def test_empty_deck_raises_valueerror():
    # Geometry check happens BEFORE the availability check, so this holds
    # regardless of whether PyNEC is installed.
    with pytest.raises(ValueError):
        necpy.solve_deck("")


def test_deck_without_geometry_raises_valueerror():
    no_gw = """CM no geometry
CE
GE 0
FR 0 1 0 0 300 0
EN
"""
    with pytest.raises(ValueError):
        necpy.solve_deck(no_gw)


def test_deck_without_excitation_raises_valueerror():
    no_ex = """CM no feed
CE
GW 1 9 -0.25 0 0 0.25 0 0 0.001
GE 0
FR 0 1 0 0 300 0
EN
"""
    with pytest.raises(ValueError):
        necpy.solve_deck(no_ex)


def test_solve_model_routes_through_solve_deck():
    model = nec.parse_nec(DIPOLE_DECK)
    assert model.wires  # sanity: the dipole parsed

    if not necpy.available():
        with pytest.raises(necpy.PyNecUnavailable):
            necpy.solve_model(model)
    else:
        out = necpy.solve_model(model)
        assert out["source"] == "pynec"
        assert isinstance(out["feed_impedance"], complex)
