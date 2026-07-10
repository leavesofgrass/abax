"""External-reference loaders (abax.engine.extloaders).

Covers the suffix dispatch end to end: csv/tsv round-trips through the stdlib
reader, ``.abax`` goes through the existing Document path, ``.xlsx`` reads
values-only via openpyxl (skipped when openpyxl is absent), unknown suffixes
raise, and a missing openpyxl raises an :class:`ExternalLoadError` naming the
``abax[excel]`` extra. A final test wires :func:`load_external` into the
externref hub exactly as the integrator will.
"""

from __future__ import annotations

import sys
import time

import pytest

from abax.engine.extloaders import (
    SUPPORTED_SUFFIXES,
    ExternalLoadError,
    load_external,
)


def test_supported_suffixes_cover_all_dispatched_formats():
    assert set(SUPPORTED_SUFFIXES) == {".abax", ".json", ".xlsx", ".csv", ".tsv"}


# -- csv / tsv ---------------------------------------------------------------

def test_csv_round_trip(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b\n1,2.5\nhello,TRUE\n", encoding="utf-8")
    before = p.read_bytes()

    wb = load_external(p)
    sheet = wb.sheet                      # empty sheet part -> first sheet
    assert sheet.get_value(0, 0) == "a"
    assert sheet.get_value(1, 0) == 1
    assert sheet.get_value(1, 1) == 2.5
    assert sheet.get_value(2, 0) == "hello"
    assert sheet.get_value(2, 1) is True
    # Single sheet named after the file stem, reachable by name too.
    assert wb.get_sheet("data") is sheet
    assert p.read_bytes() == before       # source never written


def test_tsv_uses_tab_delimiter(tmp_path):
    p = tmp_path / "cols.tsv"
    p.write_text("x\ty\n7\t8\n", encoding="utf-8")
    wb = load_external(p)
    assert wb.sheet.get_value(1, 0) == 7
    assert wb.sheet.get_value(1, 1) == 8
    assert wb.get_sheet("cols") is not None


# -- .abax through the Document path -----------------------------------------

def test_abax_loads_through_dispatch(tmp_path):
    from abax.engine.document import Document

    doc = Document()
    doc.workbook.sheet.set_cell(0, 0, "5")
    doc.workbook.sheet.set_cell(0, 1, "=A1*2")
    target = tmp_path / "book.abax"
    doc.save(target)

    wb = load_external(target)
    assert wb.get_sheet("Sheet1").get_value(0, 0) == 5
    assert wb.sheet.get_value(0, 1) == 10   # native formulas still evaluate


# -- .xlsx (values only) ------------------------------------------------------

def test_xlsx_values_only(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")

    wbx = openpyxl.Workbook()
    ws = wbx.active
    ws.title = "Data"
    ws["A1"] = 10
    ws["B2"] = "hello"
    ws["C3"] = "=A1*2"                    # openpyxl stores no cached value
    ws2 = wbx.create_sheet("Other")
    ws2["A1"] = 2.5
    path = tmp_path / "Data.xlsx"
    wbx.save(path)
    before = path.read_bytes()

    wb = load_external(path)
    data = wb.get_sheet("Data")
    assert data.get_value(0, 0) == 10
    assert data.get_value(1, 1) == "hello"
    # No cached value in the file -> the formula text comes back as inert text,
    # never re-evaluated by abax.
    assert data.get_value(2, 2) == "=A1*2"
    assert wb.get_sheet("Other").get_value(0, 0) == 2.5
    assert wb.sheet is data               # first sheet serves the empty sheet part
    assert path.read_bytes() == before    # strictly read-only


# -- error paths --------------------------------------------------------------

def test_unknown_suffix_raises(tmp_path):
    p = tmp_path / "book.exe"
    p.write_text("not a workbook", encoding="utf-8")
    with pytest.raises(ExternalLoadError, match="unsupported"):
        load_external(p)


def test_missing_openpyxl_names_the_extra(tmp_path, monkeypatch):
    p = tmp_path / "Data.xlsx"
    p.write_bytes(b"")                    # never read: the import guard fires first
    # A None entry makes ``import openpyxl`` raise ImportError even when the
    # package is installed — the standard way to simulate a missing dep.
    monkeypatch.setitem(sys.modules, "openpyxl", None)
    with pytest.raises(ExternalLoadError, match=r"abax\[excel\]"):
        load_external(p)


# -- integration with the externref hub ---------------------------------------

def test_hub_serves_csv_via_load_external(tmp_path, monkeypatch):
    """Wire the hub the way the integrator will: SUPPORTED_SUFFIXES + load_external."""
    from abax.core import externref
    from abax.core.errors import is_error
    from abax.core.externref import ExternalRefHub

    (tmp_path / "data.csv").write_text("7\n", encoding="utf-8")
    monkeypatch.setattr(externref, "ALLOWED_SUFFIXES", SUPPORTED_SUFFIXES)

    hub = ExternalRefHub()
    hub.loader = load_external
    hub.set_base_dir(tmp_path)
    hub.set_enabled(True)
    try:
        deadline = time.time() + 5.0
        value = hub.lookup("data.csv", "", 0, 0)   # first call kicks off the load
        while is_error(value) and time.time() < deadline:
            time.sleep(0.01)
            value = hub.lookup("data.csv", "", 0, 0)
        assert value == 7
    finally:
        hub.set_enabled(False)
