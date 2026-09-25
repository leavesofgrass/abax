"""Complex-load L-network matching, match paths, and complex-string SWR formulas."""

from __future__ import annotations

import math
import random

import pytest

from abax.core.errors import CellError
from abax.core.science import rf
from abax.core.workbook import Workbook


def test_textbook_example():
    # ZL = 200 − j100 Ω to 100 Ω at 500 MHz (the classic two-solution example:
    # normalized b = 0.29, x = 1.22 and b = −0.69, x = −1.22)
    sols = rf.l_match_complex(complex(200, -100), 100.0, 500e6)
    assert len(sols) == 2 and {s["topology"] for s in sols} == {"shunt-at-load"}
    by_sign = sorted(sols, key=lambda s: s["shunt_b"])
    lo, hi = by_sign
    assert hi["shunt_b"] * 100 == pytest.approx(0.29, abs=0.005)
    assert hi["series_x"] / 100 == pytest.approx(1.22, abs=0.005)
    assert hi["shunt"]["type"] == "C" and hi["shunt"]["farads"] == pytest.approx(0.92e-12, rel=0.01)
    assert hi["series"]["type"] == "L" and hi["series"]["henrys"] == pytest.approx(38.98e-9, rel=0.01)
    assert lo["shunt_b"] * 100 == pytest.approx(-0.69, abs=0.005)
    assert lo["shunt"]["type"] == "L" and lo["series"]["type"] == "C"


@pytest.mark.parametrize("seed", range(40))
def test_every_solution_actually_matches(seed):
    rnd = random.Random(seed)
    z0 = rnd.choice([50.0, 75.0, 300.0])
    zl = complex(rnd.uniform(1, 500), rnd.uniform(-400, 400))
    sols = rf.l_match_complex(zl, z0, 14e6)
    assert sols, zl                               # a lossless L-network always exists
    for s in sols:
        zin = rf.match_input_impedance(zl, s["topology"], s["series_x"], s["shunt_b"])
        assert abs(zin - z0) < 1e-6 * z0
        path = rf.match_path(zl, s, z0)
        assert path[0] == pytest.approx(rf.reflection_coefficient(zl, z0))
        assert abs(path[-1]) < 1e-6


def test_solution_counts_by_region():
    # RL > Z0: only shunt-at-load works (two solutions)
    assert {s["topology"] for s in rf.l_match_complex(complex(200, 50), 50, 7e6)} \
        == {"shunt-at-load"}
    # small RL, small X: only series-at-load
    assert {s["topology"] for s in rf.l_match_complex(complex(10, 5), 50, 7e6)} \
        == {"series-at-load"}
    # RL < Z0 but |ZL|² ≥ Z0·RL: both topologies work (four solutions)
    assert len(rf.l_match_complex(complex(25, 40), 50, 7e6)) == 4
    # RL == Z0 with reactance: a single series element cancels X
    sols = rf.l_match_complex(complex(50, 30), 50, 7e6)
    assert any(s["shunt"]["type"] == "none" and s["series_x"] == pytest.approx(-30)
               for s in sols)
    # already matched
    only = rf.l_match_complex(50, 50, 7e6)
    assert len(only) == 1 and only[0]["topology"] == "none"


def test_match_rejects_bad_input():
    for args in ((complex(0, 10), 50, 7e6), (complex(50, 0), 0, 7e6), (complex(50, 0), 50, 0)):
        with pytest.raises(ValueError):
            rf.l_match_complex(*args)
    with pytest.raises(ValueError):
        rf.match_input_impedance(50, "pi", 1, 1)


def _val(formula):
    s = Workbook().sheets[0]
    s.set("A1", formula)
    return s.get("A1")


def test_swr_formulas_accept_complex_strings():
    g = (complex(75, 25) - 50) / (complex(75, 25) + 50)
    vswr = (1 + abs(g)) / (1 - abs(g))
    assert _val('=VSWR("75+25j")') == pytest.approx(vswr)
    assert _val('=VSWR("75+25j",50)') == pytest.approx(vswr)
    assert _val('=REFLCOEF("75+25j")').startswith("0.230769230769+0.153846153846j")
    assert _val('=RETURNLOSS(REFLCOEF("75+25j"))') == pytest.approx(-20 * math.log10(abs(g)))
    assert _val('=MISMATCHLOSS(REFLCOEF("75+25j"))') == pytest.approx(
        -10 * math.log10(1 - abs(g) ** 2))
    assert _val('=VSWRG(REFLCOEF("75+25j"))') == pytest.approx(vswr)


def test_swr_formulas_unchanged_for_numbers():
    assert _val("=VSWR(75,50)") == pytest.approx(1.5)
    assert _val("=REFLCOEF(75)") == pytest.approx(0.2)
    assert isinstance(_val("=REFLCOEF(75)"), float)       # a real result stays a number
    assert _val("=RETURNLOSS(VSWR2GAMMA(1.5))") == pytest.approx(13.98, abs=0.01)
    v = _val('=VSWR("bad")')
    assert isinstance(v, CellError) and str(v) == "#VALUE!"
