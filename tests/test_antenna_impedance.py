"""Induced-EMF dipole impedance: validated against the textbook half-wave result."""

from __future__ import annotations

import math

import pytest

from abax.core.science import antenna_impedance as A


def test_sine_cosine_integrals_match_tables():
    assert A.sine_integral(0.0) == 0.0
    assert A.sine_integral(1.0) == pytest.approx(0.946083, abs=1e-4)
    assert A.sine_integral(math.pi / 2) == pytest.approx(1.370762, abs=1e-4)
    assert A.sine_integral(-1.0) == pytest.approx(-0.946083, abs=1e-4)   # odd
    assert A.cosine_integral(1.0) == pytest.approx(0.337404, abs=1e-4)
    with pytest.raises(ValueError):
        A.cosine_integral(0.0)


def test_half_wave_dipole_textbook_impedance():
    z = A.dipole_input_impedance(0.5, 1e-5)
    assert z.real == pytest.approx(73.1, abs=1.0)     # 73.1 ohms
    assert z.imag == pytest.approx(42.5, abs=1.0)     # +42.5 ohms reactive
    assert A.radiation_resistance(0.5) == pytest.approx(73.1, abs=1.0)


def test_quarter_wave_pair_is_inductive_and_short_is_tiny_R():
    # A short dipole has a small radiation resistance and large -X (capacitive).
    z = A.dipole_input_impedance(0.1, 1e-4)
    assert z.real < 10.0
    assert z.imag < 0.0


def test_resonant_length_shortens_with_thicker_wire():
    thin = A.resonant_length(1e-5)
    thick = A.resonant_length(1e-2)
    assert 0.46 < thin < 0.49
    assert thick < thin                                # fatter wire -> shorter
    # reactance really is ~zero at the returned length
    x = A.dipole_input_impedance(thin, 1e-5).imag
    assert abs(x) < 0.5


def test_singular_near_full_wavelength():
    with pytest.raises(ValueError):
        A.dipole_input_impedance(1.0)
    with pytest.raises(ValueError):
        A.dipole_input_impedance(0.0)


def test_formula_integration():
    from abax.core.errors import CellError
    from abax.core.functions import FUNCTIONS

    assert FUNCTIONS["DIPOLER"]([0.5, 1e-5]) == pytest.approx(73.1, abs=1.0)
    assert FUNCTIONS["DIPOLEX"]([0.5, 1e-5]) == pytest.approx(42.5, abs=1.0)
    assert FUNCTIONS["RADRESIST"]([0.5]) == pytest.approx(73.1, abs=1.0)
    assert 0.46 < FUNCTIONS["RESONANTLEN"]([1e-4]) < 0.49
    assert isinstance(FUNCTIONS["DIPOLER"]([1.0]), CellError)   # singular -> #NUM!
