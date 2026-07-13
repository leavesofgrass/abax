"""Tests for PM scenario undo integration.

Covers:
- apply_scenario_to_sheet with mock sheet/on_set
- apply_scenario_to_sheet edge cases (no overrides, missing tasks, disallowed fields)
- Date serialisation through _SERIALIZERS
- PmScenarioDialog should_apply / result_scenario
- Integration with real Sheet + Document undo
"""

from __future__ import annotations

import datetime
import os

import pytest

from abax.core.pm.finance import PmScenario, apply_scenario, apply_scenario_to_sheet
from abax.core.pm.taskmodel import Task, _date_to_iso, write_task

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeSheet:
    """Minimal sheet stub recording set_cell calls."""

    def __init__(self):
        self.cells: dict[tuple[int, int], str] = {}

    def set_cell(self, row: int, col: int, value: str) -> None:
        self.cells[(row, col)] = value

    def get_raw(self, row: int, col: int) -> str:
        return self.cells.get((row, col), "")


def _make_tasks() -> list[Task]:
    return [
        Task(id="t1", row=0, name="Design", cost=100.0, revenue=500.0, status="open"),
        Task(id="t2", row=1, name="Build", cost=200.0, revenue=1000.0, status="open"),
        Task(id="t3", row=2, name="Test", cost=50.0, revenue=200.0, status="open"),
    ]


def _col_map() -> dict[str, int]:
    return {"name": 0, "cost": 1, "revenue": 2, "status": 3, "start": 4, "end": 5}


# ---------------------------------------------------------------------------
# apply_scenario_to_sheet — basic
# ---------------------------------------------------------------------------


class TestApplyScenarioToSheet:
    def test_on_set_called_for_each_override(self):
        tasks = _make_tasks()
        scenario = PmScenario(
            name="High cost",
            overrides={"t1": {"cost": 999.0}, "t2": {"cost": 888.0, "revenue": 2000.0}},
        )
        calls = []

        def on_set(sh, row, col, val):
            calls.append((row, col, val))

        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=FakeSheet(), on_set=on_set,
        )
        # t1: cost; t2: cost + revenue -> 3 calls
        assert len(calls) == 3
        assert len(changes) == 3

    def test_change_log_content(self):
        tasks = _make_tasks()
        scenario = PmScenario(
            name="X", overrides={"t1": {"cost": 999.0}},
        )
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=FakeSheet(), on_set=lambda *a: None,
        )
        assert len(changes) == 1
        task, fname, old, new = changes[0]
        assert task.id == "t1"
        assert fname == "cost"
        assert old == 100.0
        assert new == 999.0

    def test_task_object_mutated_in_place(self):
        tasks = _make_tasks()
        scenario = PmScenario(
            name="X", overrides={"t1": {"cost": 999.0}},
        )
        apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=FakeSheet(), on_set=lambda *a: None,
        )
        assert tasks[0].cost == 999.0

    def test_sheet_cells_written_via_on_set(self):
        tasks = _make_tasks()
        scenario = PmScenario(
            name="X", overrides={"t2": {"status": "done"}},
        )
        sheet = FakeSheet()

        def on_set(sh, row, col, val):
            sh.set_cell(row, col, val)

        apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet, on_set=on_set,
        )
        # t2 is row 1, status is col 3
        assert sheet.cells[(1, 3)] == "done"

    def test_first_col_offset(self):
        tasks = _make_tasks()
        scenario = PmScenario(
            name="X", overrides={"t1": {"cost": 42.0}},
        )
        calls = []

        def on_set(sh, row, col, val):
            calls.append((row, col, val))

        apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), first_col=5, sheet=FakeSheet(), on_set=on_set,
        )
        # cost is col_map["cost"]=1, +first_col=5 -> col=6
        assert calls[0][1] == 6


# ---------------------------------------------------------------------------
# apply_scenario_to_sheet — edge cases
# ---------------------------------------------------------------------------


class TestApplyScenarioEdgeCases:
    def test_no_overrides_empty_log(self):
        tasks = _make_tasks()
        scenario = PmScenario(name="Empty", overrides={})
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=FakeSheet(), on_set=lambda *a: None,
        )
        assert changes == []

    def test_no_on_set_calls_when_empty(self):
        tasks = _make_tasks()
        scenario = PmScenario(name="Empty", overrides={})
        calls = []

        def on_set(sh, row, col, val):
            calls.append(1)

        apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=FakeSheet(), on_set=on_set,
        )
        assert calls == []

    def test_missing_task_id_skipped(self):
        tasks = _make_tasks()
        scenario = PmScenario(
            name="X", overrides={"nonexistent": {"cost": 1.0}},
        )
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=FakeSheet(), on_set=lambda *a: None,
        )
        assert changes == []

    def test_disallowed_field_filtered(self):
        tasks = _make_tasks()
        # "id" and "row" are not in ALLOWED_FIELDS
        scenario = PmScenario(
            name="X", overrides={"t1": {"id": "hacked", "row": 999}},
        )
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=FakeSheet(), on_set=lambda *a: None,
        )
        assert changes == []
        # originals untouched
        assert tasks[0].id == "t1"
        assert tasks[0].row == 0

    def test_field_not_in_col_map_skipped(self):
        """A field in ALLOWED_FIELDS but absent from col_map -> write_task is a no-op."""
        tasks = _make_tasks()
        scenario = PmScenario(
            name="X", overrides={"t1": {"notes": "hello"}},
        )
        calls = []

        def on_set(sh, row, col, val):
            calls.append(1)

        # col_map has no "notes"
        apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=FakeSheet(), on_set=on_set,
        )
        # write_task silently skips when field not in col_map, but the in-memory
        # Task is still updated
        assert tasks[0].notes == "hello"

    def test_multiple_tasks_partial_overrides(self):
        tasks = _make_tasks()
        scenario = PmScenario(
            name="X",
            overrides={
                "t1": {"cost": 1.0},
                "t3": {"revenue": 9.0, "status": "pass"},
            },
        )
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=FakeSheet(), on_set=lambda *a: None,
        )
        assert len(changes) == 3  # t1:cost + t3:revenue + t3:status


# ---------------------------------------------------------------------------
# Date serialisation
# ---------------------------------------------------------------------------


class TestDateOverrides:
    def test_date_to_iso_from_date(self):
        d = datetime.date(2026, 7, 1)
        assert _date_to_iso(d) == "2026-07-01"

    def test_date_to_iso_from_datetime(self):
        dt = datetime.datetime(2026, 7, 1, 14, 30)
        assert _date_to_iso(dt) == "2026-07-01"

    def test_date_to_iso_passthrough_string(self):
        assert _date_to_iso("2026-07-01") == "2026-07-01"

    def test_date_override_written_as_iso(self):
        tasks = [Task(id="t1", row=0, start=datetime.date(2026, 1, 1))]
        scenario = PmScenario(
            name="X", overrides={"t1": {"start": datetime.date(2026, 12, 25)}},
        )
        calls = []

        def on_set(sh, row, col, val):
            calls.append(val)

        apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=FakeSheet(), on_set=on_set,
        )
        assert calls[0] == "2026-12-25"


# ---------------------------------------------------------------------------
# write_task unit tests
# ---------------------------------------------------------------------------


class TestWriteTask:
    def test_write_task_with_on_set(self):
        task = Task(id="t1", row=3, cost=100.0)
        calls = []

        def on_set(sh, row, col, val):
            calls.append((row, col, val))

        write_task("sheet", task, "cost", 42.0, col_map={"cost": 1}, on_set=on_set)
        assert calls == [(3, 1, "42.0")]

    def test_write_task_without_on_set(self):
        task = Task(id="t1", row=0, name="X")
        sheet = FakeSheet()
        write_task(sheet, task, "name", "Y", col_map={"name": 0})
        assert sheet.cells[(0, 0)] == "Y"

    def test_write_task_field_not_in_col_map(self):
        task = Task(id="t1", row=0)
        calls = []

        def on_set(sh, row, col, val):
            calls.append(1)

        write_task("sheet", task, "notes", "x", col_map={"cost": 0}, on_set=on_set)
        assert calls == []


# ---------------------------------------------------------------------------
# apply_scenario (pure, non-sheet)
# ---------------------------------------------------------------------------


class TestApplyScenarioPure:
    def test_returns_new_copies(self):
        tasks = _make_tasks()
        scenario = PmScenario(name="X", overrides={"t1": {"cost": 999.0}})
        result = apply_scenario(tasks, scenario)
        assert result[0].cost == 999.0
        # original untouched
        assert tasks[0].cost == 100.0
        assert result[0] is not tasks[0]

    def test_no_overrides_returns_copies(self):
        tasks = _make_tasks()
        scenario = PmScenario(name="Empty")
        result = apply_scenario(tasks, scenario)
        assert len(result) == len(tasks)
        assert all(r is not t for r, t in zip(result, tasks))


# ---------------------------------------------------------------------------
# PmScenario dataclass
# ---------------------------------------------------------------------------


class TestPmScenario:
    def test_to_dict_from_dict_roundtrip(self):
        sc = PmScenario(name="A", overrides={"t1": {"cost": 50}})
        d = sc.to_dict()
        restored = PmScenario.from_dict(d)
        assert restored.name == "A"
        assert restored.overrides == {"t1": {"cost": 50}}

    def test_from_dict_empty(self):
        sc = PmScenario.from_dict({})
        assert sc.name == ""
        assert sc.overrides == {}


# ---------------------------------------------------------------------------
# Dialog: should_apply / result_scenario
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PySide6")
    from abax.gui._qtcompat import QApplication

    return QApplication.instance() or QApplication([])


class TestPmScenarioDialog:
    def test_should_apply_false_by_default(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        dlg = PmScenarioDialog(scenarios=[PmScenario(name="A")])
        assert dlg.should_apply() is False
        dlg.deleteLater()

    def test_result_scenario_none_by_default(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        dlg = PmScenarioDialog(scenarios=[PmScenario(name="A")])
        assert dlg.result_scenario() is None
        dlg.deleteLater()

    def test_apply_sets_flag(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        sc = PmScenario(name="B", overrides={"t1": {"cost": 1}})
        dlg = PmScenarioDialog(scenarios=[sc])
        dlg._on_apply()
        assert dlg.should_apply() is True
        assert dlg.result_scenario() is sc
        dlg.deleteLater()

    def test_result_scenario_none_after_ok(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        dlg = PmScenarioDialog(scenarios=[PmScenario(name="A")])
        dlg.accept()  # OK without apply
        assert dlg.should_apply() is False
        assert dlg.result_scenario() is None
        dlg.deleteLater()

    def test_empty_scenario_list(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        dlg = PmScenarioDialog(scenarios=[])
        dlg._on_apply()
        assert dlg.should_apply() is True
        assert dlg.result_scenario() is None  # no scenario to pick
        dlg.deleteLater()


# ---------------------------------------------------------------------------
# Integration: real Sheet + Document undo
# ---------------------------------------------------------------------------


class TestUndoIntegration:
    def test_apply_and_undo_restores_values(self):
        """Apply a scenario to a real Sheet through Document.checkpoint, then
        undo and verify the original cell values are restored."""
        from abax.engine.document import Document

        doc = Document()
        sheet = doc.workbook.sheet

        # Set up cells: row 0 = task t1, col 0 = name, col 1 = cost
        sheet.set_cell(0, 0, "Design")
        sheet.set_cell(0, 1, "100")
        sheet.set_cell(1, 0, "Build")
        sheet.set_cell(1, 1, "200")

        tasks = [
            Task(id="t1", row=0, name="Design", cost=100.0),
            Task(id="t2", row=1, name="Build", cost=200.0),
        ]
        col_map = {"name": 0, "cost": 1}
        scenario = PmScenario(
            name="Expensive", overrides={"t1": {"cost": 999.0}, "t2": {"cost": 888.0}},
        )

        # Checkpoint ONCE before the batch
        doc.checkpoint("apply scenario")

        def on_set(sh, row, col, val):
            sh.set_cell(row, col, str(val))

        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=col_map, sheet=sheet, on_set=on_set,
        )
        doc.mark_dirty()

        assert len(changes) == 2
        assert sheet.get_raw(0, 1) == "999.0"
        assert sheet.get_raw(1, 1) == "888.0"

        # Undo restores original values (load_envelope replaces the sheets
        # list, so we must re-fetch the sheet reference).
        assert doc.undo()
        sheet = doc.workbook.sheet
        assert sheet.get_raw(0, 1) == "100"
        assert sheet.get_raw(1, 1) == "200"

    def test_redo_reapplies(self):
        """After undo, redo puts the scenario values back."""
        from abax.engine.document import Document

        doc = Document()
        sheet = doc.workbook.sheet
        sheet.set_cell(0, 0, "Task")
        sheet.set_cell(0, 1, "50")

        tasks = [Task(id="t1", row=0, name="Task", cost=50.0)]
        col_map = {"name": 0, "cost": 1}
        scenario = PmScenario(name="X", overrides={"t1": {"cost": 999.0}})

        doc.checkpoint("apply scenario")

        def on_set(sh, row, col, val):
            sh.set_cell(row, col, str(val))

        apply_scenario_to_sheet(
            tasks, scenario, col_map=col_map, sheet=sheet, on_set=on_set,
        )
        doc.mark_dirty()

        assert sheet.get_raw(0, 1) == "999.0"
        assert doc.undo()
        assert doc.workbook.sheet.get_raw(0, 1) == "50"
        assert doc.redo()
        assert doc.workbook.sheet.get_raw(0, 1) == "999.0"
