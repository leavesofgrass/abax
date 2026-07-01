"""The new radio-math formula functions evaluate through the engine."""

from __future__ import annotations

import math

import pytest

from abax.core.completion import signature
from abax.core.workbook import Workbook


def _val(formula):
    wb = Workbook()
    s = wb.sheets[0]
    s.set("A1", formula)
    return s.get("A1")


def test_q_and_bandwidth():
    assert _val("=QBW(14000000,14000)") == 1000.0
    assert _val("=BWQ(14000000,1000)") == 14000.0


def test_quarter_wave_and_swr():
    assert _val("=QWMATCH(50,200)") == 100.0
    assert _val("=SWRPWR(100,0)") == 1.0
    assert math.isclose(_val("=SWRPWR(100,11.111111)"), 2.0, rel_tol=1e-4)


def test_resonance_roundtrip():
    # L to resonate 100 pF at 7 MHz, then C to resonate that L at 7 MHz ~= 100 pF.
    lval = _val("=RESONANTL(7000000,1e-10)")
    assert isinstance(lval, float)
    wb = Workbook()
    s = wb.sheets[0]
    s.set("A1", str(lval))
    s.set("A2", "=RESONANTC(7000000,A1)")
    assert math.isclose(s.get("A2"), 1e-10, rel_tol=1e-6)


def test_doppler_sign():
    assert math.isclose(_val("=DOPPLER(145800000,7660)"), 3725.34, rel_tol=1e-3)
    assert _val("=DOPPLER(145800000,-7660)") < 0


def test_dish_gain_reasonable():
    g = _val("=DISHGAIN(3,10000000000)")
    assert 45 < g < 50


def test_bad_args_give_error():
    # equal forward/reflected power -> infinite SWR -> #NUM!
    assert "NUM" in str(_val("=SWRPWR(100,100)")).upper()


def test_signatures_present():
    for name in ("QBW", "QWMATCH", "DOPPLER", "AIRCOILL", "TOROIDN"):
        assert signature(name).startswith(name + "(")


@pytest.mark.parametrize("formula", [
    "=CFROMXC(50,7000000)", "=LFROMXL(50,7000000)", "=AIRCOILL(0.025,0.05,20)",
    "=AIRCOILN(1e-6,0.025,0.05)", "=TOROIDL(50,20)", "=TOROIDN(1e-5,50)",
    "=LOOPLEN(7000000)", "=DISHBW(3,10000000000)",
])
def test_all_new_functions_numeric(formula):
    v = _val(formula)
    assert isinstance(v, float) and v == v  # not NaN / error
