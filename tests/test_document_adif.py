"""ADIF logbook routing through the Document façade (open / save / re-open)."""

from __future__ import annotations

from abax.core.io import adif_io
from abax.engine.document import Document

SAMPLE_RECORDS = [
    {"CALL": "W1AW", "QSO_DATE": "20240115", "BAND": "20m", "MODE": "SSB"},
    {"CALL": "DL1ABC", "QSO_DATE": "20240116", "BAND": "40m", "MODE": "CW"},
]


def _write_adif(path):
    path.write_text(adif_io.to_adif(SAMPLE_RECORDS), encoding="utf-8")


def _header(sheet):
    _, nc = sheet.used_bounds()
    return [str(sheet.get_value(0, c) or "") for c in range(nc)]


def test_open_adif_populates_sheet(tmp_path):
    src = tmp_path / "log.adi"
    _write_adif(src)

    doc = Document.open(src)
    sheet = doc.workbook.sheet
    header = _header(sheet)
    assert "CALL" in header
    assert "MODE" in header
    # First QSO's callsign lands in the CALL column, row 1.
    call_col = header.index("CALL")
    assert sheet.get_value(1, call_col) == "W1AW"


def test_open_adif_enriches_dxcc(tmp_path):
    src = tmp_path / "log.adi"
    _write_adif(src)

    doc = Document.open(src)
    sheet = doc.workbook.sheet
    header = _header(sheet)
    assert "DXCC" in header
    dxcc_col = header.index("DXCC")
    assert sheet.get_value(1, dxcc_col) == "United States"
    assert sheet.get_value(2, dxcc_col) == "Germany"


def test_save_and_reopen_roundtrip(tmp_path):
    src = tmp_path / "log.adi"
    _write_adif(src)
    doc = Document.open(src)

    out = tmp_path / "out.adi"
    doc.save(out)
    assert out.exists()

    # Re-parse the saved file: the QSOs (and the enriched DXCC field) survive.
    records = adif_io.parse_adif(out.read_text(encoding="utf-8"))
    assert len(records) == 2
    assert records[0]["CALL"] == "W1AW"
    assert records[0]["DXCC"] == "United States"

    # And a full second open through Document still yields the same first QSO.
    doc2 = Document.open(out)
    sheet2 = doc2.workbook.sheet
    header2 = _header(sheet2)
    assert sheet2.get_value(1, header2.index("CALL")) == "W1AW"
