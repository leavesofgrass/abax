"""Tests for the PM report renderer and dashboard widget."""

from __future__ import annotations

import os
from datetime import date

import pytest

from abax.core.pm.projects import Milestone, Project
from abax.core.pm.report import report_html, report_markdown, report_sheet_data
from abax.core.pm.taskmodel import Task

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TODAY = date(2026, 7, 12)


def _make_tasks() -> list[Task]:
    """A handful of tasks with varied states."""
    return [
        Task(row=1, title="Design", status="Done", start=date(2026, 7, 1),
             due=date(2026, 7, 5), percent_done=100.0, effort=8.0),
        Task(row=2, title="Implement", status="In Progress",
             start=date(2026, 7, 5), due=date(2026, 7, 10),
             percent_done=60.0, effort=20.0),
        Task(row=3, title="Test", status="To Do",
             start=date(2026, 7, 10), due=date(2026, 7, 15),
             percent_done=0.0, effort=10.0),
        Task(row=4, title="Overdue bug", status="Open",
             start=date(2026, 7, 1), due=date(2026, 7, 8),
             percent_done=30.0, effort=4.0),
    ]


def _make_project(name: str = "Alpha") -> Project:
    return Project(
        name=name,
        sheet="Tasks",
        milestones=[
            Milestone(name="MVP", date="2026-07-10", done=True),
            Milestone(name="Launch", date="2026-07-20", done=False),
        ],
    )


# ---------------------------------------------------------------------------
# report_sheet_data tests
# ---------------------------------------------------------------------------


class TestReportSheetData:
    def test_headers_and_row_count(self):
        proj = _make_project()
        tasks = _make_tasks()
        headers, rows = report_sheet_data([(proj, tasks)], _TODAY)

        assert headers == [
            "Project", "Progress %", "Tasks", "Done", "Overdue",
            "Health", "Milestones",
        ]
        # 1 project row + 1 totals row
        assert len(rows) == 2

    def test_project_row_values(self):
        proj = _make_project()
        tasks = _make_tasks()
        headers, rows = report_sheet_data([(proj, tasks)], _TODAY)
        row = rows[0]

        assert row[0] == "Alpha"
        assert row[2] == "4"  # total tasks
        assert row[3] == "1"  # done count
        # Overdue: "Implement" (due Jul 10) and "Overdue bug" (due Jul 8)
        assert int(row[4]) >= 1  # at least one overdue

    def test_empty_projects_list(self):
        headers, rows = report_sheet_data([], _TODAY)
        assert headers == [
            "Project", "Progress %", "Tasks", "Done", "Overdue",
            "Health", "Milestones",
        ]
        # Just the totals row
        assert len(rows) == 1
        assert rows[0][0] == "TOTAL"
        assert rows[0][2] == "0"

    def test_multiple_projects(self):
        p1 = _make_project("Alpha")
        p2 = _make_project("Beta")
        tasks1 = _make_tasks()
        tasks2 = [
            Task(row=1, title="Deploy", status="Done", percent_done=100.0),
        ]
        headers, rows = report_sheet_data(
            [(p1, tasks1), (p2, tasks2)], _TODAY,
        )
        # 2 project rows + 1 totals row
        assert len(rows) == 3
        assert rows[0][0] == "Alpha"
        assert rows[1][0] == "Beta"
        assert rows[2][0] == "TOTAL"

    def test_milestone_summary(self):
        proj = _make_project()
        tasks = _make_tasks()
        _, rows = report_sheet_data([(proj, tasks)], _TODAY)
        # Milestone column: "1/2" (1 done of 2)
        assert rows[0][6] == "1/2"

    def test_totals_row_sums_tasks(self):
        p1 = _make_project("A")
        p2 = _make_project("B")
        t1 = _make_tasks()  # 4 tasks
        t2 = [Task(row=1, title="X", status="To Do")]
        _, rows = report_sheet_data([(p1, t1), (p2, t2)], _TODAY)
        totals = rows[-1]
        assert totals[2] == "5"  # 4 + 1


# ---------------------------------------------------------------------------
# report_html tests
# ---------------------------------------------------------------------------


class TestReportHtml:
    def test_returns_html_with_svg(self):
        proj = _make_project()
        tasks = _make_tasks()
        html = report_html([(proj, tasks)], _TODAY)

        assert "<!DOCTYPE html>" in html
        assert "<svg" in html
        assert "</svg>" in html

    def test_contains_project_name(self):
        proj = _make_project("Alpha")
        tasks = _make_tasks()
        html = report_html([(proj, tasks)], _TODAY)
        assert "Alpha" in html

    def test_contains_generation_date(self):
        proj = _make_project()
        tasks = _make_tasks()
        html = report_html([(proj, tasks)], _TODAY)
        assert "2026-07-12" in html

    def test_custom_title(self):
        proj = _make_project()
        tasks = _make_tasks()
        html = report_html(
            [(proj, tasks)], _TODAY, title="My Custom Report",
        )
        assert "My Custom Report" in html

    def test_milestone_list_in_html(self):
        proj = _make_project()
        tasks = _make_tasks()
        html = report_html([(proj, tasks)], _TODAY)
        assert "MVP" in html
        assert "Launch" in html

    def test_empty_projects_produces_valid_html(self):
        html = report_html([], _TODAY)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_health_classes_present(self):
        proj = _make_project()
        tasks = _make_tasks()
        html = report_html([(proj, tasks)], _TODAY)
        # At least one health class should appear
        assert "health-" in html


# ---------------------------------------------------------------------------
# report_markdown tests
# ---------------------------------------------------------------------------


class TestReportMarkdown:
    def test_returns_markdown_with_heading(self):
        proj = _make_project()
        tasks = _make_tasks()
        md = report_markdown([(proj, tasks)], _TODAY)
        assert md.startswith("# Project Report")

    def test_contains_project_name(self):
        proj = _make_project("Alpha")
        tasks = _make_tasks()
        md = report_markdown([(proj, tasks)], _TODAY)
        assert "## Alpha" in md

    def test_contains_generation_date(self):
        proj = _make_project()
        tasks = _make_tasks()
        md = report_markdown([(proj, tasks)], _TODAY)
        assert "2026-07-12" in md

    def test_custom_title(self):
        proj = _make_project()
        tasks = _make_tasks()
        md = report_markdown([(proj, tasks)], _TODAY, title="Sprint 12")
        assert "# Sprint 12" in md

    def test_summary_table(self):
        proj = _make_project()
        tasks = _make_tasks()
        md = report_markdown([(proj, tasks)], _TODAY)
        assert "| Project |" in md
        assert "| Alpha |" in md
        # Totals row is bold
        assert "| **TOTAL** |" in md

    def test_overdue_section(self):
        proj = _make_project()
        tasks = _make_tasks()
        md = report_markdown([(proj, tasks)], _TODAY)
        assert "### Overdue tasks" in md
        assert "Overdue bug" in md

    def test_milestone_checkboxes(self):
        proj = _make_project()
        tasks = _make_tasks()
        md = report_markdown([(proj, tasks)], _TODAY)
        assert "- [x] MVP" in md
        assert "- [ ] Launch" in md

    def test_empty_projects_list(self):
        md = report_markdown([], _TODAY)
        assert "# Project Report" in md
        assert "| **TOTAL** |" in md

    def test_multiple_projects(self):
        p1 = _make_project("Alpha")
        p2 = _make_project("Beta")
        tasks = _make_tasks()
        md = report_markdown(
            [(p1, tasks), (p2, [Task(row=1, title="X", status="Done",
                                     percent_done=100.0)])],
            _TODAY,
        )
        assert "## Alpha" in md
        assert "## Beta" in md

    def test_no_html_tags(self):
        proj = _make_project()
        tasks = _make_tasks()
        md = report_markdown([(proj, tasks)], _TODAY)
        assert "<html" not in md
        assert "<svg" not in md
        assert "<!DOCTYPE" not in md


# ---------------------------------------------------------------------------
# Dashboard widget tests
# ---------------------------------------------------------------------------

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, QEvent  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    _win = MainWindow(Settings())
    yield _win
    _win.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


class TestDashboardWidget:
    def test_creates_without_error(self, app):
        from abax.gui.pm.dashboard import DashboardView

        dash = DashboardView()
        assert dash is not None
        dash.deleteLater()

    def test_set_data_populates_kpis(self, app):
        from abax.gui.pm.dashboard import DashboardView

        dash = DashboardView()
        proj = _make_project()
        tasks = _make_tasks()
        dash.setData([(proj, tasks)], _TODAY)

        # KPI tiles should show actual numbers, not the default "--"
        assert dash._kpi_tasks._value_label.text() == "4"
        assert dash._kpi_done._value_label.text() == "1"
        assert "%" in dash._kpi_progress._value_label.text()
        dash.deleteLater()

    def test_handles_empty_project_list(self, app):
        from abax.gui.pm.dashboard import DashboardView

        dash = DashboardView()
        dash.setData([], _TODAY)

        assert dash._kpi_tasks._value_label.text() == "0"
        assert dash._kpi_done._value_label.text() == "0"
        assert dash._table.rowCount() == 0
        dash.deleteLater()

    def test_shows_milestone_entries(self, app):
        from abax.gui.pm.dashboard import DashboardView

        dash = DashboardView()
        proj = _make_project()
        tasks = _make_tasks()
        dash.setData([(proj, tasks)], _TODAY)

        ms_text = dash._ms_list.text()
        # "Launch" milestone is not done, so it should appear
        assert "Launch" in ms_text
        dash.deleteLater()

    def test_health_table_rows(self, app):
        from abax.gui.pm.dashboard import DashboardView

        dash = DashboardView()
        p1 = _make_project("A")
        p2 = _make_project("B")
        t1 = _make_tasks()
        t2 = [Task(row=1, title="X", status="Done", percent_done=100.0)]
        dash.setData([(p1, t1), (p2, t2)], _TODAY)

        assert dash._table.rowCount() == 2
        assert dash._table.item(0, 0).text() == "A"
        assert dash._table.item(1, 0).text() == "B"
        dash.deleteLater()
