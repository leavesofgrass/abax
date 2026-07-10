"""The public automation API (``abax.api``): build, read, save, reopen, errors."""

from __future__ import annotations

import pytest

from abax import api
from abax.core.errors import CellError


def test_new_book_has_one_sheet():
    book = api.new()
    assert book.sheets == ["Sheet1"]
    assert book.active.name == "Sheet1"
    assert len(book) == 1
    assert "Sheet1" in book
    assert "Nope" not in book


def test_set_and_read_scalar_and_sum():
    book = api.new()
    sheet = book.active
    sheet["A1"] = 10
    sheet["A2"] = 20
    sheet["A3"] = 30
    sheet["B1"] = "=SUM(A1:A3)"
    # The SUM computes on read — no explicit recalc needed (auto calc mode).
    assert sheet["B1"] == 60
    # Coordinate accessors mirror the subscript ones (zero-based).
    assert sheet.value(0, 0) == 10
    sheet.set(3, 0, 40)          # A4 = 40
    assert sheet["B1"] == 60     # A4 is outside the SUM range
    sheet["A3"] = 300            # a dependency changes -> SUM refreshes on read
    assert sheet["B1"] == 330


def test_read_raw_formula_vs_value():
    book = api.new()
    sheet = book.active
    sheet["A1"] = 2
    sheet["A2"] = "=A1*21"
    assert sheet["A2"] == 42            # computed value
    assert sheet.formula("A2") == "=A1*21"  # raw source
    assert sheet.formula("A1") == "2"       # literal source
    assert sheet.formula("Z9") == ""        # blank cell


def test_read_range_returns_2d_list():
    book = api.new()
    sheet = book.active
    sheet["A1"] = 1
    sheet["B1"] = 2
    sheet["A2"] = "=A1+10"
    sheet["B2"] = "=B1+10"
    grid = sheet["A1:B2"]
    assert grid == [[1, 2], [11, 12]]


def test_error_value_surfaces_as_cellerror():
    book = api.new()
    sheet = book.active
    sheet["A1"] = "=1/0"
    val = sheet["A1"]
    assert isinstance(val, CellError)
    assert str(val) == "#DIV/0!"


def test_add_sheet_and_cross_sheet_formula():
    book = api.new()
    data = book.add_sheet("Data")
    assert isinstance(data, api.Sheet)
    assert book.sheets == ["Sheet1", "Data"]
    # Wrapper identity is stable.
    assert book["Data"] is data
    data["A1"] = 5
    book["Sheet1"]["A1"] = "=Data!A1*2"
    assert book["Sheet1"]["A1"] == 10


def test_add_sheet_duplicate_raises_value_error():
    book = api.new()
    with pytest.raises(ValueError):
        book.add_sheet("Sheet1")


def test_missing_sheet_raises_key_error():
    book = api.new()
    with pytest.raises(KeyError):
        _ = book["DoesNotExist"]


def test_bad_reference_raises_value_error():
    book = api.new()
    sheet = book.active
    with pytest.raises(ValueError):
        _ = sheet["not-a-ref"]
    with pytest.raises(ValueError):
        sheet["A1:B2"] = 5  # range assignment is rejected


def test_save_and_reopen_roundtrip(tmp_path):
    path = tmp_path / "book.abax"
    book = api.new()
    sheet = book.active
    sheet["A1"] = 10
    sheet["A2"] = 20
    sheet["A3"] = "=SUM(A1:A2)"
    extra = book.add_sheet("Notes")
    extra["A1"] = "hello"
    book.save(path)
    assert path.exists()

    reopened = api.open(path)
    assert reopened.sheets == ["Sheet1", "Notes"]
    assert reopened.active["A3"] == 30                 # formula survives + recomputes
    assert reopened.active.formula("A3") == "=SUM(A1:A2)"
    assert reopened["Notes"]["A1"] == "hello"


def test_save_without_path_raises(tmp_path):
    book = api.new()
    with pytest.raises(ValueError):
        book.save()  # never opened from / saved to a path


def test_context_manager(tmp_path):
    path = tmp_path / "ctx.abax"
    with api.new() as book:
        book.active["A1"] = "=1+2"
        assert book.active["A1"] == 3
        book.save(path)
    # Reopen within a with-block; the block does not auto-save on exit.
    with api.open(path) as reopened:
        assert reopened.active["A1"] == 3


def test_recalc_is_available_and_idempotent():
    book = api.new()
    sheet = book.active
    sheet["A1"] = 1
    sheet["A2"] = "=A1+1"
    book.recalc()
    assert sheet["A2"] == 2


def test_none_clears_cell():
    book = api.new()
    sheet = book.active
    sheet["A1"] = 99
    assert sheet["A1"] == 99
    sheet["A1"] = None
    assert sheet["A1"] is None
    assert sheet.formula("A1") == ""
