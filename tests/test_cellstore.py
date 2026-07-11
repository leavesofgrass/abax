"""The cell-storage seam (:mod:`abax.core.cellstore`).

DictCellStore is the default backing store — a behaviourally-identical ``dict``
subclass — and the swap point for a future windowed/lazy store. These tests pin
the contract the rest of the engine (and a replacement store) relies on.
"""

from __future__ import annotations

import os
import random

from abax.core.cells import Cell
from abax.core.cellstore import CellStore, DictCellStore, WindowedCellStore
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


# --------------------------------------------------------------------------- #
# WindowedCellStore — bounded resident set + on-disk spill (opt-in)
# --------------------------------------------------------------------------- #


def test_windowed_store_bounds_resident_and_spans_all():
    w = WindowedCellStore(capacity=5)
    try:
        for i in range(100):
            w[(i, 0)] = Cell(str(i))
        assert w.resident_count() <= 5          # window is bounded
        assert len(w) == 100                    # but len spans resident + spilled
        assert set(w.keys()) == {(i, 0) for i in range(100)}
        assert (73, 0) in w and (999, 0) not in w
        # A spilled cell pages back in with the right source text.
        assert w[(73, 0)].raw == "73"
        assert w.get((5, 0)).raw == "5"
        assert w.get((999, 0)) is None
        # items() spans everything without exploding the window.
        got = {k: c.raw for k, c in w.items()}
        assert got == {(i, 0): str(i) for i in range(100)}
        assert w.resident_count() <= 6          # scan stayed bounded
    finally:
        w.close()


def test_windowed_store_matches_a_plain_dict_under_random_ops():
    """Differential test: identical ops on a WindowedCellStore and a ref dict
    must yield identical observable results (compared by cell source text)."""
    rng = random.Random(20260711)
    w = WindowedCellStore(capacity=8)
    ref: dict = {}
    try:
        for _ in range(3000):
            key = (rng.randrange(20), rng.randrange(20))
            op = rng.random()
            if op < 0.55:                        # set
                raw = str(rng.randrange(1000))
                w[key] = Cell(raw)
                ref[key] = raw
            elif op < 0.75:                      # pop
                a = w.pop(key, None)
                b = ref.pop(key, None)
                assert (a.raw if a is not None else None) == b
            elif op < 0.85:                      # membership
                assert (key in w) == (key in ref)
            else:                                # get
                a = w.get(key)
                assert (a.raw if a is not None else None) == ref.get(key)
            assert len(w) == len(ref)
            assert w.resident_count() <= 8
        # Final full comparison via items().
        assert {k: c.raw for k, c in w.items()} == ref
    finally:
        w.close()


def _fill_sheet(sh, edits):
    for (r, c), raw in edits:
        sh.set_cell(r, c, raw)
    sh.recalculate()


def test_windowed_sheet_computes_identically_to_a_plain_sheet():
    """The real proof: a windowed sheet and a plain sheet, driven through the
    same random edits (literals + formulas that reference other cells, so recalc
    must page precedents in), must agree on every cell value."""
    rng = random.Random(42)
    edits = []
    for r in range(30):
        for c in range(4):
            if rng.random() < 0.5:
                edits.append(((r, c), str(rng.randrange(1, 50))))
            elif r > 0:
                # a formula referencing a couple of earlier cells
                edits.append(((r, c), f"=A{r} + {chr(65 + c)}{r} + 1"))
    plain = Sheet()
    windowed = Sheet(cell_store=WindowedCellStore(capacity=6))
    try:
        _fill_sheet(plain, edits)
        _fill_sheet(windowed, edits)
        assert windowed._cells.resident_count() <= 6
        for r in range(30):
            for c in range(4):
                assert repr(plain.get_value(r, c)) == repr(windowed.get_value(r, c)), (r, c)
    finally:
        windowed._cells.close()


def test_windowed_store_survives_a_structural_shift():
    """insert_rows rebuilds the store via remap(); the windowed type + values
    must survive, and formulas must track the shift."""
    sh = Sheet(cell_store=WindowedCellStore(capacity=4))
    try:
        sh.set_cell(0, 0, "10")
        for r in range(1, 10):
            sh.set_cell(r, 0, f"=A{r}+1")
        sh.recalculate()
        assert sh.get_value(9, 0) == 19.0
        sh.insert_rows(0, 2)                     # push everything down two rows
        assert isinstance(sh._cells, WindowedCellStore)
        assert sh._cells.resident_count() <= 4
        assert sh.get_value(11, 0) == 19.0       # value tracked the shift
    finally:
        sh._cells.close()


def test_windowed_store_cleans_up_its_spill_file():
    w = WindowedCellStore(capacity=2)
    for i in range(10):
        w[(i, 0)] = Cell(str(i))
    path = w._spill_path
    assert os.path.exists(path)
    w.close()
    assert not os.path.exists(path)
    w.close()                                    # idempotent


def test_windowed_eviction_is_lru():
    """Reading a cell keeps it resident; the least-recently-used one is evicted."""
    w = WindowedCellStore(capacity=3)
    try:
        for i in range(3):
            w[(i, 0)] = Cell(str(i))         # resident: 0, 1, 2
        _ = w[(0, 0)]                        # touch 0 -> most-recently-used
        w[(3, 0)] = Cell("3")               # overflow -> evict LRU, which is 1
        assert (1, 0) in w._spilled          # least-recently-used was spilled
        assert w.resident_count() == 3
        for k in [(0, 0), (2, 0), (3, 0)]:   # these stayed resident
            assert k not in w._spilled
        assert w[(1, 0)].raw == "1"          # and it still pages back correctly
    finally:
        w.close()
