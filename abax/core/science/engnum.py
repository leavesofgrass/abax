"""Engineering-notation numbers: parse "50u", "40 pF", "3.5 MHz"; format 3.559e6
as "3.559 MHz". Pure stdlib.

Prefixes are case-sensitive where SI makes them so: ``m`` is milli and ``M`` is
mega. ``u`` is accepted for micro alongside ``µ`` (U+00B5) and ``μ`` (U+03BC).
"""

from __future__ import annotations

import math

_PREFIX = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3,
    "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12,
}

_FORMAT_PREFIX = ((1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""),
                  (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"))

_UNIT_ALIASES = {"Ω": ("Ω", "ohms", "ohm", "Ohms", "Ohm", "R")}


def parse_eng(text: str, unit: str = "") -> float:
    """Parse ``text`` as a number with an optional SI prefix and optional
    ``unit`` suffix: ``parse_eng("50 µH", "H") == 50e-6``.

    Plain numbers and scientific notation (``"4e-11"``) pass straight through.
    Raises ValueError for anything else.
    """
    s = str(text).strip().replace(" ", "")
    if not s:
        raise ValueError("empty value")
    try:
        return float(s)
    except ValueError:
        pass
    for u in _UNIT_ALIASES.get(unit, (unit,) if unit else ()):
        if u and s.endswith(u) and len(s) > len(u):
            s = s[: -len(u)]
            break
    try:
        return float(s)
    except ValueError:
        pass
    mult = _PREFIX.get(s[-1])
    if mult is None:
        raise ValueError(f"not a number: {text!r}")
    return float(s[:-1]) * mult


def fmt_eng(value: float, unit: str = "", digits: int = 4) -> str:
    """Format ``value`` with an SI prefix and ``digits`` significant figures:
    ``fmt_eng(3.5588e6, "Hz") == "3.559 MHz"``."""
    if value == 0 or not math.isfinite(value):
        return f"{value:g} {unit}".strip()
    mag = abs(value)
    for scale, prefix in _FORMAT_PREFIX:
        if mag >= scale * (1 - 1e-12):
            break
    else:
        scale, prefix = _FORMAT_PREFIX[-1]
    return f"{value / scale:.{digits}g} {prefix}{unit}".strip()
