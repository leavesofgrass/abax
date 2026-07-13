"""Tests for PM scenario undo integration — apply_scenario_to_sheet."""

from __future__ import annotations

from datetime import date

from abax.core.pm.finance import PmScenario, apply_scenario_to_sheet
from abax.core.pm.taskmodel import Task


class FakeSheet:
    """Minimal sheet stub recording set_cell calls."""

    def __init__(self):
        self.cells: dict[tuple[int, int], str] = {}

    def set_cell(self, row: int, col: int, value: str) -> None:
        self.cells[(row, col)] = value


def _tasks() -> list[Task]:
    return [
        Task(row=1, id="T1", title="Design", status="To Do",
             start=date(2026, 1, 1), due=date(2026, 2, 1), cost=100.0),
        Task(row=2, id="T2", title="Build", status="In Progress",
             start=date(2026, 2, 1), due=date(2026, 3, 1), cost=200.0),
        Task(row=3, id="T3", title="Test", status="To Do",
             start=date(2026, 3, 1), due=date(2026, 4, 1), effort=40.0),
    ]


def _col_map() -> dict[str, int]:
    return {
        "title": 0, "status": 1, "start": 2, "due": 3,
        "assignee": 4, "cost": 5, "effort": 6, "percent_done": 7,
    }


class TestApplyScenarioToSheet:
    def test_basic_override(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="slip", overrides={
            "T1": {"status": "In Progress"},
        })
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        assert len(changes) == 1
        task, field, old, new = changes[0]
        assert task.id == "T1"
        assert field == "status"
        assert old == "To Do"
        assert new == "In Progress"

    def test_sheet_cells_written(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "T1": {"status": "Done"},
        })
        apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        assert (1, 1) in sheet.cells
        assert sheet.cells[(1, 1)] == "Done"

    def test_on_set_called(self):
        tasks = _tasks()
        sheet = FakeSheet()
        calls = []

        def on_set(s, r, c, v):
            calls.append((r, c, v))

        scenario = PmScenario(name="s", overrides={
            "T2": {"cost": 500.0},
        })
        apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet, on_set=on_set,
        )
        assert len(calls) == 1
        assert calls[0][0] == 2  # row
        assert calls[0][1] == 5  # col for cost

    def test_task_mutated_in_place(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "T1": {"status": "Done"},
        })
        apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        assert tasks[0].status == "Done"

    def test_multiple_fields_one_task(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "T1": {"status": "Done", "cost": 150.0},
        })
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        assert len(changes) == 2
        fields = {c[1] for c in changes}
        assert fields == {"status", "cost"}

    def test_multiple_tasks(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "T1": {"status": "Done"},
            "T3": {"effort": 80.0},
        })
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        assert len(changes) == 2

    def test_empty_scenario(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="empty", overrides={})
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        assert changes == []

    def test_missing_task_id_skipped(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "NONEXISTENT": {"status": "Done"},
        })
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        assert changes == []

    def test_disallowed_field_skipped(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "T1": {"title": "Changed Title"},
        })
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        assert changes == []

    def test_field_not_in_col_map_skipped(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "T1": {"status": "Done"},
        })
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map={"title": 0}, sheet=sheet,
        )
        assert changes == []

    def test_date_override_as_string(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "T1": {"due": "2026-06-01"},
        })
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        assert len(changes) == 1
        assert tasks[0].due == date(2026, 6, 1)
        assert sheet.cells[(1, 3)] == "2026-06-01"

    def test_date_override_as_date(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "T2": {"start": date(2026, 5, 1)},
        })
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        assert len(changes) == 1
        assert tasks[1].start == date(2026, 5, 1)

    def test_first_col_offset(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "T1": {"status": "Done"},
        })
        apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), first_col=3, sheet=sheet,
        )
        assert (1, 4) in sheet.cells  # col 1 + offset 3

    def test_change_log_records_old_and_new(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "T1": {"cost": 999.0},
        })
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        _, field, old, new = changes[0]
        assert field == "cost"
        assert old == 100.0
        assert new == 999.0

    def test_percent_done_override(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "T1": {"percent_done": 75.0},
        })
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        assert len(changes) == 1
        assert tasks[0].percent_done == 75.0

    def test_assignee_override(self):
        tasks = _tasks()
        sheet = FakeSheet()
        scenario = PmScenario(name="s", overrides={
            "T2": {"assignee": "Alice"},
        })
        changes = apply_scenario_to_sheet(
            tasks, scenario, col_map=_col_map(), sheet=sheet,
        )
        assert len(changes) == 1
        assert tasks[1].assignee == "Alice"
        assert sheet.cells[(2, 4)] == "Alice"
