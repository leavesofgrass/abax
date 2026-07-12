"""Tests for GanttView and TimelineView (offscreen)."""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.core.pm.taskmodel import Task  # noqa: E402
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


def _sample_tasks() -> list[Task]:
    today = date.today()
    return [
        Task(
            row=0, title="Design", assignee="Alice",
            start=today, due=today + timedelta(days=5),
            id="T1", percent_done=0.6,
        ),
        Task(
            row=1, title="Implement", assignee="Bob",
            start=today + timedelta(days=3), due=today + timedelta(days=10),
            id="T2", depends=["T1"],
        ),
        Task(
            row=2, title="Test", assignee="Alice",
            start=today + timedelta(days=8), due=today + timedelta(days=12),
            id="T3",
        ),
        Task(row=3, title="Review", assignee="Charlie", id="T4"),
        Task(
            row=4, title="Release", assignee="Bob",
            start=today + timedelta(days=14), due=today + timedelta(days=14),
            id="T5", milestone=True,
        ),
    ]


# ── GanttView ─────────────────────────────────────────────────────────


class TestGanttView:
    def test_create_without_error(self, app):
        from abax.gui.pm.gantt_view import GanttView

        view = GanttView()
        assert view is not None

    def test_set_tasks(self, app):
        from abax.gui.pm.gantt_view import GanttView

        view = GanttView()
        tasks = _sample_tasks()
        view.setTasks(tasks)
        assert len(view._tasks) == 5

    def test_date_range_computed(self, app):
        from abax.gui.pm.gantt_view import GanttView

        view = GanttView()
        tasks = _sample_tasks()
        view.setTasks(tasks)
        assert view._date_start is not None
        assert view._date_end is not None
        today = date.today()
        assert view._date_start <= today
        assert view._date_end >= today + timedelta(days=14)

    def test_set_zoom(self, app):
        from abax.gui.pm.gantt_view import GanttView

        view = GanttView()
        for level in ("day", "week", "month"):
            view.setZoom(level)
            assert view._zoom == level

    def test_set_critical(self, app):
        from abax.gui.pm.gantt_view import GanttView

        view = GanttView()
        ids = {"T1", "T3"}
        view.setCritical(ids)
        assert view._critical_ids == ids

    def test_set_dependencies(self, app):
        from abax.gui.pm.gantt_view import GanttView

        view = GanttView()
        dag = {"T2": ["T1"], "T3": ["T2"]}
        view.setDependencies(dag)
        assert view._dag == dag

    def test_set_today(self, app):
        from abax.gui.pm.gantt_view import GanttView

        view = GanttView()
        today = date.today()
        view.setToday(today)
        assert view._today == today
        view.setToday(None)
        assert view._today is None

    def test_tasks_without_dates_no_crash(self, app):
        from abax.gui.pm.gantt_view import GanttView

        view = GanttView()
        tasks = [Task(row=0, title="No dates", id="X1")]
        view.setTasks(tasks)
        view.refresh()

    def test_task_selected_signal_exists(self, app):
        from abax.gui.pm.gantt_view import GanttView

        view = GanttView()
        received: list[int] = []
        view.taskSelected.connect(received.append)
        assert hasattr(view, "taskSelected")

    def test_task_moved_signal_exists(self, app):
        from abax.gui.pm.gantt_view import GanttView

        view = GanttView()
        received: list[tuple] = []
        view.taskMoved.connect(lambda *a: received.append(a))
        assert hasattr(view, "taskMoved")

    def test_set_context(self, app):
        from abax.gui.pm.gantt_view import GanttView

        view = GanttView()
        col_map = {"start": 2, "due": 3}
        view.setContext(sheet=None, col_map=col_map, first_col=1, on_set=None)
        assert view._col_map == col_map
        assert view._first_col == 1


# ── TimelineView ──────────────────────────────────────────────────────


class TestTimelineView:
    def test_create_without_error(self, app):
        from abax.gui.pm.timeline_view import TimelineView

        view = TimelineView()
        assert view is not None

    def test_set_tasks_computes_lanes(self, app):
        from abax.gui.pm.timeline_view import TimelineView

        view = TimelineView()
        tasks = _sample_tasks()
        view.setTasks(tasks)
        assert len(view._lanes) > 0
        assert "Alice" in view._lanes
        assert "Bob" in view._lanes
        assert "Charlie" in view._lanes

    def test_set_lane_field(self, app):
        from abax.gui.pm.timeline_view import TimelineView

        view = TimelineView()
        tasks = _sample_tasks()
        view.setTasks(tasks)
        view.setLaneField("status")
        assert view._lane_field == "status"

    def test_signal_exists(self, app):
        from abax.gui.pm.timeline_view import TimelineView

        view = TimelineView()
        received: list[int] = []
        view.taskSelected.connect(received.append)
        assert hasattr(view, "taskSelected")

    def test_set_zoom(self, app):
        from abax.gui.pm.timeline_view import TimelineView

        view = TimelineView()
        view.setZoom("day")
        assert view._zoom == "day"

    def test_vrows_built(self, app):
        from abax.gui.pm.timeline_view import TimelineView

        view = TimelineView()
        tasks = _sample_tasks()
        view.setTasks(tasks)
        assert len(view._vrows) > 0
        lane_headers = [r for r in view._vrows if r[0] == "lane"]
        assert len(lane_headers) == 3
