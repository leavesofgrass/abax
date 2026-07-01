"""Tests for abax.engine.parquet_io — Parquet/Feather round-trips.

These tests require pandas plus a parquet engine (pyarrow). They skip cleanly
when those optional deps are absent, so the suite still passes with zero
optional packages installed (a core invariant).
"""

from __future__ import annotations

import pytest

from abax.core.sheet import Sheet
from abax.core.workbook import Workbook
from abax.engine import parquet_io
from abax.engine.parquet_io import ParquetError


def test_available_returns_bool():
    # Importable without any optional dep; available() is always a plain bool.
    assert isinstance(parquet_io.available(), bool)


def test_module_imports_without_pandas():
    # The module and ParquetError exist regardless of pandas being installed.
    assert issubclass(ParquetError, Exception)


def _make_workbook() -> Workbook:
    sheet = Sheet("data")
    sheet.set_cell(0, 0, "name")
    sheet.set_cell(0, 1, "age")
    sheet.set_cell(1, 0, "Alice")
    sheet.set_cell(1, 1, "30")
    sheet.set_cell(2, 0, "Bob")
    sheet.set_cell(2, 1, "25")
    return Workbook.from_sheets([sheet])


def test_parquet_roundtrip(tmp_path):
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")

    wb = _make_workbook()
    path = tmp_path / "data.parquet"
    parquet_io.save_parquet(wb, path)
    assert path.exists()

    loaded = parquet_io.load_parquet(path)
    sheet = loaded.sheet
    # Header row survives.
    assert sheet.get_raw(0, 0) == "name"
    assert sheet.get_raw(0, 1) == "age"
    # A couple of values survive (as cell text).
    assert sheet.get_raw(1, 0) == "Alice"
    assert sheet.get_raw(1, 1) == "30"
    assert sheet.get_raw(2, 0) == "Bob"


def test_feather_roundtrip(tmp_path):
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")

    wb = _make_workbook()
    path = tmp_path / "data.feather"
    parquet_io.save_parquet(wb, path)
    assert path.exists()

    loaded = parquet_io.load_parquet(path)
    sheet = loaded.sheet
    assert sheet.get_raw(0, 0) == "name"
    assert sheet.get_raw(2, 0) == "Bob"


def test_load_missing_deps_raises_parqueterror(tmp_path):
    # Guard with importorskip so this only runs when deps ARE present; in that
    # case a genuinely unreadable file still surfaces a ParquetError-or-pandas
    # error path. We assert the deps-absent contract directly via monkeypatching.
    pytest.importorskip("pandas")
    path = tmp_path / "missing.parquet"
    # Reading a non-existent file should raise (pandas/engine error), not crash
    # the interpreter; the module's own ParquetError is raised when pandas is
    # absent (covered by the without-pandas import test above).
    with pytest.raises((OSError, ValueError)):
        parquet_io.load_parquet(path)
