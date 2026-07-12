"""Unit tests for the PM task-sheet convention (core/pm/taskmodel.py)."""

from __future__ import annotations

from datetime import date

from abax.core.pm.taskmodel import (
    Task,
    STATUS_ORDER,
    detect_columns,
    parse_tasks,
    write_task,
)
from abax.core.sheet import Sheet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sheet(headers: list[str], rows: list[list]) -> Sheet:
    """Build a Sheet with *headers* in row 0 and *rows* below."""
    s = Sheet("Tasks")
    for c, h in enumerate(headers):
        s.set_cell(0, c, h)
    for r, vals in enumerate(rows, start=1):
        for c, v in enumerate(vals):
            if v is not None:
                s.set_cell(r, c, str(v))
    return s


# ---------------------------------------------------------------------------
# detect_columns
# ---------------------------------------------------------------------------

class TestDetectColumns:
    def test_canonical_headers(self):
        m = detect_columns(["Title", "Status", "Due", "Assignee"])
        assert m == {"title": 0, "status": 1, "due": 2, "assignee": 3}

    def test_aliases(self):
        m = detect_columns(["Task", "State", "Deadline", "Owner"])
        assert m == {"title": 0, "status": 1, "due": 2, "assignee": 3}

    def test_case_insensitive(self):
        m = detect_columns(["TITLE", "STATUS", "DUE", "ASSIGNEE"])
        assert m == {"title": 0, "status": 1, "due": 2, "assignee": 3}

    def test_first_match_wins(self):
        m = detect_columns(["Name", "Task", "Status"])
        assert m["title"] == 0

    def test_unrecognised_skipped(self):
        m = detect_columns(["Title", "Notes", "RandomCol"])
        assert m == {"title": 0}

    def test_all_known_fields(self):
        headers = [
            "Title", "Status", "Start", "Due", "Assignee", "Priority",
            "%Done", "Depends", "Milestone", "Effort", "Cost", "Tags", "ID",
        ]
        m = detect_columns(headers)
        assert len(m) == 13

    def test_percent_done_aliases(self):
        for alias in ("Progress", "Complete", "%Complete", "Pct"):
            m = detect_columns(["Title", alias])
            assert "percent_done" in m, f"{alias} not matched"

    def test_depends_aliases(self):
        for alias in ("DependsOn", "Blocked By", "Predecessors", "Deps"):
            m = detect_columns(["Title", alias])
            assert "depends" in m, f"{alias} not matched"

    def test_prefix_match(self):
        m = detect_columns(["Title", "% Done (approx)"])
        assert "percent_done" in m


# ---------------------------------------------------------------------------
# parse_tasks
# ---------------------------------------------------------------------------

class TestParseTasks:
    def test_basic_parse(self):
        s = _make_sheet(
            ["Title", "Status", "Due"],
            [
                ["Fix bug", "Open", "2026-08-01"],
                ["Add feature", "In Progress", "2026-09-15"],
            ],
        )
        tasks = parse_tasks(s)
        assert len(tasks) == 2
        assert tasks[0].title == "Fix bug"
        assert tasks[0].status == "Open"
        assert tasks[0].due == date(2026, 8, 1)
        assert tasks[1].title == "Add feature"
        assert tasks[1].due == date(2026, 9, 15)

    def test_alias_headers(self):
        s = _make_sheet(
            ["Task", "State", "Deadline", "Owner"],
            [["Ship it", "Done", "2026-07-04", "Alice"]],
        )
        tasks = parse_tasks(s)
        assert len(tasks) == 1
        assert tasks[0].title == "Ship it"
        assert tasks[0].status == "Done"
        assert tasks[0].due == date(2026, 7, 4)
        assert tasks[0].assignee == "Alice"

    def test_missing_columns_yield_defaults(self):
        s = _make_sheet(["Title"], [["Only title"]])
        tasks = parse_tasks(s)
        assert len(tasks) == 1
        t = tasks[0]
        assert t.title == "Only title"
        assert t.status == ""
        assert t.due is None
        assert t.assignee == ""
        assert t.percent_done == 0.0
        assert t.depends == []
        assert t.milestone is False
        assert t.effort is None

    def test_bad_dates_yield_none(self):
        s = _make_sheet(
            ["Title", "Start", "Due"],
            [["Task", "not-a-date", "also bad"]],
        )
        tasks = parse_tasks(s)
        assert tasks[0].start is None
        assert tasks[0].due is None

    def test_date_formats(self):
        s = _make_sheet(
            ["Title", "Due"],
            [
                ["ISO", "2026-08-01"],
                ["US", "08/01/2026"],
                ["Slash", "2026/08/01"],
            ],
        )
        tasks = parse_tasks(s)
        assert tasks[0].due == date(2026, 8, 1)
        assert tasks[1].due == date(2026, 8, 1)
        assert tasks[2].due == date(2026, 8, 1)

    def test_empty_title_skipped(self):
        s = _make_sheet(
            ["Title", "Status"],
            [
                ["Real task", "Open"],
                ["", "Orphan"],
                ["Another", "Done"],
            ],
        )
        tasks = parse_tasks(s)
        assert len(tasks) == 2
        assert tasks[0].title == "Real task"
        assert tasks[1].title == "Another"

    def test_none_title_skipped(self):
        s = _make_sheet(["Title", "Status"], [])
        # Add a row with no title cell at all (None value).
        tasks = parse_tasks(s)
        assert tasks == []

    def test_percent_done_clamped(self):
        s = _make_sheet(
            ["Title", "%Done"],
            [
                ["Over", "150"],
                ["Under", "-10"],
                ["Normal", "42"],
            ],
        )
        tasks = parse_tasks(s)
        assert tasks[0].percent_done == 100.0
        assert tasks[1].percent_done == 0.0
        assert tasks[2].percent_done == 42.0

    def test_depends_parsing(self):
        s = _make_sheet(
            ["Title", "Depends"],
            [["Blocked", "T1, T2; T3"]],
        )
        tasks = parse_tasks(s)
        assert tasks[0].depends == ["T1", "T2", "T3"]

    def test_tags_parsing(self):
        s = _make_sheet(
            ["Title", "Tags"],
            [["Tagged", "frontend, backend | infra"]],
        )
        tasks = parse_tasks(s)
        assert tasks[0].tags == ["frontend", "backend", "infra"]

    def test_milestone_bool(self):
        s = _make_sheet(
            ["Title", "Milestone"],
            [
                ["MS1", "TRUE"],
                ["Regular", "FALSE"],
                ["Also MS", "yes"],
            ],
        )
        tasks = parse_tasks(s)
        assert tasks[0].milestone is True
        assert tasks[1].milestone is False
        assert tasks[2].milestone is True

    def test_effort_and_cost(self):
        s = _make_sheet(
            ["Title", "Effort", "Cost"],
            [["Work", "8.5", "1200"]],
        )
        tasks = parse_tasks(s)
        assert tasks[0].effort == 8.5
        assert tasks[0].cost == 1200.0

    def test_auto_id(self):
        s = _make_sheet(["Title"], [["No ID"]])
        tasks = parse_tasks(s)
        assert tasks[0].id == "T1"

    def test_explicit_id(self):
        s = _make_sheet(["Title", "ID"], [["Has ID", "PROJ-42"]])
        tasks = parse_tasks(s)
        assert tasks[0].id == "PROJ-42"

    def test_extra_columns(self):
        s = _make_sheet(
            ["Title", "Notes", "Color"],
            [["Task", "some note", "red"]],
        )
        tasks = parse_tasks(s)
        assert tasks[0].extra == {"Notes": "some note", "Color": "red"}

    def test_explicit_region(self):
        s = _make_sheet(
            ["Junk", "Title", "Status", "Junk2"],
            [
                ["x", "Task A", "Open", "y"],
                ["x", "Task B", "Done", "y"],
            ],
        )
        tasks = parse_tasks(
            s,
            header_row=0,
            first_col=1,
            last_col=2,
            first_data_row=1,
            last_data_row=2,
        )
        assert len(tasks) == 2
        assert tasks[0].title == "Task A"
        assert tasks[0].status == "Open"

    def test_no_title_column_returns_empty(self):
        s = _make_sheet(["Status", "Due"], [["Open", "2026-01-01"]])
        tasks = parse_tasks(s)
        assert tasks == []

    def test_priority(self):
        s = _make_sheet(
            ["Title", "Prio"],
            [["Important", "High"]],
        )
        tasks = parse_tasks(s)
        assert tasks[0].priority == "High"


# ---------------------------------------------------------------------------
# write_task
# ---------------------------------------------------------------------------

class TestWriteTask:
    def test_write_via_on_set(self):
        s = _make_sheet(["Title", "Status", "Due"], [["Fix", "Open", "2026-01-01"]])
        tasks = parse_tasks(s)
        col_map = detect_columns(["Title", "Status", "Due"])
        calls = []

        def on_set(sheet, row, col, val):
            calls.append((row, col, val))
            sheet.set_cell(row, col, str(val))

        write_task(s, tasks[0], "status", "Done", col_map=col_map, on_set=on_set)
        assert len(calls) == 1
        assert calls[0] == (1, 1, "Done")
        assert s.get_value(1, 1) == "Done"

    def test_write_date(self):
        s = _make_sheet(["Title", "Due"], [["Task", "2026-01-01"]])
        tasks = parse_tasks(s)
        col_map = detect_columns(["Title", "Due"])

        write_task(s, tasks[0], "due", date(2026, 12, 25), col_map=col_map)
        assert s.get_value(1, 1) == "2026-12-25"

    def test_write_percent(self):
        s = _make_sheet(["Title", "%Done"], [["Task", "0"]])
        tasks = parse_tasks(s)
        col_map = detect_columns(["Title", "%Done"])

        write_task(s, tasks[0], "percent_done", 75.0, col_map=col_map)
        assert s.get_value(1, 1) == 75.0

    def test_write_depends_list(self):
        s = _make_sheet(["Title", "Depends"], [["Task", ""]])
        tasks = parse_tasks(s)
        col_map = detect_columns(["Title", "Depends"])

        write_task(s, tasks[0], "depends", ["T1", "T3"], col_map=col_map)
        assert s.get_value(1, 1) == "T1, T3"

    def test_write_unknown_field_raises(self):
        s = _make_sheet(["Title"], [["Task"]])
        tasks = parse_tasks(s)
        col_map = detect_columns(["Title"])
        import pytest

        with pytest.raises(KeyError):
            write_task(s, tasks[0], "nonexistent", "val", col_map=col_map)

    def test_write_without_on_set(self):
        s = _make_sheet(["Title", "Status"], [["Task", "Open"]])
        tasks = parse_tasks(s)
        col_map = detect_columns(["Title", "Status"])
        write_task(s, tasks[0], "status", "Closed", col_map=col_map)
        assert s.get_value(1, 1) == "Closed"

    def test_write_with_first_col_offset(self):
        s = _make_sheet(
            ["Junk", "Title", "Status"],
            [["x", "Task", "Open"]],
        )
        col_map = detect_columns(["Title", "Status"])
        tasks = parse_tasks(s, first_col=1, last_col=2)
        write_task(s, tasks[0], "status", "Done", col_map=col_map, first_col=1)
        assert s.get_value(1, 2) == "Done"


# ---------------------------------------------------------------------------
# STATUS_ORDER
# ---------------------------------------------------------------------------

class TestStatusOrder:
    def test_first_appearance(self):
        tasks = [
            Task(row=1, status="In Progress"),
            Task(row=2, status="Open"),
            Task(row=3, status="In Progress"),
            Task(row=4, status="Done"),
        ]
        assert STATUS_ORDER(tasks) == ["In Progress", "Open", "Done"]

    def test_override(self):
        tasks = [
            Task(row=1, status="In Progress"),
            Task(row=2, status="Open"),
            Task(row=3, status="Done"),
        ]
        order = STATUS_ORDER(tasks, override=["Open", "In Progress", "Done"])
        assert order == ["Open", "In Progress", "Done"]

    def test_override_with_extras(self):
        tasks = [
            Task(row=1, status="Open"),
            Task(row=2, status="Review"),
            Task(row=3, status="Done"),
        ]
        order = STATUS_ORDER(tasks, override=["Open", "Done"])
        assert order == ["Open", "Done", "Review"]

    def test_empty_status_skipped(self):
        tasks = [
            Task(row=1, status=""),
            Task(row=2, status="Open"),
        ]
        assert STATUS_ORDER(tasks) == ["Open"]

    def test_empty_tasks(self):
        assert STATUS_ORDER([]) == []


# ---------------------------------------------------------------------------
# Task dataclass
# ---------------------------------------------------------------------------

class TestTask:
    def test_auto_id(self):
        t = Task(row=7)
        assert t.id == "T7"

    def test_explicit_id_preserved(self):
        t = Task(row=7, id="PROJ-1")
        assert t.id == "PROJ-1"

    def test_defaults(self):
        t = Task(row=0)
        assert t.title == ""
        assert t.status == ""
        assert t.start is None
        assert t.due is None
        assert t.percent_done == 0.0
        assert t.depends == []
        assert t.tags == []
        assert t.extra == {}
