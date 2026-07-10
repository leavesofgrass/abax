"""RESTTABLE — array-spilling live data (abax.core.livearray).

Shaping (:func:`records_to_grid`) is exercised as a pure function; the formula
is exercised against the process-wide hub with an injected in-memory transport,
mirroring tests/test_livedata.py — no network is ever touched. Every test that
enables the hub disables it again in ``finally`` so state never leaks.
"""

from __future__ import annotations

import time

import pytest

from abax.core import livearray, livedata
from abax.core.errors import CellError, is_error
from abax.core.io.restimport import RestImportError
from abax.core.livearray import records_to_grid
from abax.core.livedata import OFF_MARKER
from abax.core.values import RangeValue


def _wait_for(pred, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


def _scripted_transport(values, *, then_block=True):
    """A transport that yields each of *values* once, then optionally blocks."""
    def _t(url, *, interval, stop_event):
        for v in values:
            yield (True, v)
        if then_block:
            stop_event.wait()
    return _t


PAYLOAD = {
    "data": {
        "items": [
            {"sym": "AAPL", "price": 189.5, "vol": 1000},
            {"sym": "MSFT", "price": 402},
        ]
    }
}


# -- records_to_grid: pure shaping ------------------------------------------

def test_grid_explicit_columns():
    grid = records_to_grid(PAYLOAD, "data.items", ["sym", "price"])
    assert grid == [["sym", "price"], ["AAPL", 189.5], ["MSFT", 402]]


def test_grid_numbers_stay_numbers():
    grid = records_to_grid(PAYLOAD, "data.items", ["price", "vol"])
    assert isinstance(grid[1][0], float) and grid[1][0] == 189.5
    assert isinstance(grid[1][1], int) and grid[1][1] == 1000
    flags = records_to_grid([{"ok": True}], None, ["ok"])
    assert flags[1][0] is True


def test_grid_derived_columns_union_first_seen():
    records = [{"a": 1}, {"b": 2, "a": 3}, {"c": None}]
    grid = records_to_grid(records)
    assert grid[0] == ["a", "b", "c"]            # union, first-seen order
    assert grid[1] == [1, "", ""]                # missing keys -> ""
    assert grid[2] == [3, 2, ""]
    assert grid[3] == ["", "", ""]               # None -> "" (coerce)


def test_grid_dotted_columns_dig_into_records():
    records = [
        {"sym": "AAPL", "quote": {"last": 189.5}},
        {"sym": "MSFT"},                          # no quote at all
    ]
    grid = records_to_grid(records, None, ["sym", "quote.last"])
    assert grid == [["sym", "quote.last"], ["AAPL", 189.5], ["MSFT", ""]]


def test_grid_nested_leaf_compacts_to_json_text():
    grid = records_to_grid([{"sym": "AAPL", "tags": [1, 2]}], None, ["sym", "tags"])
    assert grid[1] == ["AAPL", "[1,2]"]


def test_grid_root_list_and_single_object():
    assert records_to_grid([{"x": 1}]) == [["x"], [1]]
    assert records_to_grid({"x": 1}) == [["x"], [1]]  # object -> one row


def test_grid_empty_records():
    empty = {"data": {"items": []}}
    # Explicit columns: header row alone.
    assert records_to_grid(empty, "data.items", ["sym"]) == [["sym"]]
    # Derived columns: nothing to derive from.
    with pytest.raises(RestImportError):
        records_to_grid(empty, "data.items")


def test_grid_bad_path_raises():
    with pytest.raises(RestImportError):
        records_to_grid(PAYLOAD, "data.nope")
    with pytest.raises(RestImportError):
        records_to_grid(PAYLOAD, "data.items[0].price")  # scalar, not records


# -- columns-argument normalization ------------------------------------------

def test_columns_list_forms():
    assert livearray._columns_list(None) is None
    assert livearray._columns_list("") is None
    assert livearray._columns_list("sym, price") == ["sym", "price"]
    assert livearray._columns_list(["sym", "price"]) == ["sym", "price"]
    assert livearray._columns_list([["sym", "price"]]) == ["sym", "price"]
    assert livearray._columns_list(RangeValue([["sym", "price"]])) == ["sym", "price"]


# -- the RESTTABLE formula against the hub -----------------------------------

def test_resttable_off_marker_when_disabled():
    livedata.HUB.set_enabled(False)
    assert livearray._resttable(["http://h/x", "data.items"]) == OFF_MARKER
    assert livedata.HUB.source_count() == 0  # no connection opened


def test_resttable_bad_args():
    livedata.HUB.set_enabled(True)
    try:
        assert is_error(livearray._resttable([""]))          # empty url
        assert is_error(livearray._resttable([["a", "b"]]))  # range as url
        assert is_error(livearray._resttable(
            ["http://h", "data.items", None, "notanumber"]))
    finally:
        livedata.HUB.set_enabled(False)


def test_resttable_na_before_first_document():
    livedata.HUB.set_enabled(True)
    try:
        url = "http://h/pending-table"
        # Pre-seed the exact key the formula computes: whole document (path "")
        # at the default 5.0s interval — with a transport that never yields.
        livedata.HUB.subscribe("rest", url, "", 5.0,
                               transport=lambda u, **k: iter(()))
        result = livearray._resttable([url, "data.items"])
        assert is_error(result) and result.code == CellError.NA
    finally:
        livedata.HUB.set_enabled(False)


def test_resttable_spills_grid_from_seeded_hub():
    livedata.HUB.set_enabled(True)
    try:
        url = "http://h/table"
        # Pre-seed the hub under the exact key the formula computes (kind
        # "rest", url, EMPTY path, default interval 5.0); subscribe is
        # idempotent, so the formula reuses this source instead of opening one.
        key = livedata.HUB.subscribe(
            "rest", url, "", 5.0, transport=_scripted_transport([PAYLOAD]))
        assert _wait_for(lambda: livedata.HUB.latest(key)[0] is not None)

        grid = livearray._resttable([url, "data.items", ["sym", "price"]])
        assert grid == [["sym", "price"], ["AAPL", 189.5], ["MSFT", 402]]
        assert isinstance(grid[1][1], float)  # survived the hub's JSON caching

        # Same subscription serves comma-string columns and derived columns.
        assert livearray._resttable([url, "data.items", "sym,price"]) == grid
        derived = livearray._resttable([url, "data.items"])
        assert derived[0] == ["sym", "price", "vol"]
        assert livedata.HUB.source_count() == 1  # everything shared one poller
    finally:
        livedata.HUB.set_enabled(False)


def test_resttable_shaping_error_is_value():
    livedata.HUB.set_enabled(True)
    try:
        url = "http://h/table-badpath"
        key = livedata.HUB.subscribe(
            "rest", url, "", 5.0, transport=_scripted_transport([PAYLOAD]))
        assert _wait_for(lambda: livedata.HUB.latest(key)[0] is not None)
        result = livearray._resttable([url, "data.missing"])
        assert is_error(result) and result.code == CellError.VALUE
    finally:
        livedata.HUB.set_enabled(False)


def test_register_exposes_resttable():
    fns: dict = {}
    livearray.register(fns)
    assert fns["RESTTABLE"] is livearray._resttable
