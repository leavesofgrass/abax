"""A pure-Python unit-conversion engine (Excel ``CONVERT``-style).

Converts a numeric value between two units within a single physical category
(length, mass, time, temperature, area, volume, energy, power, pressure, speed,
angle, data). Every scale-based category defines a base unit and a factor that
maps each unit to that base; a conversion is then::

    result = value * factor[from_unit] / factor[to_unit]

Temperature is the one affine category (units have an offset as well as a
scale), so it is special-cased: convert *to* the base (Kelvin) and then *from*
the base using the affine formulas.

Unit names are case-SENSITIVE for the canonical symbols (e.g. ``km``, ``KiB``),
but a small set of common aliases is accepted (e.g. ``lb`` -> ``lbm``,
``sec`` -> ``s``, ``torr`` -> ``mmHg``-category but its own exact factor).

Public API: :func:`convert`, :func:`category_of`, :func:`units_in_category`,
and :data:`CATEGORIES`. Errors raise :class:`UnitError`.
"""

from __future__ import annotations

import math


class UnitError(Exception):
    """Raised when a unit is unknown or the two units share no category."""


# Each scale category maps canonical unit symbol -> multiplicative factor that
# converts a quantity expressed in that unit into the category's base unit.
_SCALE: dict[str, dict[str, float]] = {
    "length": {  # base: m
        "m": 1.0,
        "km": 1e3,
        "cm": 1e-2,
        "mm": 1e-3,
        "um": 1e-6,
        "nm": 1e-9,
        "mi": 1609.344,
        "yd": 0.9144,
        "ft": 0.3048,
        "in": 0.0254,
        "nmi": 1852.0,
        "ly": 9.4607304725808e15,
    },
    "mass": {  # base: kg
        "kg": 1.0,
        "g": 1e-3,
        "mg": 1e-6,
        "t": 1000.0,
        "lbm": 0.45359237,
        "oz": 0.028349523125,
        "stone": 6.35029318,
        "slug": 14.5939029,
    },
    "time": {  # base: s
        "s": 1.0,
        "min": 60.0,
        "hr": 3600.0,
        "day": 86400.0,
        "wk": 604800.0,
        "yr": 31557600.0,
    },
    "area": {  # base: m2
        "m2": 1.0,
        "km2": 1e6,
        "cm2": 1e-4,
        "ha": 1e4,
        "acre": 4046.8564224,
        "ft2": 0.09290304,
        "in2": 0.00064516,
        "mi2": 2589988.110336,
    },
    "volume": {  # base: m3
        "m3": 1.0,
        "L": 1e-3,
        "mL": 1e-6,
        "gal": 0.003785411784,
        "qt": 0.000946352946,
        "pt": 0.000473176473,
        "cup": 0.0002365882365,
        "floz": 2.95735295625e-5,
        "ft3": 0.028316846592,
        "in3": 1.6387064e-5,
    },
    "energy": {  # base: J
        "J": 1.0,
        "kJ": 1e3,
        "cal": 4.184,
        "kcal": 4184.0,
        "Wh": 3600.0,
        "kWh": 3.6e6,
        "BTU": 1055.05585262,
        "eV": 1.602176634e-19,
        "erg": 1e-7,
    },
    "power": {  # base: W
        "W": 1.0,
        "kW": 1e3,
        "MW": 1e6,
        "hp": 745.6998715823,
        "PS": 735.49875,
    },
    "pressure": {  # base: Pa
        "Pa": 1.0,
        "kPa": 1e3,
        "bar": 1e5,
        "atm": 101325.0,
        "psi": 6894.757293168,
        "mmHg": 133.322387415,
        "torr": 101325.0 / 760.0,
        "inHg": 3386.389,
    },
    "speed": {  # base: m/s
        "m/s": 1.0,
        "km/h": 1.0 / 3.6,
        "mph": 0.44704,
        "knot": 0.514444444,
        "ft/s": 0.3048,
    },
    "angle": {  # base: rad
        "rad": 1.0,
        "deg": math.pi / 180.0,
        "grad": math.pi / 200.0,
        "rev": 2.0 * math.pi,
    },
    "data": {  # base: byte
        "byte": 1.0,
        "bit": 0.125,
        "KB": 1e3,
        "MB": 1e6,
        "GB": 1e9,
        "TB": 1e12,
        "KiB": 1024.0,
        "MiB": 1048576.0,
        "GiB": 1073741824.0,
    },
}

# Temperature is affine, not a pure scale, so it lives outside ``_SCALE`` and is
# resolved through :func:`_temp_to_base` / :func:`_temp_from_base`.
_TEMPERATURE_UNITS: tuple[str, ...] = ("C", "F", "K")

# Aliases (case-sensitive on the way in) -> canonical symbol.
_ALIASES: dict[str, str] = {
    "lb": "lbm",
    "sec": "s",
    "h": "hr",
    "d": "day",
    "l": "L",
    "ml": "mL",
    "turn": "rev",
    "B": "byte",
}

# Category names, in declaration order with temperature inserted where listed.
CATEGORIES: list[str] = [
    "length",
    "mass",
    "time",
    "temperature",
    "area",
    "volume",
    "energy",
    "power",
    "pressure",
    "speed",
    "angle",
    "data",
]


def _resolve(unit: str) -> str:
    """Resolve an alias to its canonical symbol (identity if not an alias)."""
    return _ALIASES.get(unit, unit)


def category_of(unit: str) -> str | None:
    """Return the category name for ``unit``, or ``None`` if it is unknown."""
    canon = _resolve(unit)
    if canon in _TEMPERATURE_UNITS:
        return "temperature"
    for category, table in _SCALE.items():
        if canon in table:
            return category
    return None


def units_in_category(category: str) -> list[str]:
    """Return the canonical unit symbols belonging to ``category``.

    Raises :class:`UnitError` if ``category`` is not a known category name.
    """
    if category == "temperature":
        return list(_TEMPERATURE_UNITS)
    if category in _SCALE:
        return list(_SCALE[category])
    raise UnitError(f"unknown category: {category!r}")


def _temp_to_base(value: float, unit: str) -> float:
    """Convert a temperature in ``unit`` to Kelvin (the temperature base)."""
    if unit == "K":
        return value
    if unit == "C":
        return value + 273.15
    if unit == "F":
        return (value - 32.0) * 5.0 / 9.0 + 273.15
    raise UnitError(f"unknown temperature unit: {unit!r}")


def _temp_from_base(kelvin: float, unit: str) -> float:
    """Convert a temperature in Kelvin to ``unit``."""
    if unit == "K":
        return kelvin
    if unit == "C":
        return kelvin - 273.15
    if unit == "F":
        return (kelvin - 273.15) * 9.0 / 5.0 + 32.0
    raise UnitError(f"unknown temperature unit: {unit!r}")


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert ``value`` from ``from_unit`` to ``to_unit``.

    Both units must belong to the same category. Aliases are resolved first;
    canonical symbols are case-sensitive. Raises :class:`UnitError` if either
    unit is unknown or the two units are in different categories.
    """
    src = _resolve(from_unit)
    dst = _resolve(to_unit)

    from_cat = category_of(src)
    if from_cat is None:
        raise UnitError(f"unknown unit: {from_unit!r}")
    to_cat = category_of(dst)
    if to_cat is None:
        raise UnitError(f"unknown unit: {to_unit!r}")

    if from_cat != to_cat:
        raise UnitError(
            f"cannot convert between {from_cat} ({from_unit!r}) "
            f"and {to_cat} ({to_unit!r})"
        )

    if from_cat == "temperature":
        return _temp_from_base(_temp_to_base(value, src), dst)

    table = _SCALE[from_cat]
    return value * table[src] / table[dst]
