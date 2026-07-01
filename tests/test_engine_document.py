"""Document façade: open/save dispatch by extension; Excel when available."""

from __future__ import annotations

import pytest

from abax.engine import HAS_OPENPYXL
from abax.engine.document import Document


def test_open_csv_and_save_json(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("1,2,=A1+B1\n")
    doc = Document.open(src)
    assert doc.workbook.sheet.get("C1") == 3
    out = tmp_path / "out.abax"
    doc.save(out)
    assert out.exists()
    reopened = Document.open(out)
    assert reopened.workbook.sheet.get("C1") == 3


def test_unsupported_extension(tmp_path):
    p = tmp_path / "x.foo"
    p.write_text("nope")
    with pytest.raises(ValueError):
        Document.open(p)


@pytest.mark.skipif(not HAS_OPENPYXL, reason="openpyxl not installed")
def test_xlsx_roundtrip(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("5,10,=A1+B1\n")
    doc = Document.open(src)
    xlsx = tmp_path / "book.xlsx"
    doc.save(xlsx)
    assert xlsx.exists()
    reopened = Document.open(xlsx)
    # Formula survives the round-trip and re-evaluates.
    assert reopened.workbook.sheet.get("C1") == 15


@pytest.mark.skipif(HAS_OPENPYXL, reason="openpyxl IS installed")
def test_xlsx_without_openpyxl_raises(tmp_path):
    from abax.engine.excel_io import load_xlsx

    with pytest.raises(RuntimeError):
        load_xlsx(tmp_path / "missing.xlsx")
