"""Engineering-notation parse / format (abax.core.science.engnum)."""

from __future__ import annotations

import math

import pytest

from abax.core.science.engnum import fmt_eng, parse_eng


@pytest.mark.parametrize("text, unit, want", [
    ("50", "", 50.0), ("4e-11", "F", 4e-11), ("50u", "H", 50e-6),
    ("50 µH", "H", 50e-6), ("50μH", "H", 50e-6), ("40p", "F", 40e-12),
    ("40 pF", "F", 40e-12), ("3.5 MHz", "Hz", 3.5e6), ("10m", "", 10e-3),
    ("10M", "", 10e6), ("1k", "Ω", 1e3), ("2.2 kohm", "Ω", 2.2e3),
    ("470Ω", "Ω", 470.0), ("1F", "F", 1.0),
])
def test_parse_eng(text, unit, want):
    assert math.isclose(parse_eng(text, unit), want, rel_tol=1e-12)


@pytest.mark.parametrize("bad", ["", "abc", "5x", "M"])
def test_parse_eng_rejects(bad):
    with pytest.raises(ValueError):
        parse_eng(bad)


@pytest.mark.parametrize("value, unit, want", [
    (3.5588e6, "Hz", "3.559 MHz"), (47.3e3, "Hz", "47.3 kHz"), (220.0, "s", "220 s"),
    (50e-6, "H", "50 µH"), (40e-12, "F", "40 pF"), (0.0, "V", "0 V"),
    (-0.002, "A", "-2 mA"), (1e-15, "F", "0.001 pF"),
])
def test_fmt_eng(value, unit, want):
    assert fmt_eng(value, unit) == want
