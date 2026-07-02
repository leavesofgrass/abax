"""Targeted tests for the incremental recalc dependency graph (WS1).

These pin the specific correctness fixes the design's adversarial review turned
up: transitive invalidation below a volatile/dynamic cell, cross-sheet single
cell dependents, range membership, and the spill fall-back. The broad
"incremental == full recalc" guarantee lives in test_depgraph_property.py.
"""

from __future__ import annotations

import pytest

import abax.core.depgraph as depgraph
from abax.core.depgraph import ALWAYS_DIRTY_FUNCS, DepGraph, analyze
from abax.core.workbook import Workbook

# Some tests inspect the index internals, which only exist under incremental mode.
incremental_only = pytest.mark.skipif(
    not depgraph.ABAX_INCREMENTAL, reason="dependency index only built when incremental"
)


def _wb(*sheet_names):
    wb = Workbook()
    wb.sheets[0].name = sheet_names[0] if sheet_names else "S1"
    for nm in sheet_names[1:]:
        wb.add_sheet(nm)
    return wb


# --- basic incremental invalidation --------------------------------------

def test_chain_updates_on_edit():
    wb = _wb("S1")
    s = wb.sheets[0]
    s.set("A1", "1")
    s.set("B1", "=A1*2")
    s.set("C1", "=B1+A1")
    assert (s.get("A1"), s.get("B1"), s.get("C1")) == (1, 2.0, 3.0)
    s.set("A1", "10")
    assert (s.get("B1"), s.get("C1")) == (20.0, 30.0)


def test_edited_cell_own_cache_cleared():
    wb = _wb("S1")
    s = wb.sheets[0]
    s.set("A1", "5")
    assert s.get("A1") == 5
    s.set("A1", "9")
    assert s.get("A1") == 9  # the edited cell's own memo must be dropped


def test_unrelated_cell_survives_but_stays_correct():
    wb = _wb("S1")
    s = wb.sheets[0]
    s.set("A1", "1")
    s.set("Z9", "=A1+1")
    s.set("M5", "42")
    assert s.get("M5") == 42
    s.set("A1", "100")
    assert s.get("Z9") == 101.0
    assert s.get("M5") == 42  # untouched, still right


# --- cross-sheet ----------------------------------------------------------

def test_cross_sheet_single_cell_dependent():
    wb = _wb("S1", "Data")
    s, d = wb.get_sheet("S1"), wb.get_sheet("Data")
    d.set("A1", "5")
    s.set("A1", "=Data!A1+1")
    assert s.get("A1") == 6.0
    d.set("A1", "50")
    assert s.get("A1") == 51.0  # cross-sheet reverse edge fired


def test_cross_sheet_range_dependent():
    wb = _wb("S1", "Data")
    s, d = wb.get_sheet("S1"), wb.get_sheet("Data")
    d.set("A1", "1")
    d.set("A2", "2")
    s.set("A1", "=SUM(Data!A1:A3)")
    assert s.get("A1") == 3.0
    d.set("A3", "10")
    assert s.get("A1") == 13.0


# --- ranges ---------------------------------------------------------------

def test_range_membership_invalidates():
    wb = _wb("S1")
    s = wb.sheets[0]
    for r in range(5):
        s.set(f"A{r + 1}", str(r + 1))
    s.set("C1", "=SUM(A1:A100)")
    assert s.get("C1") == 15.0
    s.set("A3", "30")  # inside A1:A100
    assert s.get("C1") == 42.0  # 1+2+30+4+5


@incremental_only
def test_large_range_stored_as_one_rect():
    wb = _wb("S1")
    s = wb.sheets[0]
    s.set("C1", "=SUM(A1:A100000)")
    s.set("A1", "1")  # force the index to build
    dg = wb._dep_graph
    assert dg.is_built
    # The 100k-cell range is a single rectangle, not 100k reverse edges.
    entries = dg.range_rdeps.get("S1", [])
    assert sum(1 for t in entries if t[4] == ("S1", 0, 2)) == 1


# --- always-dirty (volatile / dynamic) ------------------------------------

def test_indirect_chain_transitive():
    # F reads E via INDIRECT (dynamic); G depends on F statically. Editing E
    # must recompute F (always-dirty seed) AND G (its dependent).
    wb = _wb("S1")
    s = wb.sheets[0]
    s.set("E1", "3")
    s.set("F1", "=INDIRECT(\"E1\")")
    s.set("G1", "=F1*10")
    assert (s.get("F1"), s.get("G1")) == (3, 30.0)
    s.set("E1", "7")
    assert (s.get("F1"), s.get("G1")) == (7, 70.0)
    if depgraph.ABAX_INCREMENTAL:
        assert ("S1", 0, 5) in wb._dep_graph.always_dirty  # F1


def test_offset_is_always_dirty():
    an = analyze("=OFFSET(A1,1,0)", "S1", ["S1"])
    assert an.always_dirty is True and an.ok is True


def test_volatile_funcs_are_always_dirty():
    for fn in ("NOW", "TODAY", "RAND", "RANDBETWEEN"):
        an = analyze(f"={fn}()", "S1", ["S1"])
        assert an.always_dirty is True, fn


def test_unknown_macro_is_always_dirty():
    # A function name not in any registry (a user macro here) must be treated
    # conservatively as always-dirty so a hidden volatile can't serve stale.
    an = analyze("=MYMACRO(A1)", "S1", ["S1"])
    assert an.always_dirty is True


def test_plain_refs_not_dirty():
    an = analyze("=A1+B2*SUM(C1:C9)", "S1", ["S1"])
    assert an.always_dirty is False
    assert ("S1", 0, 0) in an.cells and ("S1", 1, 1) in an.cells
    assert ("S1", 0, 2, 8, 2) in an.rects


def test_registry_drift_guard():
    # The static always-dirty names must actually be registered functions, and
    # the "known pure" set must exclude every one of them.
    from abax.core.functions import CONTEXT_FUNCTIONS, FUNCTIONS
    registered = set(FUNCTIONS) | set(CONTEXT_FUNCTIONS)
    for name in ALWAYS_DIRTY_FUNCS:
        assert name in registered, f"{name} not registered — stale always-dirty set"
    pure = depgraph._known_pure_funcs()
    assert not (pure & ALWAYS_DIRTY_FUNCS)


# --- defined names --------------------------------------------------------

def test_name_reference_is_always_dirty_and_updates():
    wb = _wb("S1")
    s = wb.sheets[0]
    wb.names.define("NM", "S1!A1")
    s.set("A1", "5")
    s.set("B1", "=NM+1")
    assert s.get("B1") == 6.0
    # Redefining the name changes B1's value; B1 is always-dirty so it recomputes.
    wb.names.define("NM", "S1!A2")
    s.set("A2", "40")
    assert s.get("B1") == 41.0


# --- spill fall-back (Phase A) --------------------------------------------

def test_spill_reader_updates_on_anchor_edit():
    wb = _wb("S1")
    s = wb.sheets[0]
    s.set("A1", "=SEQUENCE(3)")          # spills 1,2,3 into A1:A3
    s.set("B1", "=A2+100")               # reads spilled A2 == 2
    assert s.get("B1") == 102.0
    s.set("A1", "=SEQUENCE(3,1,10)")     # now 10,11,12 -> A2 == 11
    assert s.get("B1") == 111.0


def test_spill_vacate_reader_reverts():
    wb = _wb("S1")
    s = wb.sheets[0]
    s.set("A1", "=SEQUENCE(3)")
    s.set("B1", "=A2+100")
    assert s.get("B1") == 102.0
    s.set("A1", "5")                     # spill vacates; A2 back to empty
    assert s.get("B1") == 100.0


# --- structural ops rebuild the index -------------------------------------

def test_insert_rows_keeps_dependents_correct():
    wb = _wb("S1")
    s = wb.sheets[0]
    s.set("A1", "1")
    s.set("A2", "=A1+1")
    assert s.get("A2") == 2.0
    s.insert_rows(0, 1)  # shift down: A1->A2 (=1), A2->A3 (=A2+1 after adjust)
    assert s.get("A3") == 2.0
    s.set("A2", "5")     # index was reset by the shift; rebuilds on this edit
    assert s.get("A3") == 6.0  # dependent still tracked across the shift


# --- rollback flag --------------------------------------------------------

def test_flag_off_still_correct(monkeypatch):
    monkeypatch.setattr(depgraph, "ABAX_INCREMENTAL", False)
    wb = _wb("S1")
    s = wb.sheets[0]
    s.set("A1", "1")
    s.set("B1", "=A1*3")
    assert s.get("B1") == 3.0
    s.set("A1", "4")
    assert s.get("B1") == 12.0  # blanket-clear path still correct


# --- DepGraph unit-level --------------------------------------------------

def test_reedit_removes_stale_edges():
    dg = DepGraph()
    wb = _wb("S1")
    dg.build(wb.sheets)
    # B1 depends on A1
    dg.on_cell_changed(wb.sheets, "S1", 0, 1, "=A1")
    assert ("S1", 0, 1) in dg.closure({("S1", 0, 0)})
    # Re-edit B1 to depend on C1 instead — the A1 edge must be gone.
    dg.on_cell_changed(wb.sheets, "S1", 0, 1, "=C1")
    assert ("S1", 0, 1) not in dg.closure({("S1", 0, 0)})
    assert ("S1", 0, 1) in dg.closure({("S1", 0, 2)})
