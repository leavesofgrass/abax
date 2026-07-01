"""Tests for the unit-conversion engine (``abax.core.science.units``)."""

from __future__ import annotations

import math

import pytest

from abax.core.science.units import (
    CATEGORIES,
    UnitError,
    category_of,
    convert,
    units_in_category,
)


def test_length_km_to_m() -> None:
    assert convert(1, "km", "m") == pytest.approx(1000.0)


def test_length_mi_to_m() -> None:
    assert convert(1, "mi", "m") == pytest.approx(1609.344)


def test_time_hr_to_s() -> None:
    assert convert(1, "hr", "s") == pytest.approx(3600.0)


def test_temperature_c_to_k() -> None:
    assert convert(0, "C", "K") == pytest.approx(273.15)


def test_temperature_f_to_c() -> None:
    assert convert(32, "F", "C") == pytest.approx(0.0)


def test_temperature_c_to_f() -> None:
    assert convert(100, "C", "F") == pytest.approx(212.0)


def test_energy_cal_to_j() -> None:
    assert convert(1, "cal", "J") == pytest.approx(4.184)


def test_energy_kwh_to_j() -> None:
    assert convert(1, "kWh", "J") == pytest.approx(3.6e6)


def test_pressure_atm_to_pa() -> None:
    assert convert(1, "atm", "Pa") == pytest.approx(101325.0)


def test_speed_mph_to_ms() -> None:
    assert convert(60, "mph", "m/s") == pytest.approx(26.8224)


def test_angle_deg_to_rad() -> None:
    assert convert(180, "deg", "rad") == pytest.approx(math.pi)


def test_data_kib_to_byte() -> None:
    assert convert(1, "KiB", "byte") == pytest.approx(1024.0)


def test_alias_lb_equals_lbm() -> None:
    assert convert(1, "lb", "kg") == convert(1, "lbm", "kg")


def test_alias_resolution_more() -> None:
    assert convert(1, "sec", "s") == pytest.approx(1.0)
    assert convert(1, "l", "mL") == pytest.approx(1000.0)
    assert convert(1, "turn", "deg") == pytest.approx(360.0)
    assert convert(1, "B", "bit") == pytest.approx(8.0)


def test_cross_category_raises() -> None:
    with pytest.raises(UnitError):
        convert(1, "m", "kg")


def test_unknown_unit_raises() -> None:
    with pytest.raises(UnitError):
        convert(1, "m", "bogus")
    with pytest.raises(UnitError):
        convert(1, "bogus", "m")


def test_case_sensitivity() -> None:
    # Canonical symbols are case-sensitive; "KM" is not a known unit.
    with pytest.raises(UnitError):
        convert(1, "KM", "m")


def test_category_of() -> None:
    assert category_of("ft") == "length"
    assert category_of("C") == "temperature"
    assert category_of("KiB") == "data"
    assert category_of("lb") == "length" or category_of("lb") == "mass"
    assert category_of("lb") == "mass"
    assert category_of("bogus") is None


def test_units_in_category() -> None:
    assert "ft" in units_in_category("length")
    assert set(units_in_category("temperature")) == {"C", "F", "K"}
    with pytest.raises(UnitError):
        units_in_category("bogus")


def test_categories_constant() -> None:
    assert "length" in CATEGORIES
    assert "temperature" in CATEGORIES
    assert len(CATEGORIES) == 12


def test_torr_distinct_from_mmhg() -> None:
    # torr has its own exact factor (101325/760), close to but not equal mmHg.
    assert convert(1, "torr", "Pa") == pytest.approx(101325.0 / 760.0)


def test_roundtrip() -> None:
    assert convert(convert(123.0, "ft", "m"), "m", "ft") == pytest.approx(123.0)
