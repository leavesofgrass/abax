"""7-Zip (.7z) support — the py7zr adapter and the unified archive facade.

The real .7z round-trip tests are skipped when py7zr isn't installed; the facade
routing and fallback-message tests always run."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from abax.core.archive import ArchiveError
from abax.engine import archive7z
from abax.engine import archives as A

_HAS_7Z = archive7z.available()
requires_7z = pytest.mark.skipif(not _HAS_7Z, reason="py7zr not installed")


# --- facade routing / availability (always run) ------------------------------


def test_create_exts_reflects_7z_availability():
    exts = A.create_exts()
    assert ".zip" in exts and ".tar.gz" in exts
    assert (".7z" in exts) == _HAS_7Z


def test_zip_still_routes_through_core(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    dest = tmp_path / "out.zip"
    A.create_archive([str(tmp_path / "a.txt")], str(dest))
    assert dest.exists()
    assert "a.txt" in A.list_archive(str(dest))
    assert A.is_archive(str(dest))


def test_read_member_from_zip(tmp_path):
    (tmp_path / "data.csv").write_bytes(b"x,y\n1,2\n")  # exact bytes (no CRLF)
    dest = tmp_path / "z.zip"
    A.create_archive([str(tmp_path / "data.csv")], str(dest))
    assert A.read_member(str(dest), "data.csv") == b"x,y\n1,2\n"


def test_extract_member_to_temp_keeps_extension(tmp_path):
    (tmp_path / "sheet.csv").write_text("a\n1\n", encoding="utf-8")
    dest = tmp_path / "z.zip"
    A.create_archive([str(tmp_path / "sheet.csv")], str(dest))
    out = A.extract_member_to_temp(str(dest), "sheet.csv")
    assert out.endswith("sheet.csv")
    assert Path(out).read_text(encoding="utf-8") == "a\n1\n"


def test_7z_helpers_fail_closed_without_py7zr(monkeypatch):
    # Simulate py7zr absent even if installed: a None entry makes `import py7zr`
    # raise ImportError. Opening/creating .7z then raises an actionable error.
    monkeypatch.setitem(sys.modules, "py7zr", None)
    assert archive7z.available() is False
    with pytest.raises(ArchiveError, match="py7zr"):
        archive7z.list_7z("x.7z")
    # is_archive on a .7z path is False when the tool is missing (not an error).
    assert A.is_archive("nope.7z") is False


# --- real .7z round-trip (needs py7zr) ---------------------------------------


@requires_7z
def test_7z_create_list_extract_round_trip(tmp_path):
    (tmp_path / "one.txt").write_text("uno", encoding="utf-8")
    (tmp_path / "two.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    dest = tmp_path / "bundle.7z"
    A.create_archive([str(tmp_path / "one.txt"), str(tmp_path / "two.csv")], str(dest))
    assert dest.exists()

    names = set(A.list_archive(str(dest)))
    assert {"one.txt", "two.csv"} <= names
    assert A.is_archive(str(dest))

    out = tmp_path / "unpacked"
    A.extract_archive(str(dest), str(out))
    assert (out / "one.txt").read_text(encoding="utf-8") == "uno"
    assert (out / "two.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"


@requires_7z
def test_7z_read_and_extract_single_member(tmp_path):
    (tmp_path / "grid.csv").write_bytes(b"x\n7\n")  # exact bytes (no CRLF)
    dest = tmp_path / "s.7z"
    A.create_archive([str(tmp_path / "grid.csv")], str(dest))
    assert A.read_member(str(dest), "grid.csv") == b"x\n7\n"
    temp = A.extract_member_to_temp(str(dest), "grid.csv")
    assert temp.endswith("grid.csv")
    assert Path(temp).read_bytes() == b"x\n7\n"


@requires_7z
def test_7z_member_opens_as_workbook(tmp_path):
    # The end-to-end promise: a supported file inside a .7z extracts and loads.
    from abax.engine.document import Document

    (tmp_path / "book.csv").write_text("name,val\nfoo,10\n", encoding="utf-8")
    dest = tmp_path / "wb.7z"
    A.create_archive([str(tmp_path / "book.csv")], str(dest))
    temp = A.extract_member_to_temp(str(dest), "book.csv")
    doc = Document.open(temp)
    assert doc.workbook.sheet.get("A1") == "name"
    assert doc.workbook.sheet.get("B2") == 10
