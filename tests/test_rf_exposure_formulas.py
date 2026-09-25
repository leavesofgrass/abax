"""The RF exposure formula functions evaluate through the engine."""

from __future__ import annotations

import math

import pytest

from abax.core.completion import signature
from abax.core.errors import CellError
from abax.core.funcmeta import category_key
from abax.core.workbook import Workbook

NEW = ("MPELIMIT MPEEFIELD MPEHFIELD PWRDENSITY MPEDIST MPEPERCENT AVGPOWER "
       "EXEMPTERP EXEMPTMINDIST SARLIMIT SAR").split()


def _val(formula):
    s = Workbook().sheets[0]
    s.set("A1", formula)
    return s.get("A1")


def _is_err(v, code):
    return isinstance(v, CellError) and str(v) == code


@pytest.mark.parametrize("name", NEW)
def test_signature_and_category(name):
    assert signature(name).startswith(name + "(")
    assert category_key(name) == "rf"


def test_limits_take_hz_and_return_fcc_units():
    assert _val("=MPELIMIT(14.2e6)") == pytest.approx(180 / 14.2 ** 2)
    assert _val('=MPELIMIT(14.2e6,"controlled")') == pytest.approx(900 / 14.2 ** 2)
    assert _val('=MPELIMIT(146e6,"general")') == pytest.approx(0.2)
    assert _val("=MPEEFIELD(14.2e6)") == pytest.approx(824 / 14.2)
    assert _val("=MPEHFIELD(14.2e6)") == pytest.approx(2.19 / 14.2)
    assert _is_err(_val("=MPEEFIELD(440e6)"), "#N/A")        # blank in the table
    assert _is_err(_val("=MPELIMIT(137e3)"), "#NUM!")        # below 0.3 MHz
    assert _is_err(_val('=MPELIMIT(14.2e6,"neighbor")'), "#VALUE!")
    assert _is_err(_val("=MPELIMIT()"), "#VALUE!")


def test_density_distance_percent():
    assert _val("=PWRDENSITY(100,1)") == pytest.approx(100 / (4 * math.pi) / 10)
    d = _val('=MPEDIST(1000,28.4e6,"uncontrolled",4)')
    assert _val(f"=PWRDENSITY(1000,{d},4)") == pytest.approx(_val("=MPELIMIT(28.4e6)"))
    assert _val("=MPEPERCENT(0.01,146e6)") == pytest.approx(5.0)
    assert _is_err(_val("=PWRDENSITY(100,0)"), "#NUM!")


def test_average_power_and_exemption():
    assert _val("=AVGPOWER(100,0.5,0.5)") == 25
    assert _val("=AVGPOWER(100)") == 100
    assert _is_err(_val("=AVGPOWER(100,1.5)"), "#NUM!")
    assert _val("=EXEMPTERP(146e6,5)") == pytest.approx(3.83 * 25)
    assert _is_err(_val("=EXEMPTERP(14.2e6,1)"), "#NUM!")    # inside λ/2π
    assert _val("=EXEMPTMINDIST(14.2e6)") == pytest.approx(3.36, abs=0.01)


def test_sar():
    assert _val("=SARLIMIT()") == 0.08
    assert _val('=SARLIMIT("controlled","extremity")') == 20
    assert _val('=SARLIMIT("General Population/Uncontrolled","1g")') == 1.6
    assert _is_err(_val('=SARLIMIT("general","brain")'), "#VALUE!")
    assert _val("=SAR(0.5,40,1000)") == pytest.approx(0.8)


def test_rf_toolkit_worked_example():
    """The worked example printed in docs/rf-toolkit.md (RF exposure)."""
    s = Workbook().sheets[0]
    s.set("A1", "=AVGPOWER(1500, 0.5, 0.5)")
    s.set("A2", "=A1*10^(8/10)")
    s.set("A3", '=MPEDIST(A2, 28.4e6, "uncontrolled", 4)')
    s.set("A4", '=MPEDIST(A2, 28.4e6, "controlled", 4)')
    s.set("A5", "=EXEMPTERP(28.4e6, 20)")
    assert s.get("A1") == 375
    assert round(s.get("A2")) == 2366
    assert round(s.get("A3"), 1) == 18.4
    assert round(s.get("A4"), 1) == 8.2
    assert round(s.get("A5")) == 1711
