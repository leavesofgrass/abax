"""Tests for abax.core.pm.exporter — Gantt/timeline SVG and PDF export."""

from __future__ import annotations

from datetime import date

from abax.core.pm.exporter import (
    _combine_svgs,
    _legend_svg,
    export_gantt_pdf,
    export_gantt_svg,
    export_report_svg,
    export_timeline_svg,
)
from abax.core.pm.projects import Milestone, Project
from abax.core.pm.taskmodel import Task

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tasks() -> list[Task]:
    """A small set of dated tasks for most tests."""
    return [
        Task(row=1, title="Design", start=date(2026, 1, 1), due=date(2026, 1, 15),
             id="T1", assignee="Alice", percent_done=100.0),
        Task(row=2, title="Build", start=date(2026, 1, 10), due=date(2026, 2, 10),
             id="T2", assignee="Bob", depends=["T1"], percent_done=50.0),
        Task(row=3, title="Test", start=date(2026, 2, 5), due=date(2026, 2, 28),
             id="T3", assignee="Alice", depends=["T2"]),
    ]


def _make_project(name: str = "Alpha") -> Project:
    return Project(name=name, sheet="Tasks")


# ===========================================================================
# Gantt SVG export
# ===========================================================================

class TestExportGanttSvg:
    """export_gantt_svg — basic file generation and options."""

    def test_basic_creates_file(self, tmp_path):
        out = tmp_path / "gantt.svg"
        export_gantt_svg(_make_tasks(), out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert content.startswith("<svg")
        assert "</svg>" in content

    def test_contains_task_names(self, tmp_path):
        out = tmp_path / "gantt.svg"
        export_gantt_svg(_make_tasks(), out)
        content = out.read_text(encoding="utf-8")
        assert "Design" in content
        assert "Build" in content
        assert "Test" in content

    def test_respects_width(self, tmp_path):
        out = tmp_path / "gantt.svg"
        export_gantt_svg(_make_tasks(), out, width=1200)
        content = out.read_text(encoding="utf-8")
        assert "1200" in content

    def test_title_appears(self, tmp_path):
        out = tmp_path / "gantt.svg"
        export_gantt_svg(_make_tasks(), out, title="Sprint 1")
        content = out.read_text(encoding="utf-8")
        assert "Sprint 1" in content

    def test_legend_rendered_by_default(self, tmp_path):
        out = tmp_path / "gantt.svg"
        export_gantt_svg(_make_tasks(), out)
        content = out.read_text(encoding="utf-8")
        assert "Critical path" in content
        assert "Milestone" in content
        assert "Today" in content

    def test_legend_disabled(self, tmp_path):
        out = tmp_path / "gantt.svg"
        export_gantt_svg(_make_tasks(), out, show_legend=False)
        content = out.read_text(encoding="utf-8")
        # The legend text should NOT appear.
        assert "Critical path" not in content

    def test_empty_task_list(self, tmp_path):
        out = tmp_path / "gantt.svg"
        export_gantt_svg([], out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "<svg" in content

    def test_critical_path_colour(self, tmp_path):
        tasks = _make_tasks()
        out = tmp_path / "gantt.svg"
        export_gantt_svg(tasks, out, critical={"T2"})
        content = out.read_text(encoding="utf-8")
        # The critical colour constant should appear in the bar fills.
        assert "#c62828" in content

    def test_today_line(self, tmp_path):
        out = tmp_path / "gantt.svg"
        export_gantt_svg(_make_tasks(), out, today=date(2026, 1, 20))
        content = out.read_text(encoding="utf-8")
        # The today-line colour and dashed stroke should appear.
        assert "#ef6c00" in content
        assert "stroke-dasharray" in content

    def test_milestones(self, tmp_path):
        ms = [Milestone(name="Beta", date="2026-02-01")]
        out = tmp_path / "gantt.svg"
        export_gantt_svg(_make_tasks(), out, milestones=ms)
        content = out.read_text(encoding="utf-8")
        assert "Beta" in content

    def test_string_path(self, tmp_path):
        out = str(tmp_path / "gantt_str.svg")
        export_gantt_svg(_make_tasks(), out)
        import pathlib
        assert pathlib.Path(out).exists()

    def test_overwrites_existing_file(self, tmp_path):
        out = tmp_path / "gantt.svg"
        out.write_text("old content", encoding="utf-8")
        export_gantt_svg(_make_tasks(), out)
        content = out.read_text(encoding="utf-8")
        assert "old content" not in content
        assert "<svg" in content


# ===========================================================================
# Timeline SVG export
# ===========================================================================

class TestExportTimelineSvg:
    """export_timeline_svg — timeline chart file generation."""

    def test_basic_creates_file(self, tmp_path):
        out = tmp_path / "timeline.svg"
        export_timeline_svg(_make_tasks(), out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert content.startswith("<svg")

    def test_contains_task_names(self, tmp_path):
        out = tmp_path / "timeline.svg"
        export_timeline_svg(_make_tasks(), out)
        content = out.read_text(encoding="utf-8")
        assert "Design" in content
        assert "Build" in content

    def test_title(self, tmp_path):
        out = tmp_path / "timeline.svg"
        export_timeline_svg(_make_tasks(), out, title="Q1 Timeline")
        content = out.read_text(encoding="utf-8")
        assert "Q1 Timeline" in content

    def test_explicit_lanes(self, tmp_path):
        out = tmp_path / "timeline.svg"
        export_timeline_svg(
            _make_tasks(), out, lanes=["Alice", "Bob", "Carol"],
        )
        content = out.read_text(encoding="utf-8")
        assert "Alice" in content
        assert "Bob" in content

    def test_empty_tasks(self, tmp_path):
        out = tmp_path / "timeline.svg"
        export_timeline_svg([], out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "<svg" in content

    def test_tasks_without_dates_skipped(self, tmp_path):
        tasks = [
            Task(row=1, title="No dates"),
            Task(row=2, title="Has dates", start=date(2026, 3, 1),
                 due=date(2026, 3, 15)),
        ]
        out = tmp_path / "timeline.svg"
        export_timeline_svg(tasks, out)
        content = out.read_text(encoding="utf-8")
        # The dateless task is skipped silently; the dated one appears.
        assert "Has dates" in content


# ===========================================================================
# PDF wrapper
# ===========================================================================

class TestExportGanttPdf:
    """export_gantt_pdf — HTML wrapper for browser-based PDF printing."""

    def test_generates_html(self, tmp_path):
        out = tmp_path / "gantt.html"
        export_gantt_pdf(_make_tasks(), out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert content.startswith("<!DOCTYPE html>")

    def test_html_contains_svg(self, tmp_path):
        out = tmp_path / "gantt.html"
        export_gantt_pdf(_make_tasks(), out)
        content = out.read_text(encoding="utf-8")
        assert "<svg" in content
        assert "</svg>" in content

    def test_html_has_print_css(self, tmp_path):
        out = tmp_path / "gantt.html"
        export_gantt_pdf(_make_tasks(), out)
        content = out.read_text(encoding="utf-8")
        assert "@page" in content

    def test_title_in_html_head(self, tmp_path):
        out = tmp_path / "gantt.html"
        export_gantt_pdf(_make_tasks(), out, title="Release Plan")
        content = out.read_text(encoding="utf-8")
        assert "<title>Release Plan</title>" in content

    def test_legend_in_pdf(self, tmp_path):
        out = tmp_path / "gantt.html"
        export_gantt_pdf(_make_tasks(), out, show_legend=True)
        content = out.read_text(encoding="utf-8")
        assert "Critical path" in content

    def test_no_legend_in_pdf(self, tmp_path):
        out = tmp_path / "gantt.html"
        export_gantt_pdf(_make_tasks(), out, show_legend=False)
        content = out.read_text(encoding="utf-8")
        assert "Critical path" not in content


# ===========================================================================
# Multi-project report
# ===========================================================================

class TestExportReportSvg:
    """export_report_svg — stacked multi-project report."""

    def test_multiple_projects(self, tmp_path):
        p1 = _make_project("Alpha")
        p2 = _make_project("Bravo")
        projects = [
            (p1, _make_tasks()),
            (p2, _make_tasks()),
        ]
        out = tmp_path / "report.svg"
        export_report_svg(projects, out)
        content = out.read_text(encoding="utf-8")
        assert "Alpha" in content
        assert "Bravo" in content
        assert content.startswith("<svg")

    def test_empty_project_list(self, tmp_path):
        out = tmp_path / "report.svg"
        export_report_svg([], out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "<svg" in content
        assert "No projects" in content

    def test_single_project(self, tmp_path):
        p = _make_project("Solo")
        out = tmp_path / "report.svg"
        export_report_svg([(p, _make_tasks())], out)
        content = out.read_text(encoding="utf-8")
        assert "Solo" in content

    def test_today_line_in_report(self, tmp_path):
        p = _make_project("Alpha")
        out = tmp_path / "report.svg"
        export_report_svg([(p, _make_tasks())], out, today=date(2026, 1, 20))
        content = out.read_text(encoding="utf-8")
        assert "#ef6c00" in content

    def test_width_respected(self, tmp_path):
        p = _make_project("Alpha")
        out = tmp_path / "report.svg"
        export_report_svg([(p, _make_tasks())], out, width=1000)
        content = out.read_text(encoding="utf-8")
        assert "1000" in content


# ===========================================================================
# Internal helpers
# ===========================================================================

class TestLegendSvg:
    """_legend_svg — colour-key legend block."""

    def test_returns_svg(self):
        svg = _legend_svg()
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_contains_all_labels(self):
        svg = _legend_svg()
        for label in ("Scheduled", "Done", "Critical path",
                      "In progress", "Milestone", "Today"):
            assert label in svg

    def test_custom_width(self):
        svg = _legend_svg(width=600)
        assert "600" in svg


class TestCombineSvgs:
    """_combine_svgs — stacking multiple SVGs vertically."""

    def test_combines_two(self):
        a = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50" width="100" height="50"><text>A</text></svg>'
        b = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 30" width="100" height="30"><text>B</text></svg>'
        result = _combine_svgs(a, b, width=100)
        assert result.startswith("<svg")
        assert "<text>A</text>" in result
        assert "<text>B</text>" in result
        # Total height should be 80 (50 + 30).
        assert 'viewBox="0 0 100 80"' in result

    def test_single_svg(self):
        a = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 60" width="200" height="60"><rect/></svg>'
        result = _combine_svgs(a, width=200)
        assert "<rect/>" in result
