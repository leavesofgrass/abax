"""The circuit and radio-system formula functions evaluate through the engine."""

from __future__ import annotations

import math

import pytest

from abax.core.completion import signature
from abax.core.errors import CellError
from abax.core.funcmeta import category_key
from abax.core.workbook import Workbook

NEW = (
    "OHMV OHMI OHMR POWERVI POWERIR POWERVR RSERIES RPARALLEL LSERIES LPARALLEL "
    "CSERIES CPARALLEL TAURC TAURL TCCHARGE TCDECAY TCTIME ZSERIESRLC ZPARALLELRLC "
    "ZMAG PHASEANGLE POWERFACTOR ADMITTANCE CONDUCTANCE SUSCEPTANCE POLAR2RECT "
    "REALPOWER REACTIVEPOWER APPARENTPOWER QSERIES QPARALLEL ERPW EIRPW RXLEVEL "
    "LINKMARGIN BWNOISEDB OPAMPINV OPAMPNONINV MODINDEX DEVRATIO CARSONBW CWBW FSKBW "
    "ADCBITS ADCLEVELS ADCLSB ADCSNR NYQUIST USBMAXFREQ LSBMINFREQ LINELEN ELECDEG "
    "STUBX ANTEFF IMD3LO IMD3HI IP3 SFDR IMAGEFREQ"
).split()


def _val(formula, cells=None):
    wb = Workbook()
    s = wb.sheets[0]
    for ref, v in (cells or {}).items():
        s.set(ref, v)
    s.set("Z99", formula)
    return s.get("Z99")


def _is_err(v, code):
    return isinstance(v, CellError) and str(v) == code


@pytest.mark.parametrize("name", NEW)
def test_every_new_function_has_signature_and_rf_category(name):
    assert signature(name).startswith(name + "(")
    assert category_key(name) == "rf"


def test_ohm_and_power():
    assert _val("=OHMV(2,50)") == 100
    assert _val("=OHMI(100,50)") == 2
    assert _val("=OHMR(100,2)") == 50
    assert _val("=POWERIR(1,100)") == 100          # E5D11
    assert _is_err(_val("=OHMI(1,0)"), "#NUM!")
    assert _is_err(_val("=OHMV(1)"), "#VALUE!")


def test_series_parallel_accept_ranges():
    cells = {"A1": "1000000", "A2": "1000000", "B1": "0.00022", "B2": "0.00022"}
    assert _val("=TAURC(RPARALLEL(A1:A2),CPARALLEL(B1:B2))", cells) == pytest.approx(220)  # E5B04
    assert _val("=CSERIES(100e-12,100e-12)") == pytest.approx(50e-12)
    assert _val("=LSERIES(1e-6,2e-6)") == pytest.approx(3e-6)
    assert _is_err(_val("=RPARALLEL(100,0)"), "#NUM!")


def test_time_constants():
    assert _val("=TCCHARGE(1,1)") == pytest.approx(0.632, abs=1e-3)   # E5B01
    assert _val("=TCDECAY(1,1)") == pytest.approx(0.368, abs=1e-3)
    assert _val("=TCTIME(0.5,TAURL(10,0.001))") == pytest.approx(1e-4 * math.log(2))


def test_impedance_both_styles():
    # the same phase angle from R, X numbers and from a complex string
    assert _val("=PHASEANGLE(100,-200)") == pytest.approx(-63.43, abs=0.01)   # E5B08
    assert _val('=PHASEANGLE("100-200j")') == pytest.approx(-63.43, abs=0.01)
    assert _val('=PHASEANGLE("100-200i")') == pytest.approx(-63.43, abs=0.01)
    assert _val('=ZMAG("3+4j")') == 5 and _val("=ZMAG(3,4)") == 5
    assert _val("=POWERFACTOR(3,4)") == pytest.approx(0.6)
    assert _is_err(_val('=PHASEANGLE("not a number")'), "#VALUE!")
    assert _is_err(_val("=PHASEANGLE(0,0)"), "#NUM!")


def test_complex_results_are_excel_complex_strings():
    assert _val("=ADMITTANCE(50,-25)") == "0.016+0.008j"
    assert _val("=IMREAL(ADMITTANCE(50,-25))") == pytest.approx(0.016)
    assert _val("=CONDUCTANCE(50,-25)") == pytest.approx(0.016)
    assert _val("=SUSCEPTANCE(50,-25)") == pytest.approx(0.008)
    assert _val("=POLAR2RECT(10,90)") == "10j"                 # floating dust removed
    z = _val("=ZSERIESRLC(14e6,400,0,38e-12)")                 # E5C10 -> Point 4
    assert z.startswith("400-299.16")
    assert _val("=IMAGINARY(ZSERIESRLC(3.505e6,300,18e-6,0))") == pytest.approx(396.4, abs=0.05)
    assert _is_err(_val("=ZSERIESRLC(0,1,1,1)"), "#NUM!")


def test_power_chain_and_link():
    assert round(_val("=ERPW(150,7,2,2.2)")) == 286                     # E9A02
    assert round(_val("=EIRPW(200,7,2,2.8,1.2)")) == 252                # E9A07
    assert _val("=ERPW(100,0)") == 100
    assert _is_err(_val("=ERPW(100)"), "#VALUE!")
    assert _val("=LINKMARGIN(RXLEVEL(40,10,0,136,3),-103,6)") == 8       # E4D12
    assert _val("=RXLEVEL(40,6,3,100)") == -51                          # E4D13


def test_modulation_and_bandwidths():
    assert _val("=MODINDEX(3000,1000)") == 3
    assert _val("=DEVRATIO(7500,3500)") == pytest.approx(2.142857)
    assert _val("=CWBW(13)") == pytest.approx(52)
    assert _val("=FSKBW(4800,9600)") == pytest.approx(15360)
    assert _val("=CARSONBW(5000,3000)") == 16000


def test_adc_and_sampling():
    assert _val("=ADCBITS(1,0.001)") == 10
    assert _val("=ADCLEVELS(8)") == 256
    assert _val("=NYQUIST(3000)") == 6000
    assert _is_err(_val("=ADCLEVELS(8.5)"), "#NUM!")


def test_flags_default_and_override():
    assert _val("=STUBX(50,45)") == pytest.approx(50)
    assert _val("=STUBX(50,45,TRUE)") == pytest.approx(-50)
    assert _is_err(_val("=STUBX(50,90)"), "#NUM!")
    assert _val("=IMAGEFREQ(14.2e6,9e6)") == 32.2e6
    assert _val("=IMAGEFREQ(14.2e6,455e3,FALSE)") == pytest.approx(13.29e6)


def test_imd_and_misc():
    assert _val("=IMD3LO(14.070e6,14.072e6)") == 14.068e6
    assert _val("=IMD3HI(14.070e6,14.072e6)") == 14.074e6
    assert _is_err(_val("=IMD3HI(14e6)"), "#VALUE!")
    assert _val("=LINELEN(14.1e6,0.5)") == pytest.approx(10.63, abs=0.01)   # E9F06
    assert _val("=USBMAXFREQ(14.15e6,2800)") == pytest.approx(14.1472e6)   # E1A03
    assert _val("=ANTEFF(36,4)") == pytest.approx(0.9)
