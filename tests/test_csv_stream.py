"""Tests for streaming / chunked CSV import with type inference."""

from __future__ import annotations

import pytest

from abax.core.io.csv_stream import (
    CsvStreamError,
    iter_chunks,
    load_csv_streaming,
    sniff_csv,
)


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


HEADER_CSV = (
    "id,name,score\n"
    "1,alice,9.5\n"
    "2,bob,8.0\n"
    "3,carol,7.25\n"
    "4,dave,6.5\n"
    "5,erin,10.0\n"
)


def test_sniff_header_csv(tmp_path):
    path = _write(tmp_path / "h.csv", HEADER_CSV)
    prof = sniff_csv(path)
    assert prof.has_header is True
    assert prof.columns == ["id", "name", "score"]
    assert prof.types == ["int", "text", "float"]
    assert prof.delimiter == ","
    assert prof.approx_rows == 5
    assert len(prof.sample_rows) == 5
    assert prof.sample_rows[0] == ["1", "alice", "9.5"]


def test_sniff_headerless_numeric(tmp_path):
    text = "1,2,3\n4,5,6\n7,8,9\n"
    path = _write(tmp_path / "n.csv", text)
    prof = sniff_csv(path)
    assert prof.has_header is False
    assert prof.columns == ["Column 1", "Column 2", "Column 3"]
    assert prof.types == ["int", "int", "int"]
    assert prof.delimiter == ","
    assert prof.approx_rows == 3


def test_sniff_tsv_delimiter(tmp_path):
    text = "id\tname\tscore\n1\talice\t9.5\n2\tbob\t8.0\n3\tx\t1.0\n"
    path = _write(tmp_path / "t.tsv", text)
    prof = sniff_csv(path)
    assert prof.delimiter == "\t"
    assert prof.columns == ["id", "name", "score"]
    assert prof.types == ["int", "text", "float"]


def test_iter_chunks(tmp_path):
    path = _write(tmp_path / "h.csv", HEADER_CSV)
    chunks = list(iter_chunks(path, chunk_rows=2))
    assert [len(c) for c in chunks] == [2, 2, 1]
    flat = [row for c in chunks for row in c]
    assert flat == [
        ["1", "alice", "9.5"],
        ["2", "bob", "8.0"],
        ["3", "carol", "7.25"],
        ["4", "dave", "6.5"],
        ["5", "erin", "10.0"],
    ]


def test_iter_chunks_headerless(tmp_path):
    text = "1,2\n3,4\n5,6\n"
    path = _write(tmp_path / "n.csv", text)
    chunks = list(iter_chunks(path, chunk_rows=2, has_header=False))
    flat = [row for c in chunks for row in c]
    assert flat == [["1", "2"], ["3", "4"], ["5", "6"]]


def test_load_streaming_roundtrip(tmp_path):
    path = _write(tmp_path / "h.csv", HEADER_CSV)
    wb = load_csv_streaming(path)
    sheet = wb.sheets[0]
    assert sheet.get_raw(0, 0) == "id"
    assert sheet.get_raw(0, 1) == "name"
    assert sheet.get_raw(0, 2) == "score"
    assert sheet.get_raw(1, 0) == "1"
    assert sheet.get_raw(1, 1) == "alice"
    assert sheet.get_raw(5, 1) == "erin"
    assert sheet.get_raw(5, 2) == "10.0"


def test_load_streaming_max_rows(tmp_path):
    path = _write(tmp_path / "h.csv", HEADER_CSV)
    wb = load_csv_streaming(path, max_rows=2)
    sheet = wb.sheets[0]
    # header + 2 data rows -> rows 0,1,2 populated; row 3 empty
    assert sheet.get_raw(0, 0) == "id"
    assert sheet.get_raw(1, 1) == "alice"
    assert sheet.get_raw(2, 1) == "bob"
    assert sheet.get_raw(3, 1) == ""


def test_load_streaming_coerce_types(tmp_path):
    # Under typeinfer's rules: an all-integer column is "int"; a column with a
    # decimal value is "float". coerce_types canonicalizes each column to its
    # inferred type's text: int "03" -> "3", float "9.50" -> "9.5".
    text = "qty,price\n03,9.50\n4,8.00\n5,7.5\n"
    path = _write(tmp_path / "c.csv", text)
    prof = sniff_csv(path)
    assert prof.types == ["int", "float"]
    wb = load_csv_streaming(path, coerce_types=True)
    sheet = wb.sheets[0]
    assert sheet.get_raw(1, 0) == "3"   # "03" -> "3" (int column)
    assert sheet.get_raw(2, 0) == "4"
    # float column coerced via float(): "9.50" -> "9.5", "8.00" -> "8.0"
    assert sheet.get_raw(1, 1) == "9.5"
    assert sheet.get_raw(2, 1) == "8.0"


def test_missing_file_raises(tmp_path):
    with pytest.raises(CsvStreamError):
        sniff_csv(str(tmp_path / "nope.csv"))


def test_empty_file_raises(tmp_path):
    path = _write(tmp_path / "empty.csv", "")
    with pytest.raises(CsvStreamError):
        sniff_csv(path)
