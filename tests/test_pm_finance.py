"""Tests for abax.core.pm.finance — budget roll-up, EVM-lite, scenario engine."""

from __future__ import annotations

from datetime import date

import pytest

from abax.core.pm.finance import (
    PmScenario,
    apply_scenario,
    budget_rollup,
    burn_by_completion,
    burn_by_elapsed,
    evm,
    scenario_delta,
)
from abax.core.pm.projects import Project
from abax.core.pm.taskmodel import Task

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(
    row: int = 1,
    *,
    title: str = "task",
    cost: float | None = None,
    percent_done: float = 0.0,
    start: date | None = None,
    due: date | None = None,
    effort: float | None = None,
    status: str = "",
    assignee: str = "",
    depends: list[str] | None = None,
    id: str = "",
) -> Task:
    return Task(
        row=row,
        title=title,
        cost=cost,
        percent_done=percent_done,
        start=start,
        due=due,
        effort=effort,
        status=status,
        assignee=assignee,
        depends=depends or [],
        id=id or f"T{row}",
    )


def _project(name: str = "Alpha", budget: float = 0.0) -> Project:
    return Project(name=name, budget_total=budget)


# ===================================================================
# Budget roll-up
# ===================================================================


class TestBudgetRollup:
    def test_single_project(self):
        proj = _project("A", 1000.0)
        tasks = [_task(1, cost=200.0), _task(2, cost=300.0)]
        result = budget_rollup([(proj, tasks)])
        assert result["total_budget"] == 1000.0
        assert result["total_cost"] == 500.0
        assert result["remaining"] == 500.0
        pp = result["per_project"]
        assert len(pp) == 1
        assert pp[0]["name"] == "A"
        assert pp[0]["pct_used"] == pytest.approx(50.0)

    def test_multiple_projects(self):
        p1 = _project("A", 1000.0)
        p2 = _project("B", 2000.0)
        t1 = [_task(1, cost=100.0)]
        t2 = [_task(2, cost=500.0), _task(3, cost=250.0)]
        result = budget_rollup([(p1, t1), (p2, t2)])
        assert result["total_budget"] == 3000.0
        assert result["total_cost"] == 850.0
        assert result["remaining"] == 2150.0
        assert len(result["per_project"]) == 2

    def test_zero_budget(self):
        proj = _project("Z", 0.0)
        tasks = [_task(1, cost=100.0)]
        result = budget_rollup([(proj, tasks)])
        assert result["per_project"][0]["pct_used"] == 0.0

    def test_no_costs(self):
        proj = _project("N", 500.0)
        tasks = [_task(1), _task(2)]
        result = budget_rollup([(proj, tasks)])
        assert result["total_cost"] == 0.0
        assert result["remaining"] == 500.0

    def test_empty_projects(self):
        result = budget_rollup([])
        assert result["total_budget"] == 0.0
        assert result["total_cost"] == 0.0
        assert result["per_project"] == []

    def test_none_costs_skipped(self):
        proj = _project("M", 1000.0)
        tasks = [_task(1, cost=100.0), _task(2, cost=None), _task(3, cost=50.0)]
        result = budget_rollup([(proj, tasks)])
        assert result["total_cost"] == 150.0

    def test_over_budget(self):
        proj = _project("Over", 100.0)
        tasks = [_task(1, cost=200.0)]
        result = budget_rollup([(proj, tasks)])
        assert result["remaining"] == -100.0
        assert result["per_project"][0]["pct_used"] == pytest.approx(200.0)


# ===================================================================
# Burn tracking
# ===================================================================


class TestBurnByCompletion:
    def test_basic(self):
        tasks = [
            _task(1, cost=100.0, percent_done=50.0),
            _task(2, cost=200.0, percent_done=25.0),
        ]
        assert burn_by_completion(tasks) == pytest.approx(100.0)

    def test_no_cost(self):
        tasks = [_task(1, percent_done=50.0)]
        assert burn_by_completion(tasks) == 0.0

    def test_empty(self):
        assert burn_by_completion([]) == 0.0

    def test_zero_percent(self):
        tasks = [_task(1, cost=500.0, percent_done=0.0)]
        assert burn_by_completion(tasks) == 0.0

    def test_100_percent(self):
        tasks = [_task(1, cost=500.0, percent_done=100.0)]
        assert burn_by_completion(tasks) == pytest.approx(500.0)


class TestBurnByElapsed:
    def test_basic_midpoint(self):
        # Mon Jan 6 to Fri Jan 10 = 4 business days.
        # Today = Wed Jan 8 -> 2 business days elapsed -> fraction 2/4 = 0.5.
        tasks = [_task(1, cost=100.0, start=date(2025, 1, 6), due=date(2025, 1, 10))]
        result = burn_by_elapsed(tasks, date(2025, 1, 8))
        assert result == pytest.approx(50.0)

    def test_past_due(self):
        tasks = [_task(1, cost=100.0, start=date(2025, 1, 6), due=date(2025, 1, 10))]
        result = burn_by_elapsed(tasks, date(2025, 2, 1))
        # Capped at due date -> full cost.
        assert result == pytest.approx(100.0)

    def test_before_start(self):
        tasks = [_task(1, cost=100.0, start=date(2025, 1, 6), due=date(2025, 1, 10))]
        result = burn_by_elapsed(tasks, date(2025, 1, 3))
        assert result == pytest.approx(0.0)

    def test_missing_fields_skipped(self):
        tasks = [
            _task(1, cost=100.0, start=None, due=date(2025, 1, 10)),
            _task(2, cost=100.0, start=date(2025, 1, 6), due=None),
            _task(3, cost=None, start=date(2025, 1, 6), due=date(2025, 1, 10)),
        ]
        assert burn_by_elapsed(tasks, date(2025, 1, 8)) == 0.0

    def test_zero_duration_task_before_due(self):
        # Same start and due -> 0 business days.
        tasks = [_task(1, cost=50.0, start=date(2025, 1, 6), due=date(2025, 1, 6))]
        result = burn_by_elapsed(tasks, date(2025, 1, 5))
        assert result == 0.0

    def test_zero_duration_task_on_due(self):
        tasks = [_task(1, cost=50.0, start=date(2025, 1, 6), due=date(2025, 1, 6))]
        result = burn_by_elapsed(tasks, date(2025, 1, 6))
        assert result == pytest.approx(50.0)

    def test_empty(self):
        assert burn_by_elapsed([], date(2025, 1, 8)) == 0.0


# ===================================================================
# EVM-lite
# ===================================================================


class TestEvm:
    def test_basic(self):
        today = date(2025, 1, 15)
        tasks = [
            _task(1, cost=100.0, due=date(2025, 1, 10), percent_done=100.0),
            _task(2, cost=200.0, due=date(2025, 1, 20), percent_done=50.0),
        ]
        result = evm(tasks, today, budget=500.0)
        assert result["PV"] == pytest.approx(100.0)  # only task 1 due <= today
        assert result["EV"] == pytest.approx(200.0)   # 100 + 100
        assert result["AC"] == pytest.approx(200.0)
        assert result["SPI"] == pytest.approx(2.0)
        assert result["CPI"] == pytest.approx(1.0)
        assert result["EAC"] == pytest.approx(500.0)

    def test_pv_zero(self):
        today = date(2025, 1, 1)
        tasks = [_task(1, cost=100.0, due=date(2025, 12, 31), percent_done=10.0)]
        result = evm(tasks, today)
        assert result["PV"] == 0.0
        assert result["SPI"] is None

    def test_ac_zero(self):
        today = date(2025, 1, 15)
        tasks = [_task(1, cost=100.0, due=date(2025, 1, 10), percent_done=0.0)]
        result = evm(tasks, today)
        assert result["AC"] == 0.0
        assert result["CPI"] is None
        assert result["EAC"] is None

    def test_no_budget(self):
        today = date(2025, 1, 15)
        tasks = [_task(1, cost=100.0, due=date(2025, 1, 10), percent_done=50.0)]
        result = evm(tasks, today, budget=None)
        assert result["EAC"] is None

    def test_no_tasks(self):
        result = evm([], date(2025, 1, 15))
        assert result["PV"] == 0.0
        assert result["EV"] == 0.0
        assert result["AC"] == 0.0
        assert result["SPI"] is None
        assert result["CPI"] is None

    def test_no_due_dates(self):
        tasks = [_task(1, cost=100.0, due=None, percent_done=50.0)]
        result = evm(tasks, date(2025, 1, 15))
        assert result["PV"] == 0.0
        assert result["EV"] == pytest.approx(50.0)

    def test_all_complete(self):
        today = date(2025, 6, 1)
        tasks = [
            _task(1, cost=100.0, due=date(2025, 1, 10), percent_done=100.0),
            _task(2, cost=200.0, due=date(2025, 3, 10), percent_done=100.0),
        ]
        result = evm(tasks, today, budget=300.0)
        assert result["PV"] == pytest.approx(300.0)
        assert result["EV"] == pytest.approx(300.0)
        assert result["SPI"] == pytest.approx(1.0)
        assert result["CPI"] == pytest.approx(1.0)
        assert result["EAC"] == pytest.approx(300.0)

    def test_no_costs(self):
        tasks = [_task(1, cost=None, due=date(2025, 1, 10), percent_done=50.0)]
        result = evm(tasks, date(2025, 1, 15))
        assert result["PV"] == 0.0
        assert result["EV"] == 0.0


# ===================================================================
# PmScenario / apply_scenario
# ===================================================================


class TestApplyScenario:
    def test_override_cost(self):
        tasks = [_task(1, cost=100.0, id="T1")]
        scenario = PmScenario("bump", {"T1": {"cost": 200.0}})
        result = apply_scenario(tasks, scenario)
        assert result[0].cost == 200.0
        assert tasks[0].cost == 100.0  # original unchanged

    def test_override_dates_as_strings(self):
        tasks = [_task(1, start=date(2025, 1, 1), due=date(2025, 2, 1), id="T1")]
        scenario = PmScenario("shift", {"T1": {
            "start": "2025-03-01",
            "due": "2025-04-01",
        }})
        result = apply_scenario(tasks, scenario)
        assert result[0].start == date(2025, 3, 1)
        assert result[0].due == date(2025, 4, 1)

    def test_override_dates_as_date_objects(self):
        tasks = [_task(1, id="T1")]
        scenario = PmScenario("shift", {"T1": {"start": date(2025, 6, 1)}})
        result = apply_scenario(tasks, scenario)
        assert result[0].start == date(2025, 6, 1)

    def test_override_assignee(self):
        tasks = [_task(1, assignee="Alice", id="T1")]
        scenario = PmScenario("reassign", {"T1": {"assignee": "Bob"}})
        result = apply_scenario(tasks, scenario)
        assert result[0].assignee == "Bob"

    def test_override_status(self):
        tasks = [_task(1, status="todo", id="T1")]
        scenario = PmScenario("done", {"T1": {"status": "done"}})
        result = apply_scenario(tasks, scenario)
        assert result[0].status == "done"

    def test_override_percent_done(self):
        tasks = [_task(1, percent_done=0.0, id="T1")]
        scenario = PmScenario("half", {"T1": {"percent_done": 50.0}})
        result = apply_scenario(tasks, scenario)
        assert result[0].percent_done == 50.0

    def test_override_effort(self):
        tasks = [_task(1, effort=8.0, id="T1")]
        scenario = PmScenario("more", {"T1": {"effort": 16.0}})
        result = apply_scenario(tasks, scenario)
        assert result[0].effort == 16.0

    def test_empty_scenario(self):
        tasks = [_task(1, cost=100.0, id="T1")]
        scenario = PmScenario("noop", {})
        result = apply_scenario(tasks, scenario)
        assert result[0].cost == 100.0

    def test_unknown_task_id_ignored(self):
        tasks = [_task(1, cost=100.0, id="T1")]
        scenario = PmScenario("miss", {"T99": {"cost": 999.0}})
        result = apply_scenario(tasks, scenario)
        assert result[0].cost == 100.0

    def test_unknown_field_ignored(self):
        tasks = [_task(1, id="T1")]
        scenario = PmScenario("bad", {"T1": {"nonexistent_field": 42}})
        result = apply_scenario(tasks, scenario)
        # Should not raise, field is silently skipped.
        assert result[0].title == "task"

    def test_deep_copy_isolation(self):
        tasks = [_task(1, id="T1")]
        tasks[0].extra["key"] = [1, 2, 3]
        scenario = PmScenario("noop", {})
        result = apply_scenario(tasks, scenario)
        result[0].extra["key"].append(4)
        assert tasks[0].extra["key"] == [1, 2, 3]

    def test_multiple_overrides(self):
        tasks = [
            _task(1, cost=100.0, id="T1"),
            _task(2, cost=200.0, id="T2"),
        ]
        scenario = PmScenario("both", {
            "T1": {"cost": 150.0},
            "T2": {"cost": 250.0, "percent_done": 75.0},
        })
        result = apply_scenario(tasks, scenario)
        assert result[0].cost == 150.0
        assert result[1].cost == 250.0
        assert result[1].percent_done == 75.0


# ===================================================================
# scenario_delta
# ===================================================================


class TestScenarioDelta:
    def test_cost_delta(self):
        proj = _project("A", 1000.0)
        tasks = [
            _task(1, cost=100.0, id="T1", start=date(2025, 1, 6), effort=8.0),
            _task(2, cost=200.0, id="T2", start=date(2025, 1, 7), effort=8.0),
        ]
        scenario = PmScenario("cheaper", {"T1": {"cost": 50.0}})
        result = scenario_delta([(proj, tasks)], scenario, date(2025, 1, 15))
        p = result["projects"][0]
        assert p["old_cost"] == 300.0
        assert p["new_cost"] == 250.0
        assert p["cost_delta"] == pytest.approx(-50.0)

    def test_finish_date_change(self):
        proj = _project("A", 1000.0)
        # Two sequential tasks.
        tasks = [
            _task(1, cost=100.0, id="T1", start=date(2025, 1, 6), effort=8.0),
            _task(2, cost=100.0, id="T2", start=date(2025, 1, 7), effort=8.0, depends=["T1"]),
        ]
        # Make T1 take longer.
        scenario = PmScenario("delay", {"T1": {"effort": 40.0}})
        result = scenario_delta([(proj, tasks)], scenario, date(2025, 1, 15))
        p = result["projects"][0]
        assert p["old_finish"] is not None
        assert p["new_finish"] is not None
        # New finish should be later.
        assert p["finish_delta_days"] is not None
        assert p["finish_delta_days"] > 0

    def test_empty_project(self):
        proj = _project("Empty", 0.0)
        scenario = PmScenario("noop", {})
        result = scenario_delta([(proj, [])], scenario, date(2025, 1, 15))
        p = result["projects"][0]
        assert p["old_finish"] is None
        assert p["new_finish"] is None
        assert p["finish_delta_days"] is None
        assert p["cost_delta"] == 0.0

    def test_multiple_projects(self):
        p1 = _project("A", 500.0)
        p2 = _project("B", 800.0)
        t1 = [_task(1, cost=100.0, id="T1", start=date(2025, 1, 6), effort=8.0)]
        t2 = [_task(2, cost=200.0, id="T2", start=date(2025, 1, 6), effort=8.0)]
        scenario = PmScenario("bump", {"T2": {"cost": 300.0}})
        result = scenario_delta([(p1, t1), (p2, t2)], scenario, date(2025, 1, 15))
        assert len(result["projects"]) == 2
        assert result["projects"][0]["cost_delta"] == 0.0
        assert result["projects"][1]["cost_delta"] == pytest.approx(100.0)

    def test_no_change_scenario(self):
        proj = _project("A", 1000.0)
        tasks = [_task(1, cost=100.0, id="T1", start=date(2025, 1, 6), effort=8.0)]
        scenario = PmScenario("noop", {})
        result = scenario_delta([(proj, tasks)], scenario, date(2025, 1, 15))
        p = result["projects"][0]
        assert p["cost_delta"] == 0.0
        assert p["finish_delta_days"] == 0


# ===================================================================
# Layering sanity — finance must not import engine or gui
# ===================================================================


class TestLayering:
    def test_no_engine_or_gui_imports(self):
        import abax.core.pm.finance as mod
        src = open(mod.__file__, encoding="utf-8").read()
        assert "abax.engine" not in src
        assert "abax.gui" not in src
