"""Tests for abax.core.pm.portfolio — portfolio analytics engine."""

from __future__ import annotations

from datetime import date

import pytest

from abax.core.pm.portfolio import (
    at_risk_tasks,
    milestone_schedule,
    overdue_tasks,
    portfolio_kpis,
    project_health,
    project_progress,
    resolve_cross_links,
    slip_impact,
    status_counts,
)
from abax.core.pm.projects import CrossProjectLink, Milestone, Project
from abax.core.pm.taskmodel import Task

# ── helpers ─────────────────────────────────────────────────────────

def _parse(s: str) -> date | None:
    return date.fromisoformat(s) if s else None


def _task(
    id: str = "",
    title: str = "",
    status: str = "",
    start: str = "",
    due: str = "",
    percent_done: int = 0,
    effort: float | None = None,
    depends: list[str] | None = None,
    row: int = 0,
    **kw,
) -> Task:
    """Shorthand for building a Task with sane defaults."""
    return Task(
        row=row,
        id=id,
        title=title,
        status=status,
        start=_parse(start),
        due=_parse(due),
        percent_done=percent_done,
        effort=effort,
        depends=depends or [],
        **kw,
    )


def _project(
    name: str = "proj",
    milestones: list[Milestone] | None = None,
    cross_links: list[CrossProjectLink] | None = None,
) -> Project:
    return Project(
        name=name,
        milestones=milestones or [],
        cross_links=cross_links or [],
    )


# ── project_progress ───────────────────────────────────────────────

class TestProjectProgress:
    def test_empty(self):
        assert project_progress([]) == 0.0

    def test_unweighted(self):
        tasks = [
            _task(percent_done=50),
            _task(percent_done=100),
        ]
        assert project_progress(tasks) == pytest.approx(75.0)

    def test_effort_weighted(self):
        tasks = [
            _task(percent_done=100, effort=10.0),  # 10h done
            _task(percent_done=0, effort=30.0),     # 30h not done
        ]
        # (100*10 + 0*30) / 40 = 25.0
        assert project_progress(tasks) == pytest.approx(25.0)

    def test_mixed_effort_falls_back_to_unweighted(self):
        """When some tasks lack effort, fall back to unweighted average."""
        tasks = [
            _task(percent_done=100, effort=10.0),
            _task(percent_done=0),  # effort is None
        ]
        # Unweighted: (100 + 0) / 2 = 50
        assert project_progress(tasks) == pytest.approx(50.0)

    def test_zero_effort(self):
        """All tasks have effort=0 — avoid division by zero."""
        tasks = [
            _task(percent_done=50, effort=0.0),
            _task(percent_done=80, effort=0.0),
        ]
        assert project_progress(tasks) == pytest.approx(0.0)

    def test_single_task(self):
        assert project_progress([_task(percent_done=42)]) == pytest.approx(42.0)


# ── status_counts ──────────────────────────────────────────────────

class TestStatusCounts:
    def test_basic(self):
        tasks = [
            _task(status="done"),
            _task(status="done"),
            _task(status="in progress"),
            _task(status="todo"),
        ]
        counts = status_counts(tasks)
        assert counts == {"done": 2, "in progress": 1, "todo": 1}

    def test_empty(self):
        assert status_counts([]) == {}

    def test_single_status(self):
        tasks = [_task(status="blocked"), _task(status="blocked")]
        assert status_counts(tasks) == {"blocked": 2}

    def test_case_preserved(self):
        tasks = [_task(status="Done"), _task(status="done")]
        counts = status_counts(tasks)
        assert counts == {"Done": 1, "done": 1}


# ── overdue_tasks ──────────────────────────────────────────────────

class TestOverdueTasks:
    def test_basic(self):
        today = date(2026, 7, 15)
        tasks = [
            _task(id="a", due="2026-07-10", status="in progress"),  # overdue
            _task(id="b", due="2026-07-20", status="in progress"),  # not yet
            _task(id="c", due="2026-07-10", status="done"),         # done
        ]
        result = overdue_tasks(tasks, today)
        assert len(result) == 1
        assert result[0].id == "a"

    def test_no_due_date(self):
        """Tasks without a due date are never overdue."""
        today = date(2026, 7, 15)
        tasks = [_task(id="x", status="in progress")]
        assert overdue_tasks(tasks, today) == []

    def test_due_today_not_overdue(self):
        """A task due exactly today is NOT overdue (due < today)."""
        today = date(2026, 7, 15)
        tasks = [_task(id="x", due="2026-07-15", status="todo")]
        assert overdue_tasks(tasks, today) == []

    def test_done_statuses(self):
        """Various done-like statuses should be excluded."""
        today = date(2026, 7, 15)
        for status in ("done", "Done", "COMPLETE", "completed", "Closed", "finished"):
            tasks = [_task(id="x", due="2026-07-01", status=status)]
            assert overdue_tasks(tasks, today) == [], f"status={status!r}"

    def test_all_overdue(self):
        today = date(2026, 7, 15)
        tasks = [
            _task(id="a", due="2026-07-01", status="todo"),
            _task(id="b", due="2026-07-14", status="in progress"),
        ]
        assert len(overdue_tasks(tasks, today)) == 2


# ── at_risk_tasks ──────────────────────────────────────────────────

class TestAtRiskTasks:
    def test_basic(self):
        today = date(2026, 7, 15)
        tasks = [
            # Due within 7 days, <80% done -> at risk
            _task(id="a", due="2026-07-18", status="in progress", percent_done=50),
            # Due within 7 days, >=80% done -> NOT at risk
            _task(id="b", due="2026-07-18", status="in progress", percent_done=80),
            # Due outside 7 days -> NOT at risk
            _task(id="c", due="2026-07-30", status="in progress", percent_done=10),
        ]
        result = at_risk_tasks(tasks, today)
        assert len(result) == 1
        assert result[0].id == "a"

    def test_exactly_on_boundary(self):
        """Due exactly on today: within [today, today+7), so at risk if <80%."""
        today = date(2026, 7, 15)
        tasks = [_task(id="x", due="2026-07-15", status="todo", percent_done=0)]
        assert len(at_risk_tasks(tasks, today)) == 1

    def test_due_at_window_boundary_excluded(self):
        """Due exactly at today + window_days: outside [today, today+7)."""
        today = date(2026, 7, 15)
        tasks = [_task(id="x", due="2026-07-22", status="todo", percent_done=0)]
        assert at_risk_tasks(tasks, today) == []

    def test_no_due_date(self):
        today = date(2026, 7, 15)
        tasks = [_task(id="x", status="todo", percent_done=0)]
        assert at_risk_tasks(tasks, today) == []

    def test_done_excluded(self):
        today = date(2026, 7, 15)
        tasks = [_task(id="x", due="2026-07-18", status="done", percent_done=10)]
        assert at_risk_tasks(tasks, today) == []

    def test_custom_window(self):
        today = date(2026, 7, 15)
        tasks = [_task(id="x", due="2026-07-25", status="todo", percent_done=0)]
        # Default 7 days: 07-25 is outside
        assert at_risk_tasks(tasks, today) == []
        # 14-day window: 07-25 is inside
        assert len(at_risk_tasks(tasks, today, window_days=14)) == 1


# ── milestone_schedule ─────────────────────────────────────────────

class TestMilestoneSchedule:
    def test_done_milestone(self):
        proj = _project(milestones=[
            Milestone(name="M1", date="2026-01-01", done=True),
        ])
        result = milestone_schedule(proj)
        assert len(result) == 1
        assert result[0]["done"] is True
        assert result[0]["overdue"] is False

    def test_overdue_milestone(self):
        proj = _project(milestones=[
            Milestone(name="M2", date="2020-01-01", done=False),
        ])
        result = milestone_schedule(proj)
        assert result[0]["overdue"] is True

    def test_future_milestone(self):
        proj = _project(milestones=[
            Milestone(name="M3", date="2099-12-31", done=False),
        ])
        result = milestone_schedule(proj)
        assert result[0]["overdue"] is False

    def test_no_date_milestone(self):
        proj = _project(milestones=[
            Milestone(name="M4", date="", done=False),
        ])
        result = milestone_schedule(proj)
        assert result[0]["overdue"] is False

    def test_multiple(self):
        proj = _project(milestones=[
            Milestone(name="A", date="2020-01-01", done=True),
            Milestone(name="B", date="2020-01-01", done=False),
            Milestone(name="C", date="2099-12-31", done=False),
        ])
        result = milestone_schedule(proj)
        assert len(result) == 3
        assert [r["name"] for r in result] == ["A", "B", "C"]
        assert result[0]["overdue"] is False   # done
        assert result[1]["overdue"] is True    # past & not done
        assert result[2]["overdue"] is False   # future


# ── project_health ─────────────────────────────────────────────────

class TestProjectHealth:
    def test_green(self):
        today = date(2026, 7, 15)
        tasks = [
            _task(due="2026-07-20", status="in progress"),
            _task(due="2026-07-20", status="in progress"),
        ]
        proj = _project()
        assert project_health(tasks, proj, today) == "green"

    def test_red_milestone_overdue(self):
        today = date(2026, 7, 15)
        tasks = [_task(due="2026-07-20", status="in progress")]
        proj = _project(milestones=[
            Milestone(name="M1", date="2026-07-01", done=False),
        ])
        assert project_health(tasks, proj, today) == "red"

    def test_red_high_overdue_fraction(self):
        """More than 25% overdue -> red."""
        today = date(2026, 7, 15)
        # 2/4 = 50% overdue -> red
        tasks = [
            _task(due="2026-07-01", status="todo"),
            _task(due="2026-07-01", status="todo"),
            _task(due="2026-07-20", status="in progress"),
            _task(due="2026-07-20", status="in progress"),
        ]
        proj = _project()
        assert project_health(tasks, proj, today) == "red"

    def test_amber_milestone_due_soon(self):
        today = date(2026, 7, 15)
        tasks = [_task(due="2026-07-20", status="in progress")]
        proj = _project(milestones=[
            Milestone(name="M1", date="2026-07-20", done=False),
        ])
        assert project_health(tasks, proj, today) == "amber"

    def test_amber_moderate_overdue_fraction(self):
        """More than 10% but at most 25% overdue -> amber."""
        today = date(2026, 7, 15)
        # 2/10 = 20% overdue -> amber
        tasks = [_task(due="2026-07-01", status="todo")] * 2 + [
            _task(due="2026-07-20", status="in progress"),
        ] * 8
        proj = _project()
        assert project_health(tasks, proj, today) == "amber"

    def test_green_with_done_milestone(self):
        today = date(2026, 7, 15)
        tasks = [_task(due="2026-07-20", status="in progress")]
        proj = _project(milestones=[
            Milestone(name="M1", date="2026-07-01", done=True),
        ])
        assert project_health(tasks, proj, today) == "green"

    def test_no_tasks(self):
        today = date(2026, 7, 15)
        proj = _project()
        assert project_health([], proj, today) == "green"


# ── portfolio_kpis ─────────────────────────────────────────────────

class TestPortfolioKpis:
    def test_basic(self):
        today = date(2026, 7, 15)
        proj_a = _project(name="Alpha")
        tasks_a = [
            _task(status="done", percent_done=100),
            _task(status="in progress", percent_done=50, due="2026-07-20"),
        ]
        proj_b = _project(name="Beta")
        tasks_b = [
            _task(status="todo", percent_done=0, due="2026-07-10"),  # overdue
            _task(status="done", percent_done=100),
        ]

        result = portfolio_kpis([(proj_a, tasks_a), (proj_b, tasks_b)], today)

        assert result["total_tasks"] == 4
        assert result["total_done"] == 2
        assert result["overdue_total"] == 1
        assert len(result["per_project"]) == 2
        assert result["per_project"][0]["name"] == "Alpha"
        assert result["per_project"][1]["name"] == "Beta"
        assert result["overall_progress"] == pytest.approx(
            (75.0 * 2 + 50.0 * 2) / 4
        )

    def test_empty(self):
        result = portfolio_kpis([], date(2026, 7, 15))
        assert result["total_tasks"] == 0
        assert result["total_done"] == 0
        assert result["overall_progress"] == 0.0
        assert result["per_project"] == []
        assert result["overdue_total"] == 0
        assert result["milestones_due_soon"] == []

    def test_milestones_due_soon(self):
        today = date(2026, 7, 15)
        proj = _project(
            name="Gamma",
            milestones=[
                Milestone(name="Soon", date="2026-07-20", done=False),  # within 14d
                Milestone(name="Far", date="2026-12-01", done=False),   # too far
                Milestone(name="Done", date="2026-07-18", done=True),   # done
            ],
        )
        tasks = [_task(status="in progress", percent_done=50)]
        result = portfolio_kpis([(proj, tasks)], today)
        assert len(result["milestones_due_soon"]) == 1
        assert result["milestones_due_soon"][0]["name"] == "Soon"
        assert result["milestones_due_soon"][0]["project"] == "Gamma"


# ── resolve_cross_links ───────────────────────────────────────────

class TestResolveCrossLinks:
    def test_valid_link(self):
        proj_a = _project(
            name="Alpha",
            cross_links=[
                CrossProjectLink(
                    from_project="Alpha",
                    from_id="a1",
                    to_project="Beta",
                    to_id="b1",
                ),
            ],
        )
        tasks_a = [_task(id="a1", title="Task A1", due="2026-07-10")]
        proj_b = _project(name="Beta")
        tasks_b = [_task(id="b1", title="Task B1", start="2026-07-12")]

        result = resolve_cross_links([
            (proj_a, tasks_a),
            (proj_b, tasks_b),
        ])
        assert len(result) == 1
        assert result[0]["from_project"] == "Alpha"
        assert result[0]["to_project"] == "Beta"
        assert result[0]["from_task"].id == "a1"
        assert result[0]["to_task"].id == "b1"
        assert result[0]["from_due"] == date(2026, 7, 10)
        assert result[0]["to_start"] == date(2026, 7, 12)

    def test_unresolvable_link_missing_project(self):
        proj_a = _project(
            name="Alpha",
            cross_links=[
                CrossProjectLink(
                    from_project="Alpha",
                    from_id="a1",
                    to_project="NoSuchProject",
                    to_id="x",
                ),
            ],
        )
        tasks_a = [_task(id="a1")]
        result = resolve_cross_links([(proj_a, tasks_a)])
        assert result == []

    def test_unresolvable_link_missing_task(self):
        proj_a = _project(
            name="Alpha",
            cross_links=[
                CrossProjectLink(
                    from_project="Alpha",
                    from_id="a1",
                    to_project="Beta",
                    to_id="nonexistent",
                ),
            ],
        )
        tasks_a = [_task(id="a1")]
        proj_b = _project(name="Beta")
        tasks_b = [_task(id="b_real")]
        result = resolve_cross_links([(proj_a, tasks_a), (proj_b, tasks_b)])
        assert result == []


# ── slip_impact ────────────────────────────────────────────────────

class TestSlipImpact:
    def test_intra_project_slip(self):
        """Slipping an upstream task should propagate to its successor."""
        tasks = [
            _task(id="t1", title="Design", start="2026-07-01", effort=16.0),
            _task(id="t2", title="Build", depends=["t1"], effort=8.0),
        ]
        proj = _project(name="Alpha")
        result = slip_impact(
            [(proj, tasks)],
            slipped_project="Alpha",
            slipped_task_id="t1",
            slip_days=3,
        )
        # t2 depends on t1 — it must slip
        affected_ids = {r["task_id"] for r in result}
        assert "t2" in affected_ids
        for r in result:
            if r["task_id"] == "t2":
                assert r["slip"] > 0
                assert r["project"] == "Alpha"

    def test_cross_project_slip(self):
        """Slipping a task in project A should cascade to project B via link."""
        proj_a = _project(
            name="Alpha",
            cross_links=[
                CrossProjectLink(
                    from_project="Alpha",
                    from_id="a1",
                    to_project="Beta",
                    to_id="b1",
                ),
            ],
        )
        tasks_a = [
            _task(id="a1", title="Alpha Task", start="2026-07-01", effort=8.0),
        ]
        proj_b = _project(name="Beta")
        tasks_b = [
            _task(id="b1", title="Beta Task", start="2026-07-03", effort=8.0),
            _task(id="b2", title="Beta Follow", depends=["b1"], effort=8.0),
        ]

        result = slip_impact(
            [(proj_a, tasks_a), (proj_b, tasks_b)],
            slipped_project="Alpha",
            slipped_task_id="a1",
            slip_days=5,
        )
        # At least one task in Beta should be affected
        beta_affected = [r for r in result if r["project"] == "Beta"]
        assert len(beta_affected) > 0
        for r in beta_affected:
            assert r["slip"] > 0

    def test_nonexistent_project(self):
        result = slip_impact([], "NoSuch", "t1", 3)
        assert result == []

    def test_nonexistent_task(self):
        proj = _project(name="A")
        tasks = [_task(id="t1", start="2026-07-01", effort=8.0)]
        result = slip_impact([(proj, tasks)], "A", "nonexistent", 3)
        assert result == []

    def test_no_downstream(self):
        """A task with no successors and no cross links: no impact."""
        proj = _project(name="Solo")
        tasks = [_task(id="t1", title="Lone Wolf", start="2026-07-01", effort=8.0)]
        result = slip_impact([(proj, tasks)], "Solo", "t1", 5)
        assert result == []
