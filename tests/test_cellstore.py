"""The cell-storage seam (:mod:`abax.core.cellstore`).

DictCellStore is the default backing store — a behaviourally-identical ``dict``
subclass — and the swap point for a future windowed/lazy store. These tests pin
the contract the rest of the engine (and a replacement store) relies on.
"""

from __future__ import annotations

from abax.core.cellstore import CellStore, DictCellStore
from abax.core.sheet import Sheet


def test_dictcellstore_is_a_dict_and_a_cellstore():
    store = DictCellStore()
    assert isinstance(store, dict)          # drop-in for every plain-dict caller
    assert isinstance(store, CellStore)     # satisfies the documented Protocol
    assert len(store) == 0 and not store


def test_dictcellstore_supports_the_mapping_ops_the_engine_uses():
    store = DictCellStore()
    store[(0, 0)] = "a"
    store[(1, 2)] = "b"
    assert store[(0, 0)] == "a"
    assert store.get((1, 2)) == "b"
    assert store.get((9, 9)) is None        # missing key = blank cell
    assert (0, 0) in store and (5, 5) not in store
    assert set(store.keys()) == {(0, 0), (1, 2)}
    assert set(store) == {(0, 0), (1, 2)}   # iterates keys
    assert dict(store.items()) == {(0, 0): "a", (1, 2): "b"}
    assert len(store) == 2 and bool(store)
    assert store.pop((0, 0), None) == "a"
    assert store.pop((0, 0), None) is None  # idempotent with default
    assert len(store) == 1


def test_dictcellstore_accepts_an_initial_mapping():
    # The row/col shift in Sheet rebuilds the store from a comprehension.
    store = DictCellStore({(0, 0): "x", (3, 4): "y"})
    assert isinstance(store, DictCellStore)
    assert store[(3, 4)] == "y" and len(store) == 2


def test_sheet_uses_dictcellstore_and_behaves_identically():
    sh = Sheet()
    assert isinstance(sh._cells, DictCellStore)
    sh.set_cell(0, 0, "1")
    sh.set_cell(1, 0, "=A1+1")
    sh.recalculate()
    assert sh.get_value(1, 0) == 2.0
    # The store stays a DictCellStore across a structural shift (insert row),
    # which rebuilds it via a comprehension.
    sh.insert_rows(0, 1)
    assert isinstance(sh._cells, DictCellStore)
    assert sh.get_value(2, 0) == 2.0        # the formula moved down one row
