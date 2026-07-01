"""Tests for the pure-stdlib OpenDocument Spreadsheet (.ods) adapter."""

from __future__ import annotations

import zipfile

import pytest

from abax.core.workbook import Workbook
from abax.engine import ods_io


def _make_workbook() -> Workbook:
    from abax.core.sheet import Sheet

    sheet = Sheet("Data")
    sheet.set_cell(0, 0, "Name")     # header text
    sheet.set_cell(0, 1, "Score")    # header text
    sheet.set_cell(1, 0, "Alice")
    sheet.set_cell(1, 1, "42")       # numeric
    # (2, 0) and (2, 1) left blank
    sheet.set_cell(3, 0, "Bob")
    sheet.set_cell(3, 1, "7")
    return Workbook.from_sheets([sheet])


def test_available_is_true():
    assert ods_io.available() is True


def test_round_trip_strings_numbers_blanks(tmp_path):
    wb = _make_workbook()
    target = tmp_path / "out.ods"
    ods_io.save_ods(wb, target)
    assert target.exists()

    back = ods_io.load_ods(target)
    sheet = back.sheet

    # Header text survives.
    assert sheet.display(0, 0) == "Name"
    assert sheet.display(0, 1) == "Score"
    assert sheet.display(1, 0) == "Alice"

    # Numeric value survives (as a number).
    assert sheet.get_value(1, 1) == 42

    # Blank cells stay blank.
    assert sheet.get_raw(2, 0) == ""
    assert sheet.get_raw(2, 1) == ""

    # Sheet name is preserved.
    assert sheet.name == "Data"


def test_saved_file_is_valid_ods_package(tmp_path):
    wb = _make_workbook()
    target = tmp_path / "pkg.ods"
    ods_io.save_ods(wb, target)

    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
        # mimetype must be FIRST and STORED (uncompressed).
        assert names[0] == "mimetype"
        info = zf.getinfo("mimetype")
        assert info.compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype").decode() == (
            "application/vnd.oasis.opendocument.spreadsheet"
        )
        assert "content.xml" in names
        assert "META-INF/manifest.xml" in names


def test_columns_repeated_does_not_inflate(tmp_path):
    """A hand-built content.xml with a huge repeated empty run collapses."""
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        "<office:body><office:spreadsheet>"
        '<table:table table:name="Sheet1">'
        "<table:table-row>"
        '<table:table-cell office:value-type="string"><text:p>A</text:p>'
        "</table:table-cell>"
        '<table:table-cell table:number-columns-repeated="3"/>'
        '<table:table-cell office:value-type="string"><text:p>B</text:p>'
        "</table:table-cell>"
        "</table:table-row>"
        "<table:table-row "
        'table:number-rows-repeated="100000"/>'
        "</table:table>"
        "</office:spreadsheet></office:body>"
        "</office:document-content>"
    )
    target = tmp_path / "repeated.ods"
    with zipfile.ZipFile(target, "w") as zf:
        zf.writestr(
            zipfile.ZipInfo("mimetype"),
            "application/vnd.oasis.opendocument.spreadsheet",
            compress_type=zipfile.ZIP_STORED,
        )
        zf.writestr("content.xml", content)

    wb = ods_io.load_ods(target)
    sheet = wb.sheet

    # "A" at col 0, the 3 repeated empty cells produce nothing, "B" at col 4.
    assert sheet.display(0, 0) == "A"
    assert sheet.display(0, 4) == "B"
    # The trailing 100000 empty repeated rows must NOT create cells.
    n_rows, n_cols = sheet.used_bounds()
    assert n_rows == 1
    assert n_cols == 5
    assert len(list(sheet.iter_cells())) == 2


def test_columns_repeated_with_content_expands(tmp_path):
    """A non-empty repeated cell expands to N copies."""
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        "<office:body><office:spreadsheet>"
        '<table:table table:name="Sheet1">'
        "<table:table-row>"
        '<table:table-cell office:value-type="string" '
        'table:number-columns-repeated="3"><text:p>X</text:p>'
        "</table:table-cell>"
        "</table:table-row>"
        "</table:table>"
        "</office:spreadsheet></office:body>"
        "</office:document-content>"
    )
    target = tmp_path / "expand.ods"
    with zipfile.ZipFile(target, "w") as zf:
        zf.writestr(
            zipfile.ZipInfo("mimetype"),
            "application/vnd.oasis.opendocument.spreadsheet",
            compress_type=zipfile.ZIP_STORED,
        )
        zf.writestr("content.xml", content)

    sheet = ods_io.load_ods(target).sheet
    assert sheet.display(0, 0) == "X"
    assert sheet.display(0, 1) == "X"
    assert sheet.display(0, 2) == "X"
    assert sheet.used_bounds() == (1, 3)


def test_load_garbage_raises_ods_error(tmp_path):
    bad = tmp_path / "garbage.ods"
    bad.write_bytes(b"this is definitely not a zip file")
    with pytest.raises(ods_io.OdsError):
        ods_io.load_ods(bad)
