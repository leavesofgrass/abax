"""Ham wiring: the DXCC formula function and ADIF open/save through Document."""

from __future__ import annotations

from qcell.core.errors import CellError
from qcell.core.functions import FUNCTIONS
from qcell.core.io import adif_io
from qcell.core.sheet import Sheet
from qcell.core.workbook import Workbook
from qcell.engine.document import Document


def _wb(sheet):
    return Workbook.from_sheets([sheet]) if hasattr(Workbook, "from_sheets") else Workbook()


def test_dxcc_formula_function():
    assert FUNCTIONS["DXCC"](["W1AW"]) == "United States"
    assert FUNCTIONS["DXCC"](["DL1ABC"]) == "Germany"
    assert isinstance(FUNCTIONS["DXCC"](["???garbage"]), CellError)   # #N/A


def test_dxcc_in_completion():
    from qcell.core.completion import signature

    assert signature("DXCC") == "DXCC(callsign)"


def test_adif_load_sheet(tmp_path):
    text = ("<CALL:5>W1AW/ <QSO_DATE:8>20260615 <BAND:3>20m <MODE:3>SSB <EOR>\n"
            "<CALL:4>K7RA <BAND:3>40m <MODE:2>CW <EOR>\n")
    p = tmp_path / "in.adi"
    p.write_text(text, encoding="utf-8")
    sheet = adif_io.load_adif(p)
    assert sheet.name == "Log"
    call_col = next(c for c in range(4) if sheet.get_value(0, c) == "CALL")
    assert sheet.get_value(1, call_col) == "W1AW/"
    assert sheet.get_value(2, call_col) == "K7RA"


def test_adif_document_roundtrip(tmp_path):
    s = Sheet("Log")
    for c, h in enumerate(["CALL", "QSO_DATE", "BAND", "MODE"]):
        s.set_cell(0, c, h)
    for c, v in enumerate(["W1AW", "20260615", "20m", "SSB"]):
        s.set_cell(1, c, v)
    Document(_wb(s), tmp_path / "log.adi").save()
    assert (tmp_path / "log.adi").exists()

    log = Document.open(tmp_path / "log.adi").workbook.sheet
    call_col = next(c for c in range(4) if log.get_value(0, c) == "CALL")
    assert log.get_value(1, call_col) == "W1AW"
