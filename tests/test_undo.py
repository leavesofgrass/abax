"""Undo stack + Document-level undo/redo across edits and structural ops."""

from __future__ import annotations

from abax.core.undo import UndoStack
from abax.engine.document import Document

# --- the pure stack --------------------------------------------------------


def test_stack_checkpoint_undo_redo():
    st = UndoStack()
    assert not st.can_undo and not st.can_redo
    st.checkpoint("s0", "a1")    # state before mutation 1
    st.checkpoint("s1", "a2")    # state before mutation 2
    assert st.can_undo
    assert st.undo("s2") == ("s1", "a2")  # restore s1, save s2 for redo
    assert st.undo("s1") == ("s0", "a1")
    assert not st.can_undo and st.can_redo
    assert st.redo("s0") == ("s1", "a1")
    assert st.redo("s1") == ("s2", "a2")
    assert not st.can_redo


def test_checkpoint_clears_redo():
    st = UndoStack()
    st.checkpoint("a")
    st.undo("b")                 # redo now has "b"
    assert st.can_redo
    st.checkpoint("c")           # a new edit invalidates the redo trail
    assert not st.can_redo


def test_max_depth_drops_oldest():
    st = UndoStack(max_depth=2)
    st.checkpoint("a")
    st.checkpoint("b")
    st.checkpoint("c")           # "a" should be dropped
    assert st.undo("d")[0] == "c"
    assert st.undo("c")[0] == "b"
    assert not st.can_undo       # "a" was evicted


def test_coalescing_groups_rapid_same_key():
    st = UndoStack(coalesce_window=0.8)
    assert st.checkpoint("s0", "edit", coalesce_key="edit", now=0.0) is True
    # within the window + same key → coalesced (no new step)
    assert st.checkpoint("s1", "edit", coalesce_key="edit", now=0.3) is False
    assert st.checkpoint("s2", "edit", coalesce_key="edit", now=0.5) is False
    assert len(st.undo_labels()) == 1            # one grouped step
    # past the window → a new step
    assert st.checkpoint("s3", "edit", coalesce_key="edit", now=2.0) is True
    assert len(st.undo_labels()) == 2
    # different key never coalesces
    assert st.checkpoint("s4", "paste", coalesce_key="paste", now=2.1) is True
    assert len(st.undo_labels()) == 3


def test_history_labels():
    st = UndoStack()
    st.checkpoint("s0", "edit A1")
    st.checkpoint("s1", "paste")
    assert st.undo_labels() == ["edit A1", "paste"]
    st.undo("s2")
    assert st.undo_labels() == ["edit A1"]
    assert st.redo_labels() == ["paste"]


# --- Document integration --------------------------------------------------


def test_document_undo_redo_edits():
    d = Document()
    d.checkpoint(); d.workbook.sheet.set_cell(0, 0, "1")
    d.checkpoint(); d.workbook.sheet.set_cell(0, 0, "2")
    assert d.can_undo
    assert d.undo() and d.workbook.sheet.get_raw(0, 0) == "1"
    assert d.undo() and d.workbook.sheet.get_raw(0, 0) == ""
    assert not d.can_undo
    assert d.redo() and d.workbook.sheet.get_raw(0, 0) == "1"


def test_document_undo_structural_op():
    d = Document()
    d.workbook.sheet.set_cell(0, 0, "10")
    d.workbook.sheet.set_cell(1, 0, "=A1*2")
    d.checkpoint()
    d.workbook.sheet.insert_rows(0, 1)           # push everything down
    assert d.workbook.sheet.get_raw(1, 0) == "10"
    assert d.undo()                              # restores the pre-insert layout
    assert d.workbook.sheet.get_raw(0, 0) == "10"
    assert d.workbook.sheet.get_raw(1, 0) == "=A1*2"
    assert d.workbook.sheet.get("A2") == 20.0


def test_undo_preserves_workbook_identity():
    d = Document()
    wb = d.workbook
    d.checkpoint(); d.workbook.sheet.set_cell(0, 0, "x")
    d.undo()
    assert d.workbook is wb      # restore-in-place keeps the live reference valid


def test_undo_empty_returns_false():
    d = Document()
    assert d.undo() is False
    assert d.redo() is False


# --- undo/redo under the windowing policy -----------------------------------
# Restores rebuild the workbook from an envelope snapshot; a document opened
# under a windowing policy must land back on the bounded store, not silently
# rehydrate every cell into a plain dict.


def _saved_big_doc(tmp_path, n: int = 40):
    """A native .abax file whose single sheet has ``n`` literal cells."""
    from abax.core.workbook import Workbook

    wb = Workbook()
    wb.sheet.set_cells_bulk((r, 0, str(r)) for r in range(n))
    path = tmp_path / "big.abax"
    wb.save_json(path)
    return path


def test_undo_redo_keep_explicitly_windowed_store(tmp_path):
    """Explicit positive capacity: the store stays windowed (same capacity)
    across undo AND redo, with values correct both ways."""
    from abax.core.cellstore import WindowedCellStore

    path = _saved_big_doc(tmp_path, 40)
    d = Document.open(path, windowed_capacity=10)
    sh = d.workbook.sheet
    assert isinstance(sh._cells, WindowedCellStore)

    d.checkpoint("edit")
    d.workbook.sheet.set_cell(0, 0, "edited")
    try:
        assert d.undo()
        sh = d.workbook.sheet
        assert isinstance(sh._cells, WindowedCellStore)
        assert sh._cells.capacity == 10
        assert sh._cells.resident_count() <= 10       # bounded through the restore
        assert sh.get_raw(0, 0) == "0"
        assert [sh.get_value(r, 0) for r in range(40)] == list(range(40))

        assert d.redo()
        sh = d.workbook.sheet
        assert isinstance(sh._cells, WindowedCellStore)
        assert sh._cells.capacity == 10
        assert sh.get_raw(0, 0) == "edited"
        assert sh.get_value(39, 0) == 39
    finally:
        d.workbook.sheet._cells.close()


def test_undo_reapplies_auto_policy(tmp_path, monkeypatch):
    """Auto (setting 0): a sheet over the threshold restores onto the windowed
    store at the default capacity; a small sheet restores plain — exactly the
    open-time policy, re-applied."""
    import abax.core.workbook as wbmod
    from abax.core.cellstore import DictCellStore, WindowedCellStore

    monkeypatch.setattr(wbmod, "AUTO_WINDOW_THRESHOLD", 5)
    path = _saved_big_doc(tmp_path, 20)
    d = Document.open(path)                            # default 0 -> auto
    d.workbook.add_sheet("small").set_cell(0, 0, "1")  # stays under threshold
    assert isinstance(d.workbook.sheets[0]._cells, WindowedCellStore)

    d.checkpoint("edit")
    d.workbook.sheets[0].set_cell(0, 0, "edited")
    try:
        assert d.undo()
        big = d.workbook.sheets[0]
        assert isinstance(big._cells, WindowedCellStore)
        assert big._cells.capacity == WindowedCellStore.DEFAULT_CAPACITY
        assert big.get_raw(0, 0) == "0"
        small = d.workbook.get_sheet("small")
        assert type(small._cells) is DictCellStore     # auto leaves it plain
        assert small.get_raw(0, 0) == "1"
    finally:
        d.workbook.sheets[0]._cells.close()


def test_undo_without_policy_restores_plain(monkeypatch):
    """A direct ``Document()`` (no policy — tests, console snapshots) restores
    exactly as before: plain store even above the auto threshold."""
    import abax.core.workbook as wbmod
    from abax.core.cellstore import DictCellStore, WindowedCellStore

    monkeypatch.setattr(wbmod, "AUTO_WINDOW_THRESHOLD", 5)
    d = Document()
    assert d.windowed_capacity is None
    for r in range(20):                                # over the patched threshold
        d.workbook.sheet.set_cell(r, 0, str(r))
    d.checkpoint("edit")
    d.workbook.sheet.set_cell(0, 0, "edited")
    assert d.undo()
    sh = d.workbook.sheet
    assert type(sh._cells) is DictCellStore
    assert not isinstance(sh._cells, WindowedCellStore)
    assert sh.get_raw(0, 0) == "0"
    assert d.redo()
    assert type(d.workbook.sheet._cells) is DictCellStore
