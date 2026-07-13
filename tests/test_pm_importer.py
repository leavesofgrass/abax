"""Tests for abax.core.pm.importer — CSV and MS Project XML task import/export."""

from __future__ import annotations

import csv
import io
import textwrap
from datetime import date
from pathlib import Path

import pytest

from abax.core.pm.importer import (
    _parse_date,
    _parse_duration_hours,
    import_csv,
    import_mpp_xml,
    tasks_to_csv,
)
from abax.core.pm.taskmodel import Task

# ── Helpers ──────────────────────────────────────────────────────────────────

def _csv(text: str) -> io.StringIO:
    """Dedent and wrap CSV text in a StringIO."""
    return io.StringIO(textwrap.dedent(text).strip())


def _msp_xml(tasks_xml: str = "", *, ns: bool = True) -> io.StringIO:
    """Wrap task XML fragments in a valid MS Project XML document."""
    if ns:
        return io.StringIO(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Project xmlns="http://schemas.microsoft.com/project">\n'
            f"  <Tasks>\n{tasks_xml}\n  </Tasks>\n"
            "</Project>"
        )
    return io.StringIO(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<Project><Tasks>{tasks_xml}</Tasks></Project>"
    )


# ── _parse_date unit tests ──────────────────────────────────────────────────

class TestParseDate:
    def test_iso(self):
        assert _parse_date("2024-03-15") == date(2024, 3, 15)

    def test_iso_slash(self):
        assert _parse_date("2024/03/15") == date(2024, 3, 15)

    def test_us(self):
        assert _parse_date("03/15/2024") == date(2024, 3, 15)

    def test_us_dash(self):
        assert _parse_date("03-15-2024") == date(2024, 3, 15)

    def test_eu(self):
        assert _parse_date("15.03.2024") == date(2024, 3, 15)

    def test_iso_datetime(self):
        assert _parse_date("2024-03-15T08:00:00") == date(2024, 3, 15)

    def test_empty(self):
        assert _parse_date("") is None

    def test_garbage(self):
        assert _parse_date("not-a-date") is None

    def test_invalid_date(self):
        assert _parse_date("2024-13-45") is None


# ── _parse_duration_hours unit tests ─────────────────────────────────────────

class TestParseDuration:
    def test_hours(self):
        assert _parse_duration_hours("PT8H0M0S") == 8.0

    def test_days(self):
        assert _parse_duration_hours("P5D") == 40.0  # 5 * 8h

    def test_days_and_hours(self):
        assert _parse_duration_hours("P1DT4H0M0S") == 12.0

    def test_empty(self):
        assert _parse_duration_hours("") is None

    def test_invalid(self):
        assert _parse_duration_hours("INVALID") is None

    def test_minutes(self):
        assert _parse_duration_hours("PT0H30M0S") == 0.5


# ── CSV import ───────────────────────────────────────────────────────────────

class TestImportCSV:
    def test_basic(self):
        tasks = import_csv(_csv("""\
            Title,Status,Due
            Build widget,To Do,2024-06-01
            Test widget,Done,2024-06-15
        """))
        assert len(tasks) == 2
        assert tasks[0].title == "Build widget"
        assert tasks[0].status == "To Do"
        assert tasks[0].due == date(2024, 6, 1)
        assert tasks[0].row == 1
        assert tasks[1].row == 2

    def test_alias_headers(self):
        """detect_columns aliases like Task, State, End, Owner should work."""
        tasks = import_csv(_csv("""\
            Task,State,End,Owner
            Alpha,Done,2024-01-01,Alice
        """))
        assert tasks[0].title == "Alpha"
        assert tasks[0].status == "Done"
        assert tasks[0].due == date(2024, 1, 1)
        assert tasks[0].assignee == "Alice"

    def test_semicolon_delimiter(self):
        tasks = import_csv(_csv("""\
            Title;Status;Due
            Alpha;To Do;2024-01-01
        """))
        assert len(tasks) == 1
        assert tasks[0].title == "Alpha"

    def test_tab_delimiter(self):
        tasks = import_csv(io.StringIO("Title\tStatus\nAlpha\tDone"))
        assert tasks[0].title == "Alpha"
        assert tasks[0].status == "Done"

    def test_bom_handling(self, tmp_path: Path):
        p = tmp_path / "bom.csv"
        p.write_bytes(b"\xef\xbb\xbfTitle,Status\nHello,Done\n")
        tasks = import_csv(p)
        assert len(tasks) == 1
        assert tasks[0].title == "Hello"

    def test_empty_rows_skipped(self):
        tasks = import_csv(_csv("""\
            Title,Status
            Alpha,Done
            ,
            Beta,To Do
        """))
        assert len(tasks) == 2
        assert tasks[0].title == "Alpha"
        assert tasks[1].title == "Beta"
        # Row numbers reflect position in CSV (1-based after header)
        assert tasks[0].row == 1
        assert tasks[1].row == 3

    def test_missing_columns(self):
        """CSV with only some known columns — rest of Task fields use defaults."""
        tasks = import_csv(_csv("""\
            Title
            Solo task
        """))
        assert tasks[0].title == "Solo task"
        assert tasks[0].status == ""
        assert tasks[0].due is None

    def test_extra_columns_to_extra(self):
        tasks = import_csv(_csv("""\
            Title,Department,Location
            Alpha,Engineering,NYC
        """))
        assert tasks[0].extra == {"Department": "Engineering", "Location": "NYC"}

    def test_date_us_format(self):
        tasks = import_csv(_csv("""\
            Title,Due
            Alpha,06/15/2024
        """))
        assert tasks[0].due == date(2024, 6, 15)

    def test_date_eu_format(self):
        tasks = import_csv(_csv("""\
            Title,Due
            Alpha,15.06.2024
        """))
        assert tasks[0].due == date(2024, 6, 15)

    def test_percent_done(self):
        tasks = import_csv(_csv("""\
            Title,% Done
            Alpha,50
        """))
        assert tasks[0].percent_done == 50.0

    def test_percent_done_with_pct_sign(self):
        tasks = import_csv(_csv("""\
            Title,Progress
            Alpha,75%
        """))
        assert tasks[0].percent_done == 75.0

    def test_effort_and_cost(self):
        tasks = import_csv(_csv("""\
            Title,Effort,Cost
            Alpha,8.5,1200.50
        """))
        assert tasks[0].effort == 8.5
        assert tasks[0].cost == 1200.50

    def test_depends_comma_separated(self):
        tasks = import_csv(_csv("""\
            Title;Depends
            Alpha;1, 2, 3
        """))
        assert tasks[0].depends == ["1", "2", "3"]

    def test_tags_semicolon_separated(self):
        tasks = import_csv(_csv("""\
            Title,Tags
            Alpha,urgent;backend;api
        """))
        assert tasks[0].tags == ["urgent", "backend", "api"]

    def test_milestone_bool(self):
        tasks = import_csv(_csv("""\
            Title,Milestone
            Alpha,true
            Beta,false
        """))
        assert tasks[0].milestone is True
        assert tasks[1].milestone is False

    def test_id_field(self):
        tasks = import_csv(_csv("""\
            ID,Title
            T-001,Alpha
        """))
        assert tasks[0].id == "T-001"

    def test_unicode_task_names(self):
        tasks = import_csv(_csv("""\
            Title,Status
            Erstelle Bericht,Erledigt
            タスク一,完了
        """))
        assert tasks[0].title == "Erstelle Bericht"
        assert tasks[1].title == "タスク一"

    def test_empty_file(self):
        assert import_csv(io.StringIO("")) == []

    def test_header_only(self):
        assert import_csv(_csv("Title,Status")) == []

    def test_file_path_string(self, tmp_path: Path):
        p = tmp_path / "test.csv"
        p.write_text("Title,Status\nAlpha,Done\n", encoding="utf-8")
        tasks = import_csv(str(p))
        assert tasks[0].title == "Alpha"

    def test_priority_field(self):
        tasks = import_csv(_csv("""\
            Title,Priority
            Alpha,High
        """))
        assert tasks[0].priority == "High"


# ── MS Project XML import ────────────────────────────────────────────────────

class TestImportMPPXML:
    def test_basic_task(self):
        xml = _msp_xml("""\
        <Task>
          <UID>1</UID>
          <Name>Design Phase</Name>
          <Start>2024-03-15T08:00:00</Start>
          <Finish>2024-03-20T17:00:00</Finish>
          <PercentComplete>50</PercentComplete>
          <Duration>PT40H0M0S</Duration>
        </Task>""")
        tasks = import_mpp_xml(xml)
        assert len(tasks) == 1
        t = tasks[0]
        assert t.title == "Design Phase"
        assert t.id == "1"
        assert t.start == date(2024, 3, 15)
        assert t.due == date(2024, 3, 20)
        assert t.percent_done == 50.0
        assert t.status == "In Progress"
        assert t.effort == 40.0
        assert t.row == 1

    def test_done_task(self):
        xml = _msp_xml("""\
        <Task>
          <UID>1</UID>
          <Name>Completed</Name>
          <PercentComplete>100</PercentComplete>
        </Task>""")
        tasks = import_mpp_xml(xml)
        assert tasks[0].status == "Done"

    def test_todo_task(self):
        xml = _msp_xml("""\
        <Task>
          <UID>1</UID>
          <Name>Not started</Name>
          <PercentComplete>0</PercentComplete>
        </Task>""")
        tasks = import_mpp_xml(xml)
        assert tasks[0].status == "To Do"

    def test_predecessors(self):
        xml = _msp_xml("""\
        <Task>
          <UID>2</UID>
          <Name>Phase 2</Name>
          <PredecessorLink><PredecessorUID>1</PredecessorUID></PredecessorLink>
          <PredecessorLink><PredecessorUID>3</PredecessorUID></PredecessorLink>
        </Task>""")
        tasks = import_mpp_xml(xml)
        assert tasks[0].depends == ["1", "3"]

    def test_milestone(self):
        xml = _msp_xml("""\
        <Task>
          <UID>1</UID>
          <Name>Release</Name>
          <Milestone>1</Milestone>
        </Task>""")
        tasks = import_mpp_xml(xml)
        assert tasks[0].milestone is True

    def test_skip_summary_task_uid0(self):
        xml = _msp_xml("""\
        <Task>
          <UID>0</UID>
          <Name></Name>
        </Task>
        <Task>
          <UID>1</UID>
          <Name>Real task</Name>
        </Task>""")
        tasks = import_mpp_xml(xml)
        assert len(tasks) == 1
        assert tasks[0].title == "Real task"

    def test_empty_project(self):
        xml = _msp_xml("")
        tasks = import_mpp_xml(xml)
        assert tasks == []

    def test_malformed_xml_raises_valueerror(self):
        with pytest.raises(ValueError, match="Not valid XML"):
            import_mpp_xml(io.StringIO("<not>valid<xml"))

    def test_wrong_root_raises_valueerror(self):
        with pytest.raises(ValueError, match="Not an MS Project XML"):
            import_mpp_xml(io.StringIO("<Root><Tasks/></Root>"))

    def test_duration_days(self):
        xml = _msp_xml("""\
        <Task>
          <UID>1</UID>
          <Name>Long task</Name>
          <Duration>P5D</Duration>
        </Task>""")
        tasks = import_mpp_xml(xml)
        assert tasks[0].effort == 40.0

    def test_multiple_tasks_ordering(self):
        xml = _msp_xml("""\
        <Task><UID>1</UID><Name>First</Name></Task>
        <Task><UID>2</UID><Name>Second</Name></Task>
        <Task><UID>3</UID><Name>Third</Name></Task>""")
        tasks = import_mpp_xml(xml)
        assert len(tasks) == 3
        assert [t.title for t in tasks] == ["First", "Second", "Third"]
        assert [t.row for t in tasks] == [1, 2, 3]

    def test_file_path(self, tmp_path: Path):
        content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Project xmlns="http://schemas.microsoft.com/project">\n'
            "  <Tasks>\n"
            "    <Task><UID>1</UID><Name>Hello</Name></Task>\n"
            "  </Tasks>\n"
            "</Project>"
        )
        p = tmp_path / "project.xml"
        p.write_text(content, encoding="utf-8")
        tasks = import_mpp_xml(p)
        assert tasks[0].title == "Hello"

    def test_file_path_string(self, tmp_path: Path):
        content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Project xmlns="http://schemas.microsoft.com/project">\n'
            "  <Tasks>\n"
            "    <Task><UID>1</UID><Name>World</Name></Task>\n"
            "  </Tasks>\n"
            "</Project>"
        )
        p = tmp_path / "project.xml"
        p.write_text(content, encoding="utf-8")
        tasks = import_mpp_xml(str(p))
        assert tasks[0].title == "World"


# ── CSV export ───────────────────────────────────────────────────────────────

class TestTasksToCSV:
    def test_basic_export(self):
        tasks = [
            Task(row=1, title="Alpha", status="Done", id="1"),
            Task(row=2, title="Beta", status="To Do", id="2"),
        ]
        out = io.StringIO()
        tasks_to_csv(tasks, out)
        out.seek(0)
        lines = out.getvalue().strip().split("\n")
        assert len(lines) == 3  # header + 2 rows
        assert "id" in lines[0]
        assert "Alpha" in lines[1]

    def test_field_selection(self):
        tasks = [Task(row=1, title="Alpha", status="Done")]
        out = io.StringIO()
        tasks_to_csv(tasks, out, fields=["title", "status"])
        out.seek(0)
        reader = list(csv.reader(out))
        assert reader[0] == ["title", "status"]
        assert reader[1] == ["Alpha", "Done"]

    def test_date_iso_format(self):
        tasks = [Task(row=1, start=date(2024, 3, 15), due=date(2024, 6, 1))]
        out = io.StringIO()
        tasks_to_csv(tasks, out, fields=["start", "due"])
        out.seek(0)
        reader = list(csv.reader(out))
        assert reader[1] == ["2024-03-15", "2024-06-01"]

    def test_tags_semicolon(self):
        tasks = [Task(row=1, tags=["a", "b", "c"])]
        out = io.StringIO()
        tasks_to_csv(tasks, out, fields=["tags"])
        out.seek(0)
        reader = list(csv.reader(out))
        assert reader[1] == ["a;b;c"]

    def test_none_values(self):
        tasks = [Task(row=1)]
        out = io.StringIO()
        tasks_to_csv(tasks, out, fields=["effort", "cost"])
        out.seek(0)
        reader = list(csv.reader(out))
        assert reader[1] == ["", ""]

    def test_file_path(self, tmp_path: Path):
        tasks = [Task(row=1, title="Alpha")]
        p = tmp_path / "out.csv"
        tasks_to_csv(tasks, p)
        content = p.read_text(encoding="utf-8")
        assert "Alpha" in content

    def test_depends_comma_joined(self):
        tasks = [Task(row=1, depends=["1", "2"])]
        out = io.StringIO()
        tasks_to_csv(tasks, out, fields=["depends"])
        out.seek(0)
        reader = list(csv.reader(out))
        assert reader[1] == ["1;2"]

    def test_percent_done_whole_number(self):
        tasks = [Task(row=1, percent_done=50.0)]
        out = io.StringIO()
        tasks_to_csv(tasks, out, fields=["percent_done"])
        out.seek(0)
        reader = list(csv.reader(out))
        assert reader[1] == ["50"]

    def test_percent_done_decimal(self):
        tasks = [Task(row=1, percent_done=33.3)]
        out = io.StringIO()
        tasks_to_csv(tasks, out, fields=["percent_done"])
        out.seek(0)
        reader = list(csv.reader(out))
        assert reader[1] == ["33.3"]


# ── Round-trip ───────────────────────────────────────────────────────────────

class TestRoundTrip:
    def test_csv_roundtrip(self):
        """Import → export → reimport should produce equivalent tasks."""
        original = _csv("""\
            Title,Status,Due,Assignee,Priority
            Build widget,To Do,2024-06-01,Alice,High
            Test widget,Done,2024-06-15,Bob,Low
        """)
        tasks = import_csv(original)

        # Export
        buf = io.StringIO()
        tasks_to_csv(tasks, buf, fields=["title", "status", "due", "assignee", "priority"])

        # Re-import
        buf.seek(0)
        tasks2 = import_csv(buf)

        assert len(tasks2) == len(tasks)
        for t1, t2 in zip(tasks, tasks2):
            assert t1.title == t2.title
            assert t1.status == t2.status
            assert t1.due == t2.due
            assert t1.assignee == t2.assignee
            assert t1.priority == t2.priority

    def test_csv_roundtrip_with_tags_and_dates(self):
        """Tags and dates survive a round-trip."""
        original = _csv("""\
            Title,Tags,Start,Due
            Alpha,urgent;backend,2024-01-01,2024-06-01
        """)
        tasks = import_csv(original)
        buf = io.StringIO()
        tasks_to_csv(tasks, buf, fields=["title", "tags", "start", "due"])
        buf.seek(0)
        tasks2 = import_csv(buf)
        assert tasks2[0].tags == ["urgent", "backend"]
        assert tasks2[0].start == date(2024, 1, 1)
        assert tasks2[0].due == date(2024, 6, 1)

    def test_csv_export_reimport_all_fields(self):
        """All default fields survive a round-trip."""
        tasks = [Task(
            row=1, id="T-1", title="Full task", status="In Progress",
            start=date(2024, 1, 1), due=date(2024, 6, 1),
            assignee="Alice", priority="High", percent_done=50.0,
            effort=8.0, cost=100.0, tags=["a", "b"],
        )]
        buf = io.StringIO()
        tasks_to_csv(tasks, buf)
        buf.seek(0)
        tasks2 = import_csv(buf)
        t = tasks2[0]
        assert t.id == "T-1"
        assert t.title == "Full task"
        assert t.status == "In Progress"
        assert t.start == date(2024, 1, 1)
        assert t.due == date(2024, 6, 1)
        assert t.assignee == "Alice"
        assert t.priority == "High"
        assert t.percent_done == 50.0
        assert t.effort == 8.0
        assert t.cost == 100.0
        assert t.tags == ["a", "b"]
