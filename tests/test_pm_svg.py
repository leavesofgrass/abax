"""Tests for abax.core.pm.pmsvg — Gantt, timeline, and calendar month SVG."""

from __future__ import annotations

from datetime import date

from abax.core.pm.pmsvg import calendar_month_svg, gantt_svg, timeline_svg
from abax.core.pm.projects import Milestone
from abax.core.pm.taskmodel import Task

# -- helpers -----------------------------------------------------------------

def _is_valid_svg(svg: str) -> None:
    assert svg.strip().startswith("<svg")
    assert svg.strip().endswith("</svg>")


# -- TestGanttSvg ------------------------------------------------------------


class TestGanttSvg:
    def _sample_tasks(self) -> list[Task]:
        return [
            Task(row=0, title="Design", id="T1",
                 start=date(2025, 1, 1), due=date(2025, 1, 10)),
            Task(row=1, title="Build", id="T2",
                 start=date(2025, 1, 8), due=date(2025, 1, 20),
                 depends=["T1"]),
            Task(row=2, title="Test", id="T3",
                 start=date(2025, 1, 18), due=date(2025, 1, 25),
                 depends=["T2"], percent_done=0.5),
        ]

    def test_basic(self):
        svg = gantt_svg(self._sample_tasks())
        _is_valid_svg(svg)
        assert "Design" in svg
        assert "Build" in svg
        assert "Test" in svg

    def test_critical_path_highlighting(self):
        tasks = self._sample_tasks()
        svg_crit = gantt_svg(tasks, critical={"T2"})
        _is_valid_svg(svg_crit)
        assert "#c62828" in svg_crit

    def test_today_line(self):
        svg = gantt_svg(self._sample_tasks(), today=date(2025, 1, 15))
        _is_valid_svg(svg)
        assert "<line" in svg
        assert "stroke-dasharray" in svg

    def test_milestones(self):
        ms = [Milestone(name="Alpha", date="2025-01-12", done=False)]
        svg = gantt_svg(self._sample_tasks(), milestones=ms)
        _is_valid_svg(svg)
        assert "<path" in svg
        assert "Alpha" in svg

    def test_tasks_without_dates_skipped(self):
        tasks = [
            Task(row=0, title="No dates"),
            Task(row=1, title="Has dates",
                 start=date(2025, 1, 1), due=date(2025, 1, 5)),
        ]
        svg = gantt_svg(tasks)
        _is_valid_svg(svg)
        assert "Has dates" in svg
        assert "No dates" not in svg

    def test_dependency_arrows(self):
        tasks = self._sample_tasks()
        svg = gantt_svg(tasks)
        _is_valid_svg(svg)
        assert "<path" in svg
        assert "arrowhead" in svg

    def test_empty_task_list(self):
        svg = gantt_svg([])
        _is_valid_svg(svg)

    def test_percent_done_overlay(self):
        tasks = [
            Task(row=0, title="Half done", id="T1",
                 start=date(2025, 1, 1), due=date(2025, 1, 10),
                 percent_done=0.5),
        ]
        svg = gantt_svg(tasks)
        _is_valid_svg(svg)
        assert svg.count("<rect") >= 3  # bg + bar + percent overlay

    def test_title(self):
        svg = gantt_svg(self._sample_tasks(), title="Project Plan")
        _is_valid_svg(svg)
        assert "Project Plan" in svg


# -- TestTimelineSvg ---------------------------------------------------------


class TestTimelineSvg:
    def test_single_lane(self):
        items = [
            {"name": "Phase A", "start": date(2025, 2, 1), "end": date(2025, 2, 10)},
            {"name": "Phase B", "start": date(2025, 2, 8), "end": date(2025, 2, 20)},
        ]
        svg = timeline_svg(items)
        _is_valid_svg(svg)
        assert "Phase A" in svg
        assert "Phase B" in svg

    def test_multi_lane(self):
        items = [
            {"name": "Task X", "start": date(2025, 3, 1), "end": date(2025, 3, 5),
             "lane": "Alice"},
            {"name": "Task Y", "start": date(2025, 3, 3), "end": date(2025, 3, 8),
             "lane": "Bob"},
        ]
        svg = timeline_svg(items, lanes=["Alice", "Bob"])
        _is_valid_svg(svg)
        assert "Alice" in svg
        assert "Bob" in svg
        assert "Task X" in svg

    def test_empty_items(self):
        svg = timeline_svg([])
        _is_valid_svg(svg)

    def test_title(self):
        items = [
            {"name": "X", "start": date(2025, 4, 1), "end": date(2025, 4, 3)},
        ]
        svg = timeline_svg(items, title="Roadmap")
        _is_valid_svg(svg)
        assert "Roadmap" in svg


# -- TestCalendarMonthSvg ----------------------------------------------------


class TestCalendarMonthSvg:
    def test_tasks_on_specific_days(self):
        tasks = [
            Task(row=0, title="Ship v1",
                 due=date(2025, 6, 15)),
            Task(row=1, title="Review",
                 due=date(2025, 6, 20)),
        ]
        svg = calendar_month_svg(2025, 6, tasks)
        _is_valid_svg(svg)
        assert "Ship v1" in svg
        assert "Review" in svg

    def test_month_year_header(self):
        svg = calendar_month_svg(2025, 6, [])
        _is_valid_svg(svg)
        assert "June" in svg
        assert "2025" in svg

    def test_empty_task_list(self):
        svg = calendar_month_svg(2025, 1, [])
        _is_valid_svg(svg)
        assert "January" in svg
        assert "Mon" in svg
        assert "Sun" in svg

    def test_custom_title(self):
        svg = calendar_month_svg(2025, 3, [], title="Sprint 7")
        _is_valid_svg(svg)
        assert "Sprint 7" in svg

    def test_milestone_diamond(self):
        tasks = [
            Task(row=0, title="Launch", milestone=True,
                 due=date(2025, 6, 10)),
        ]
        svg = calendar_month_svg(2025, 6, tasks)
        _is_valid_svg(svg)
        assert "<path" in svg

    def test_span_background(self):
        tasks = [
            Task(row=0, title="Sprint",
                 start=date(2025, 6, 5), due=date(2025, 6, 8)),
        ]
        svg = calendar_month_svg(2025, 6, tasks)
        _is_valid_svg(svg)
        assert "#e3f2fd" in svg
