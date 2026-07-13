"""Budget roll-up, Earned Value Management (EVM-lite), and PM scenario engine.

Pure stdlib.  Operates on :class:`~abax.core.pm.taskmodel.Task` and
:class:`~abax.core.pm.projects.Project` objects to produce financial analyses
for project management.

**Honest caveat**: this is *planning math*, not accounting.  Planned Value
uses due dates as the plan baseline; Actual Cost is approximated from
``percent_done * cost`` since the data model does not track actual spend
separately from planned cost.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from abax.core.pm.projects import Project
from abax.core.pm.schedule import compute_cpm
from abax.core.pm.taskmodel import Task, write_task

__all__ = [
    "budget_rollup",
    "burn_by_completion",
    "burn_by_elapsed",
    "evm",
    "PmScenario",
    "apply_scenario",
    "apply_scenario_to_sheet",
    "scenario_delta",
]


# ---------------------------------------------------------------------------
# Business-day arithmetic (local copy — avoids reaching into private helpers)
# ---------------------------------------------------------------------------

def _business_days_between(a: date, b: date) -> int:
    """Count business days from *a* to *b* (inclusive of *a*, exclusive of *b*)."""
    if b <= a:
        return 0
    count = 0
    cur = a
    while cur < b:
        if cur.weekday() < 5:
            count += 1
        cur += timedelta(days=1)
    return count


# ---------------------------------------------------------------------------
# Budget roll-up
# ---------------------------------------------------------------------------

def budget_rollup(
    projects: list[tuple[Project, list[Task]]],
) -> dict[str, Any]:
    """Aggregate budget vs. actual cost across multiple projects.

    Returns a dict with:
    - ``total_budget``: sum of ``project.budget_total`` across projects
    - ``total_cost``: sum of all task costs (``task.cost``, skipping None)
    - ``remaining``: ``total_budget - total_cost``
    - ``per_project``: list of per-project dicts with
      ``{name, budget, cost, remaining, pct_used}``
    """
    total_budget = 0.0
    total_cost = 0.0
    per_project: list[dict[str, Any]] = []

    for proj, tasks in projects:
        budget = proj.budget_total
        cost = sum(t.cost for t in tasks if t.cost is not None)
        remaining = budget - cost
        pct_used = (cost / budget * 100.0) if budget else 0.0
        total_budget += budget
        total_cost += cost
        per_project.append({
            "name": proj.name,
            "budget": budget,
            "cost": cost,
            "remaining": remaining,
            "pct_used": pct_used,
        })

    return {
        "total_budget": total_budget,
        "total_cost": total_cost,
        "remaining": total_budget - total_cost,
        "per_project": per_project,
    }


# ---------------------------------------------------------------------------
# Burn tracking
# ---------------------------------------------------------------------------

def burn_by_completion(tasks: list[Task]) -> float:
    """Burn-to-date by percent complete: ``sum(cost * pct_done / 100)``."""
    return sum(
        t.cost * t.percent_done / 100.0
        for t in tasks
        if t.cost is not None
    )


def burn_by_elapsed(tasks: list[Task], today: date) -> float:
    """Burn-to-date by elapsed time fraction.

    For each task with ``start``, ``due``, and ``cost``, compute::

        elapsed_fraction = business_days(start, min(today, due))
                         / business_days(start, due)

    and multiply by ``cost``.  Tasks missing any of those three fields are
    skipped.
    """
    total = 0.0
    for t in tasks:
        if t.start is None or t.due is None or t.cost is None:
            continue
        total_days = _business_days_between(t.start, t.due)
        if total_days == 0:
            # Zero-duration task: fully burned if today >= due.
            if today >= t.due:
                total += t.cost
            continue
        cutoff = min(today, t.due)
        elapsed = _business_days_between(t.start, cutoff)
        total += t.cost * elapsed / total_days
    return total


# ---------------------------------------------------------------------------
# EVM-lite  (Earned Value Management)
# ---------------------------------------------------------------------------

def evm(
    tasks: list[Task],
    today: date,
    budget: float | None = None,
) -> dict[str, Any]:
    """Compute lightweight Earned Value metrics.

    Returns a dict with:

    - ``PV`` (Planned Value): sum of ``cost`` for tasks whose ``due <= today``.
    - ``EV`` (Earned Value): sum of ``cost * percent_done / 100`` for all
      tasks with cost.
    - ``AC`` (Actual Cost): same as :func:`burn_by_completion` — the best
      available proxy when actual spend is not tracked separately.
    - ``SPI``: ``EV / PV`` (schedule performance index); ``None`` if PV == 0.
    - ``CPI``: ``EV / AC`` (cost performance index); ``None`` if AC == 0.
    - ``EAC``: ``budget / CPI`` if both *budget* and CPI are available;
      else ``None``.
    """
    pv = sum(
        t.cost for t in tasks
        if t.cost is not None and t.due is not None and t.due <= today
    )
    ev = sum(
        t.cost * t.percent_done / 100.0
        for t in tasks
        if t.cost is not None
    )
    ac = burn_by_completion(tasks)

    spi = ev / pv if pv != 0 else None
    cpi = ev / ac if ac != 0 else None
    eac = (budget / cpi) if (budget is not None and cpi is not None and cpi != 0) else None

    return {
        "PV": pv,
        "EV": ev,
        "AC": ac,
        "SPI": spi,
        "CPI": cpi,
        "EAC": eac,
    }


# ---------------------------------------------------------------------------
# PM Scenario engine
# ---------------------------------------------------------------------------

@dataclass
class PmScenario:
    """A named set of task-field overrides for what-if analysis.

    ``overrides`` maps ``task_id -> {field_name: new_value}``.
    """

    name: str
    overrides: dict[str, dict[str, Any]]


_DATE_FIELDS = frozenset({"start", "due"})
_ALLOWED_OVERRIDE_FIELDS = frozenset({
    "start", "due", "effort", "cost", "assignee", "status", "percent_done",
})


def _parse_date_value(value: Any) -> date:
    """Convert a value to a :class:`date`, accepting ISO strings."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def apply_scenario(
    tasks: list[Task],
    scenario: PmScenario,
) -> list[Task]:
    """Return a NEW list of Task copies with *scenario*'s overrides applied.

    Originals are never mutated.  Date-typed override values accept ISO
    strings (``"2025-03-15"``) and are converted to :class:`date` objects.
    """
    result: list[Task] = []
    for t in tasks:
        new_t = copy.deepcopy(t)
        overrides = scenario.overrides.get(t.id)
        if overrides:
            for field_name, value in overrides.items():
                if field_name not in _ALLOWED_OVERRIDE_FIELDS:
                    continue
                if field_name in _DATE_FIELDS and value is not None:
                    value = _parse_date_value(value)
                setattr(new_t, field_name, value)
        result.append(new_t)
    return result


def apply_scenario_to_sheet(
    tasks: list[Task],
    scenario: PmScenario,
    *,
    col_map: dict[str, int],
    first_col: int = 0,
    sheet: Any = None,
    on_set: Any = None,
) -> list[tuple[Task, str, Any, Any]]:
    """Apply scenario overrides to the sheet via write_task, returning a change log.

    Returns ``[(task, field_name, old_value, new_value), ...]``.  Uses
    :func:`~abax.core.pm.taskmodel.write_task` so each cell edit flows through
    *on_set*.  Also updates the Task object so the in-memory model stays in sync.
    """
    by_id = {t.id: t for t in tasks}
    changes: list[tuple[Task, str, Any, Any]] = []

    for task_id, field_overrides in scenario.overrides.items():
        task = by_id.get(task_id)
        if task is None:
            continue

        for field_name, new_val in field_overrides.items():
            if field_name not in _ALLOWED_OVERRIDE_FIELDS:
                continue
            if field_name not in col_map:
                continue

            old_val = getattr(task, field_name, None)
            if field_name in _DATE_FIELDS and new_val is not None:
                new_val = _parse_date_value(new_val)

            write_task(
                sheet, task, field_name, new_val,
                col_map=col_map, first_col=first_col, on_set=on_set,
            )
            setattr(task, field_name, new_val)
            changes.append((task, field_name, old_val, new_val))

    return changes


def scenario_delta(
    projects: list[tuple[Project, list[Task]]],
    scenario: PmScenario,
    today: date,
    hours_per_day: float = 8.0,
) -> dict[str, Any]:
    """Compare before/after a scenario across projects.

    For each project: runs :func:`compute_cpm` before and after scenario
    application to compare finish dates, and :func:`budget_rollup` before and
    after to compare costs.

    Returns::

        {
            "projects": [
                {
                    "name": str,
                    "old_finish": date | None,
                    "new_finish": date | None,
                    "finish_delta_days": int | None,
                    "old_cost": float,
                    "new_cost": float,
                    "cost_delta": float,
                },
                ...
            ]
        }
    """
    old_rollup = budget_rollup(projects)
    new_projects: list[tuple[Project, list[Task]]] = []
    for proj, tasks in projects:
        new_tasks = apply_scenario(tasks, scenario)
        new_projects.append((proj, new_tasks))
    new_rollup = budget_rollup(new_projects)

    results: list[dict[str, Any]] = []
    for i, (proj, tasks) in enumerate(projects):
        new_tasks = new_projects[i][1]

        # Finish dates from CPM.
        old_finish: date | None = None
        new_finish: date | None = None
        try:
            old_cpm = compute_cpm(tasks, hours_per_day=hours_per_day)
            if old_cpm:
                old_finish = max(r.early_finish for r in old_cpm.values())
        except (ValueError, Exception):
            pass
        try:
            new_cpm = compute_cpm(new_tasks, hours_per_day=hours_per_day)
            if new_cpm:
                new_finish = max(r.early_finish for r in new_cpm.values())
        except (ValueError, Exception):
            pass

        if old_finish is not None and new_finish is not None:
            finish_delta_days = (new_finish - old_finish).days
        else:
            finish_delta_days = None

        old_cost = old_rollup["per_project"][i]["cost"]
        new_cost = new_rollup["per_project"][i]["cost"]

        results.append({
            "name": proj.name,
            "old_finish": old_finish,
            "new_finish": new_finish,
            "finish_delta_days": finish_delta_days,
            "old_cost": old_cost,
            "new_cost": new_cost,
            "cost_delta": new_cost - old_cost,
        })

    return {"projects": results}
