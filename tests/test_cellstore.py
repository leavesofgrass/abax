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


def test_windowed_sheet_bounds_its_ast_caches():
    """A windowed sheet caps _ast_cache/_rast_cache to the window, so they can't
    grow to O(all cells) during a full recalc. Uses depth-1 formulas (each reads
    only A1) so there is no deep-chain recursion — just many cached ASTs."""
    from abax.core.cellstore import BoundedCache
    sh = Sheet(cell_store=WindowedCellStore(capacity=100))
    try:
        sh.set_cell(0, 0, "10")
        for i in range(1, 1000):
            sh.set_cell(i, 0, f"=$A$1 + {i}")
        sh.recalculate()
        assert isinstance(sh._ast_cache, BoundedCache)
        assert len(sh._ast_cache) <= 100          # capped to the window
        assert sh.get_value(999, 0) == 10 + 999   # values still correct
        assert sh.get_value(500, 0) == 10 + 500
    finally:
        sh._cells.close()


def test_default_sheet_uses_plain_unbounded_caches():
    """The default (non-windowed) sheet keeps plain dict caches — zero overhead,
    unchanged behaviour on the hot recalc path."""
    sh = Sheet()
    assert type(sh._ast_cache) is dict
    assert type(sh._rast_cache) is dict


# --------------------------------------------------------------------------- #
# Opt-in wiring: Workbook.use_windowed_stores + the setting
# --------------------------------------------------------------------------- #


def test_workbook_use_windowed_stores_rehomes_and_preserves_values():
    from abax.core.workbook import Workbook
    wb = Workbook()
    sh = wb.sheet
    sh.set_cell(0, 0, "100")
    for r in range(1, 60):
        sh.set_cell(r, 0, f"=$A$1 + {r}")     # depth-1 formulas (no deep chain)
    wb.recalculate()
    before = {r: sh.get_value(r, 0) for r in range(60)}
    assert isinstance(sh._cells, DictCellStore) and not isinstance(sh._cells, WindowedCellStore)

    wb.use_windowed_stores(10)                # opt in
    assert isinstance(sh._cells, WindowedCellStore)
    assert sh._cells.resident_count() <= 10
    wb.recalculate()
    assert {r: sh.get_value(r, 0) for r in range(60)} == before   # values identical
    sh._cells.close()


def test_use_windowed_stores_zero_is_a_no_op():
    from abax.core.workbook import Workbook
    wb = Workbook()
    wb.sheet.set_cell(0, 0, "1")
    wb.use_windowed_stores(0)
    assert type(wb.sheet._cells) is DictCellStore   # unchanged


def test_windowed_store_capacity_setting_defaults_off():
    from abax.settings import Settings
    assert Settings().windowed_store_capacity == 0


# --------------------------------------------------------------------------- #
# Deep dependency chains — the recursion-headroom guard in Sheet
# --------------------------------------------------------------------------- #


def _build_chain(sheet: Sheet, depth: int) -> None:
    """A1=1, A2=A1+1, ... A<depth>=A<depth-1>+1 — a straight, non-circular chain."""
    sheet.set_cell(0, 0, "1")
    for r in range(1, depth):
        sheet.set_cell(r, 0, f"=A{r} + 1")


def test_deep_chain_evaluates_on_plain_store():
    """A cold top-down read of a 2000-deep chain must yield the value, not a
    false #CIRC!. (Historically the interpreter's default recursion limit
    capped cold evaluation at a chain ~166 deep — on every store.)"""
    sh = Sheet(name="deep")
    _build_chain(sh, 2000)
    assert sh.get_value(1999, 0) == 2000


def test_deep_chain_evaluates_on_windowed_store_below_capacity():
    """Chain depth must not be constrained by the window capacity: a 2000-deep
    chain on a capacity-50 store pages through and evaluates correctly."""
    sh = Sheet(name="deepwin")
    _build_chain(sh, 2000)
    sh.use_windowed_store(50)
    try:
        assert sh.get_value(1999, 0) == 2000
        assert sh._cells.resident_count() <= 50
    finally:
        sh._cells.close()


def test_recursion_limit_restored_after_deep_evaluation():
    import sys
    before = sys.getrecursionlimit()
    sh = Sheet(name="restore")
    _build_chain(sh, 1200)
    assert sh.get_value(1199, 0) == 1200
    assert sys.getrecursionlimit() == before


def test_true_cycle_still_reports_circ_on_both_stores():
    """The headroom guard must not weaken genuine cycle detection."""
    from abax.core.errors import CellError

    for windowed in (False, True):
        sh = Sheet(name="cyc")
        sh.set_cell(0, 0, "=B1")
        sh.set_cell(0, 1, "=A1")
        if windowed:
            sh.use_windowed_store(10)
        try:
            v = sh.get_value(0, 0)
            assert isinstance(v, CellError) and str(v) == "#CIRC!"
        finally:
            if windowed:
                sh._cells.close()


# --------------------------------------------------------------------------- #
# Auto-windowing policy — Workbook.apply_windowing_policy
# --------------------------------------------------------------------------- #


def test_policy_auto_windows_only_large_sheets(monkeypatch):
    """Setting 0 (the default) windows sheets at/above the threshold and leaves
    small sheets on the plain store."""
    import abax.core.workbook as wbmod
    from abax.core.workbook import Workbook

    monkeypatch.setattr(wbmod, "AUTO_WINDOW_THRESHOLD", 100)
    wb = Workbook()
    big = wb.sheet
    for r in range(120):                       # >= patched threshold
        big.set_cell(r, 0, str(r))
    small = wb.add_sheet("small")
    small.set_cell(0, 0, "1")

    wb.apply_windowing_policy(0)
    try:
        assert isinstance(big._cells, WindowedCellStore)
        assert big._cells.capacity == WindowedCellStore.DEFAULT_CAPACITY
        assert not isinstance(small._cells, WindowedCellStore)
        # Values intact through the migration.
        assert big.get_value(119, 0) == 119
    finally:
        big._cells.close()


def test_policy_negative_never_windows(monkeypatch):
    import abax.core.workbook as wbmod
    from abax.core.workbook import Workbook

    monkeypatch.setattr(wbmod, "AUTO_WINDOW_THRESHOLD", 10)
    wb = Workbook()
    for r in range(50):
        wb.sheet.set_cell(r, 0, str(r))
    wb.apply_windowing_policy(-1)
    assert not isinstance(wb.sheet._cells, WindowedCellStore)


def test_policy_positive_windows_every_sheet():
    from abax.core.workbook import Workbook

    wb = Workbook()
    wb.sheet.set_cell(0, 0, "1")               # tiny — still windowed when >0
    tiny = wb.add_sheet("tiny")
    tiny.set_cell(0, 0, "2")
    wb.apply_windowing_policy(25)
    try:
        assert isinstance(wb.sheets[0]._cells, WindowedCellStore)
        assert isinstance(tiny._cells, WindowedCellStore)
        assert tiny._cells.capacity == 25
    finally:
        for sh in wb.sheets:
            sh._cells.close()


def test_document_open_applies_auto_policy(tmp_path, monkeypatch):
    """Document.open routes the setting through apply_windowing_policy."""
    import abax.core.workbook as wbmod
    from abax.engine.document import Document

    monkeypatch.setattr(wbmod, "AUTO_WINDOW_THRESHOLD", 5)
    csv = tmp_path / "big.csv"
    csv.write_text("\n".join(str(i) for i in range(20)), encoding="utf-8")
    doc = Document.open(csv)                   # default 0 -> auto
    try:
        assert isinstance(doc.workbook.sheet._cells, WindowedCellStore)
    finally:
        doc.workbook.sheet._cells.close()

    doc2 = Document.open(csv, windowed_capacity=-1)   # never
    assert not isinstance(doc2.workbook.sheet._cells, WindowedCellStore)


# --------------------------------------------------------------------------- #
# Windowing at LOAD time — the native envelope path builds the store directly
# (no plain-dict staging copy, no migrate-after-load memory spike)
# --------------------------------------------------------------------------- #


def _envelope_with_cells(n: int) -> dict:
    """An envelope whose sheet has ``n`` literal cells + one SUM over them all."""
    from abax.core.workbook import Workbook

    wb = Workbook()
    wb.sheet.set_cells_bulk((r, 0, str(r)) for r in range(n))
    wb.sheet.set_cell(0, 1, f"=SUM(A1:A{n})")
    return wb.to_envelope()


def test_from_envelope_builds_windowed_store_directly(monkeypatch):
    """A positive setting lands the sheet ON the windowed store during load:
    the migration function never runs, residency stays bounded (past-capacity
    cells spilled as they streamed in), and values — including a formula over
    the paged range — are correct."""
    from abax.core.workbook import Workbook

    def _no_migration(self, capacity):
        raise AssertionError("plain->windowed migration must not run at load")

    monkeypatch.setattr(Sheet, "use_windowed_store", _no_migration)
    wb = Workbook.from_envelope(_envelope_with_cells(120), windowed_capacity=25)
    sh = wb.sheet
    try:
        assert type(sh._cells) is WindowedCellStore
        assert sh._cells.capacity == 25
        assert len(sh._cells) == 121                  # 120 literals + the SUM
        assert sh._cells.resident_count() <= 25       # bounded THROUGH the load
        assert sh.get_value(0, 1) == sum(range(120))  # SUM over paged-out cells
        assert [sh.get_value(r, 0) for r in range(120)] == list(range(120))
    finally:
        sh._cells.close()


def test_from_envelope_auto_windows_large_sheets_at_load(monkeypatch):
    """Setting 0 (Auto) applies the threshold DURING load: a big sheet is built
    on the windowed store at the default capacity, a small one stays plain."""
    import abax.core.workbook as wbmod
    from abax.core.workbook import Workbook

    monkeypatch.setattr(wbmod, "AUTO_WINDOW_THRESHOLD", 100)
    wb = Workbook()
    wb.sheet.set_cells_bulk((r, 0, str(r)) for r in range(120))
    wb.add_sheet("small").set_cell(0, 0, "1")

    wb2 = Workbook.from_envelope(wb.to_envelope(), windowed_capacity=0)
    try:
        assert isinstance(wb2.sheets[0]._cells, WindowedCellStore)
        assert wb2.sheets[0]._cells.capacity == WindowedCellStore.DEFAULT_CAPACITY
        assert type(wb2.get_sheet("small")._cells) is DictCellStore
        assert wb2.sheets[0].get_value(119, 0) == 119
    finally:
        wb2.sheets[0]._cells.close()


def test_from_envelope_without_policy_or_negative_stays_plain(monkeypatch):
    """No ``windowed_capacity`` (callers that apply the policy later — or never,
    like save-a-copy snapshots) and the explicit ``-1`` both keep the plain
    store, even above the auto threshold."""
    import abax.core.workbook as wbmod
    from abax.core.workbook import Workbook

    monkeypatch.setattr(wbmod, "AUTO_WINDOW_THRESHOLD", 10)
    env = _envelope_with_cells(50)
    for wb2 in (Workbook.from_envelope(env),
                Workbook.from_envelope(env, windowed_capacity=-1)):
        assert type(wb2.sheet._cells) is DictCellStore
        assert wb2.sheet.get_value(5, 0) == 5


def test_document_open_native_windows_at_load_without_a_second_store(
        tmp_path, monkeypatch):
    """Opening a large native file constructs ONE windowed store — the loader's
    — and the delivered sheet holds exactly that instance. The old plain-then-
    migrate pass would construct a *second* store and swap it in; counting
    constructions pins the double-copy out (apply_windowing_policy still runs
    afterwards, as the fallback, and must leave the store untouched)."""
    import abax.core.workbook as wbmod
    from abax.core.workbook import Workbook
    from abax.engine.document import Document

    monkeypatch.setattr(wbmod, "AUTO_WINDOW_THRESHOLD", 5)
    wb = Workbook()
    wb.sheet.set_cells_bulk((r, 0, str(r)) for r in range(20))
    path = tmp_path / "big.abax"
    wb.save_json(path)

    created: list = []
    orig_init = WindowedCellStore.__init__

    def counting_init(self, *args, **kwargs):
        created.append(self)
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(WindowedCellStore, "__init__", counting_init)
    doc = Document.open(path)                     # default 0 -> auto policy
    sh = doc.workbook.sheet
    try:
        assert len(created) == 1                  # built once, at load...
        assert sh._cells is created[0]            # ...and never re-homed
        assert [sh.get_value(r, 0) for r in range(20)] == list(range(20))
    finally:
        sh._cells.close()


def test_use_windowed_store_is_idempotent_at_the_same_capacity():
    """Re-applying the policy to an already-windowed sheet must not re-copy:
    the same capacity keeps the very same store object; a different capacity
    still re-homes into a fresh store with values intact."""
    sh = Sheet(name="idem")
    for r in range(40):
        sh.set_cell(r, 0, str(r))
    sh.use_windowed_store(10)
    first = sh._cells
    assert isinstance(first, WindowedCellStore)

    sh.use_windowed_store(10)                     # same capacity -> no-op
    assert sh._cells is first

    sh.use_windowed_store(15)                     # different -> re-home
    try:
        assert sh._cells is not first
        assert sh._cells.capacity == 15
        assert [sh.get_value(r, 0) for r in range(40)] == list(range(40))
    finally:
        sh._cells.close()
