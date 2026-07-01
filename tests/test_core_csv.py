"""CSV import/export round-trips, including formula preservation."""

from __future__ import annotations

from abax.core.io.csv_io import dumps_csv, load_csv, loads_csv, save_csv


def test_import_parses_numbers_and_text():
    sheet = loads_csv("name,score\nalice,90\nbob,85\n")
    assert sheet.get("A1") == "name"
    assert sheet.get("B2") == 90
    assert sheet.get("A3") == "bob"


def test_formula_in_csv_is_evaluated():
    sheet = loads_csv("1,2,=A1+B1\n")
    assert sheet.get("C1") == 3


def test_export_values_vs_raw():
    sheet = loads_csv("10,20,=A1+B1\n")
    assert dumps_csv(sheet, values=True).strip() == "10,20,30"
    assert dumps_csv(sheet, values=False).strip() == "10,20,=A1+B1"


def test_file_roundtrip(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("a,b\n1,2\n3,4\n")
    sheet = load_csv(src)
    out = tmp_path / "out.csv"
    save_csv(sheet, out)
    assert out.read_text().splitlines()[0] == "a,b"
    assert out.read_text().splitlines()[1] == "1,2"
