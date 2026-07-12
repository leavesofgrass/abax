"""Tests for abax.core.pm.capacity — workload aggregation and rebalancing."""

from __future__ import annotations

from datetime import date

import pytest

from abax.core.pm.capacity import (
    Overallocation,
    Person,
    Suggestion,
    Task,
    detect_people,
    overallocation,
    rebalance,
    skill_match,
    suggest_reassignment,
    workload_by_week,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _task(
    row: int = 0,
    title: str = "",
    start: date | None = None,
    due: date | None = None,
    assignee: str = "",
    effort: float | None = None,
    tags: list[str] | None = None,
    **kw,
) -> Task:
    return Task(
        row=row,
        title=title,
        start=start,
        due=due,
        assignee=assignee,
        effort=effort,
        tags=tags or [],
        **kw,
    )


# ===================================================================
# workload_by_week
# ===================================================================

class TestWorkloadByWeek:
    def test_single_task_one_week(self):
        # Mon 2025-01-06 to Fri 2025-01-10 — 5 business days, default effort
        t = _task(row=1, assignee="Alice",
                  start=date(2025, 1, 6), due=date(2025, 1, 10))
        wl = workload_by_week([t], date(2025, 1, 6), date(2025, 1, 10))
        assert "Alice" in wl
        # 5 bdays * 8h = 40h, all in one week starting 2025-01-06
        assert wl["Alice"]["2025-01-06"] == pytest.approx(40.0)

    def test_explicit_effort(self):
        t = _task(row=1, assignee="Bob",
                  start=date(2025, 1, 6), due=date(2025, 1, 10), effort=20.0)
        wl = workload_by_week([t], date(2025, 1, 6), date(2025, 1, 10))
        # 20h spread over 5 days = 4h/day * 5 = 20h in one week
        assert wl["Bob"]["2025-01-06"] == pytest.approx(20.0)

    def test_task_spanning_two_weeks(self):
        # Mon 2025-01-06 to Fri 2025-01-17 — 10 business days
        t = _task(row=1, assignee="Carol",
                  start=date(2025, 1, 6), due=date(2025, 1, 17), effort=80.0)
        wl = workload_by_week([t], date(2025, 1, 6), date(2025, 1, 17))
        assert wl["Carol"]["2025-01-06"] == pytest.approx(40.0)
        assert wl["Carol"]["2025-01-13"] == pytest.approx(40.0)

    def test_no_assignee_skipped(self):
        t = _task(row=1, start=date(2025, 1, 6), due=date(2025, 1, 10))
        wl = workload_by_week([t], date(2025, 1, 6), date(2025, 1, 10))
        assert wl == {}

    def test_no_dates_skipped(self):
        t = _task(row=1, assignee="Dan")
        wl = workload_by_week([t], date(2025, 1, 6), date(2025, 1, 10))
        assert wl == {}

    def test_no_start_skipped(self):
        t = _task(row=1, assignee="Eve", due=date(2025, 1, 10))
        wl = workload_by_week([t], date(2025, 1, 6), date(2025, 1, 10))
        assert wl == {}

    def test_empty_tasks(self):
        wl = workload_by_week([], date(2025, 1, 6), date(2025, 1, 10))
        assert wl == {}

    def test_window_clips_task(self):
        # Task spans two weeks but we only look at the second week
        t = _task(row=1, assignee="Fay",
                  start=date(2025, 1, 6), due=date(2025, 1, 17), effort=80.0)
        wl = workload_by_week([t], date(2025, 1, 13), date(2025, 1, 17))
        assert "2025-01-06" not in wl.get("Fay", {})
        assert wl["Fay"]["2025-01-13"] == pytest.approx(40.0)

    def test_weekend_days_excluded(self):
        # Sat-Sun 2025-01-11/12 — no business days
        t = _task(row=1, assignee="Gus",
                  start=date(2025, 1, 11), due=date(2025, 1, 12))
        wl = workload_by_week([t], date(2025, 1, 11), date(2025, 1, 12))
        assert wl == {}  # 0 bdays → skipped

    def test_multiple_assignees(self):
        t1 = _task(row=1, assignee="A",
                   start=date(2025, 1, 6), due=date(2025, 1, 10), effort=10)
        t2 = _task(row=2, assignee="B",
                   start=date(2025, 1, 6), due=date(2025, 1, 10), effort=20)
        wl = workload_by_week([t1, t2], date(2025, 1, 6), date(2025, 1, 10))
        assert wl["A"]["2025-01-06"] == pytest.approx(10.0)
        assert wl["B"]["2025-01-06"] == pytest.approx(20.0)

    def test_zero_effort(self):
        t = _task(row=1, assignee="Zoe",
                  start=date(2025, 1, 6), due=date(2025, 1, 10), effort=0.0)
        wl = workload_by_week([t], date(2025, 1, 6), date(2025, 1, 10))
        # 0h spread → 0h each day
        assert wl["Zoe"]["2025-01-06"] == pytest.approx(0.0)

    def test_custom_hours_per_day(self):
        t = _task(row=1, assignee="Hal",
                  start=date(2025, 1, 6), due=date(2025, 1, 10))
        wl = workload_by_week([t], date(2025, 1, 6), date(2025, 1, 10),
                              hours_per_day=4.0)
        assert wl["Hal"]["2025-01-06"] == pytest.approx(20.0)


# ===================================================================
# detect_people
# ===================================================================

class TestDetectPeople:
    def test_basic(self):
        sheet = [
            ["Name", "Capacity", "Skills"],
            ["Alice", 40, "python, sql"],
            ["Bob", 30, "design"],
        ]
        people = detect_people(sheet)
        assert len(people) == 2
        assert people[0].name == "Alice"
        assert people[0].weekly_capacity == 40.0
        assert people[0].skills == ["python", "sql"]
        assert people[1].name == "Bob"
        assert people[1].weekly_capacity == 30.0

    def test_alias_person_hours_tags(self):
        sheet = [
            ["Person", "Hours", "Tags"],
            ["Carol", 35, "backend"],
        ]
        people = detect_people(sheet)
        assert len(people) == 1
        assert people[0].name == "Carol"
        assert people[0].weekly_capacity == 35.0
        assert people[0].skills == ["backend"]

    def test_alias_who_availability_expertise(self):
        sheet = [
            ["Who", "Availability", "Expertise"],
            ["Dan", 20, "frontend, react"],
        ]
        people = detect_people(sheet)
        assert len(people) == 1
        assert people[0].name == "Dan"

    def test_alias_resource_weekly_skill(self):
        sheet = [
            ["Resource", "Weekly", "Skill"],
            ["Eve", 25, "devops"],
        ]
        people = detect_people(sheet)
        assert len(people) == 1
        assert people[0].name == "Eve"

    def test_no_name_column(self):
        sheet = [
            ["Foo", "Bar"],
            ["Alice", 40],
        ]
        assert detect_people(sheet) == []

    def test_empty_sheet(self):
        assert detect_people([]) == []

    def test_name_only(self):
        sheet = [
            ["Name"],
            ["Alice"],
        ]
        people = detect_people(sheet)
        assert len(people) == 1
        assert people[0].weekly_capacity == 40.0  # default
        assert people[0].skills == []

    def test_empty_name_skipped(self):
        sheet = [
            ["Name", "Capacity"],
            ["Alice", 40],
            ["", 30],
            ["Bob", 25],
        ]
        people = detect_people(sheet)
        assert len(people) == 2
        assert people[1].name == "Bob"

    def test_first_col_offset(self):
        sheet = [
            ["ignore", "Name", "Capacity"],
            ["x", "Alice", 40],
        ]
        people = detect_people(sheet, first_col=1)
        assert len(people) == 1
        assert people[0].name == "Alice"

    def test_last_col(self):
        sheet = [
            ["Name", "Capacity", "Skills", "Extra"],
            ["Alice", 40, "py", "ignored"],
        ]
        people = detect_people(sheet, last_col=2)
        assert len(people) == 1
        assert people[0].skills == ["py"]

    def test_invalid_capacity_uses_default(self):
        sheet = [
            ["Name", "Capacity"],
            ["Alice", "not-a-number"],
        ]
        people = detect_people(sheet)
        assert people[0].weekly_capacity == 40.0

    def test_header_row(self):
        sheet = [
            ["title row"],
            ["Name", "Capacity"],
            ["Alice", 40],
        ]
        people = detect_people(sheet, header_row=1)
        assert len(people) == 1
        assert people[0].name == "Alice"


# ===================================================================
# overallocation
# ===================================================================

class TestOverallocation:
    def test_no_overallocation(self):
        wl = {"Alice": {"2025-01-06": 30.0}}
        result = overallocation(wl)
        assert result == []

    def test_simple_overallocation(self):
        wl = {"Alice": {"2025-01-06": 50.0}}
        result = overallocation(wl)
        assert len(result) == 1
        assert result[0].assignee == "Alice"
        assert result[0].excess == pytest.approx(10.0)

    def test_with_people_custom_capacity(self):
        people = [Person("Alice", weekly_capacity=30.0)]
        wl = {"Alice": {"2025-01-06": 35.0}}
        result = overallocation(wl, people)
        assert len(result) == 1
        assert result[0].capacity == 30.0
        assert result[0].excess == pytest.approx(5.0)

    def test_unknown_person_uses_default(self):
        people = [Person("Bob", weekly_capacity=30.0)]
        wl = {"Alice": {"2025-01-06": 50.0}}
        result = overallocation(wl, people, default_capacity=45.0)
        assert len(result) == 1
        assert result[0].capacity == 45.0
        assert result[0].excess == pytest.approx(5.0)

    def test_empty_workload(self):
        assert overallocation({}) == []

    def test_exactly_at_capacity(self):
        wl = {"Alice": {"2025-01-06": 40.0}}
        assert overallocation(wl) == []

    def test_multiple_people_and_weeks(self):
        wl = {
            "Alice": {"2025-01-06": 50.0, "2025-01-13": 30.0},
            "Bob": {"2025-01-06": 45.0},
        }
        result = overallocation(wl)
        assert len(result) == 2
        assignees = [(r.assignee, r.week) for r in result]
        assert ("Alice", "2025-01-06") in assignees
        assert ("Bob", "2025-01-06") in assignees


# ===================================================================
# skill_match
# ===================================================================

class TestSkillMatch:
    def test_basic_ranking(self):
        people = [
            Person("Alice", skills=["python", "sql"]),
            Person("Bob", skills=["python"]),
            Person("Carol", skills=["design"]),
        ]
        result = skill_match(["python", "sql"], people)
        assert result[0][0].name == "Alice"
        assert result[0][1] == 2
        assert result[1][0].name == "Bob"
        assert result[1][1] == 1

    def test_tiebreak_alphabetical(self):
        people = [
            Person("Zoe", skills=["python"]),
            Person("Alice", skills=["python"]),
        ]
        result = skill_match(["python"], people)
        assert result[0][0].name == "Alice"
        assert result[1][0].name == "Zoe"

    def test_no_tags(self):
        people = [Person("Alice", skills=["python"])]
        result = skill_match([], people)
        assert result[0][1] == 0

    def test_no_people(self):
        assert skill_match(["python"], []) == []

    def test_empty_both(self):
        assert skill_match([], []) == []


# ===================================================================
# suggest_reassignment
# ===================================================================

class TestSuggestReassignment:
    def test_basic_suggestion(self):
        tasks = [
            _task(row=1, title="Small", assignee="Alice",
                  start=date(2025, 1, 6), due=date(2025, 1, 10), effort=10,
                  tags=["python"]),
        ]
        people = [
            Person("Alice", weekly_capacity=40, skills=["python"]),
            Person("Bob", weekly_capacity=40, skills=["python"]),
        ]
        wl = {"Alice": {"2025-01-06": 50.0}, "Bob": {"2025-01-06": 10.0}}
        result = suggest_reassignment(tasks, "Alice", "2025-01-06", people, wl)
        assert len(result) == 1
        assert result[0].to_assignee == "Bob"

    def test_no_candidate_with_capacity(self):
        tasks = [
            _task(row=1, title="Big", assignee="Alice",
                  start=date(2025, 1, 6), due=date(2025, 1, 10), effort=10,
                  tags=["python"]),
        ]
        people = [
            Person("Alice", weekly_capacity=40, skills=["python"]),
            Person("Bob", weekly_capacity=40, skills=["python"]),
        ]
        wl = {"Alice": {"2025-01-06": 50.0}, "Bob": {"2025-01-06": 35.0}}
        result = suggest_reassignment(tasks, "Alice", "2025-01-06", people, wl)
        assert result == []

    def test_picks_smallest_effort(self):
        tasks = [
            _task(row=1, title="Big", assignee="Alice",
                  start=date(2025, 1, 6), due=date(2025, 1, 10), effort=30,
                  tags=["python"]),
            _task(row=2, title="Small", assignee="Alice",
                  start=date(2025, 1, 6), due=date(2025, 1, 10), effort=5,
                  tags=["python"]),
        ]
        people = [
            Person("Alice", weekly_capacity=40, skills=["python"]),
            Person("Bob", weekly_capacity=40, skills=["python"]),
        ]
        wl = {"Alice": {"2025-01-06": 50.0}, "Bob": {"2025-01-06": 0.0}}
        result = suggest_reassignment(tasks, "Alice", "2025-01-06", people, wl)
        assert len(result) >= 1
        assert result[0].task.title == "Small"

    def test_no_tasks_for_assignee(self):
        tasks = [
            _task(row=1, title="T1", assignee="Bob",
                  start=date(2025, 1, 6), due=date(2025, 1, 10), effort=10),
        ]
        people = [Person("Bob", weekly_capacity=40)]
        result = suggest_reassignment(tasks, "Alice", "2025-01-06", people)
        assert result == []

    def test_without_workload(self):
        tasks = [
            _task(row=1, title="T1", assignee="Alice",
                  start=date(2025, 1, 6), due=date(2025, 1, 10), effort=10,
                  tags=["py"]),
        ]
        people = [
            Person("Alice", weekly_capacity=40, skills=["py"]),
            Person("Bob", weekly_capacity=40, skills=["py"]),
        ]
        result = suggest_reassignment(tasks, "Alice", "2025-01-06", people)
        assert len(result) == 1
        assert result[0].to_assignee == "Bob"


# ===================================================================
# rebalance
# ===================================================================

class TestRebalance:
    def test_basic_rebalance(self):
        tasks = [
            _task(row=1, title="T1", assignee="Alice",
                  start=date(2025, 1, 6), due=date(2025, 1, 10), effort=50,
                  tags=["python"]),
            _task(row=2, title="T2", assignee="Alice",
                  start=date(2025, 1, 6), due=date(2025, 1, 10), effort=5,
                  tags=["python"]),
        ]
        people = [
            Person("Alice", weekly_capacity=40, skills=["python"]),
            Person("Bob", weekly_capacity=40, skills=["python"]),
        ]
        result = rebalance(tasks, people)
        assert len(result) >= 1
        assert result[0].from_assignee == "Alice"

    def test_no_overallocation(self):
        tasks = [
            _task(row=1, title="T1", assignee="Alice",
                  start=date(2025, 1, 6), due=date(2025, 1, 10), effort=20),
        ]
        people = [Person("Alice", weekly_capacity=40)]
        assert rebalance(tasks, people) == []

    def test_empty_tasks(self):
        assert rebalance([], [Person("Alice")]) == []

    def test_empty_people(self):
        tasks = [_task(row=1, assignee="Alice",
                       start=date(2025, 1, 6), due=date(2025, 1, 10))]
        assert rebalance(tasks, []) == []

    def test_no_dates_on_tasks(self):
        tasks = [_task(row=1, assignee="Alice")]
        people = [Person("Alice")]
        assert rebalance(tasks, people) == []


# ===================================================================
# Integration / edge cases
# ===================================================================

class TestEdgeCases:
    def test_task_due_before_start_skipped(self):
        t = _task(row=1, assignee="A",
                  start=date(2025, 1, 10), due=date(2025, 1, 6))
        wl = workload_by_week([t], date(2025, 1, 6), date(2025, 1, 10))
        assert wl == {}

    def test_single_day_task(self):
        t = _task(row=1, assignee="A",
                  start=date(2025, 1, 6), due=date(2025, 1, 6), effort=8)
        wl = workload_by_week([t], date(2025, 1, 6), date(2025, 1, 6))
        assert wl["A"]["2025-01-06"] == pytest.approx(8.0)

    def test_overallocation_dataclass_fields(self):
        oa = Overallocation("Alice", "2025-01-06", 50.0, 40.0, 10.0)
        assert oa.assignee == "Alice"
        assert oa.week == "2025-01-06"
        assert oa.allocated == 50.0
        assert oa.capacity == 40.0
        assert oa.excess == 10.0

    def test_person_defaults(self):
        p = Person("X")
        assert p.weekly_capacity == 40.0
        assert p.skills == []

    def test_suggestion_fields(self):
        t = _task(row=1, title="T")
        s = Suggestion(task=t, from_assignee="A", to_assignee="B", reason="r")
        assert s.from_assignee == "A"
        assert s.to_assignee == "B"

    def test_layering_no_engine_import(self):
        """capacity.py must not import from abax.engine or abax.gui."""
        import importlib
        mod = importlib.import_module("abax.core.pm.capacity")
        src = mod.__file__
        assert src is not None
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "abax.engine" not in text
        assert "abax.gui" not in text
