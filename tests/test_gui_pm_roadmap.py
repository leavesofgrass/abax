"""Tests for RoadmapView (offscreen)."""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.core.pm.projects import CrossProjectLink, Milestone, Project  # noqa: E402
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


def _sample_projects() -> list[tuple[Project, list[Task]]]:
    today = date.today()
    proj_a = Project(
        name="Alpha",
        milestones=[
            Milestone(name="Beta Release", date=(today + timedelta(days=10)).isoformat()),
            Milestone(name="GA", date=(today + timedelta(days=30)).isoformat()),
        ],
    )
    tasks_a = [
        Task(
            row=0, title="Design", assignee="Alice",
            start=today, due=today + timedelta(days=5),
            id="A1", percent_done=60.0,
        ),
        Task(
            row=1, title="Implement", assignee="Bob",
            start=today + timedelta(days=3), due=today + timedelta(days=12),
            id="A2", depends=["A1"],
        ),
        Task(
            row=2, title="Test", assignee="Alice",
            start=today + timedelta(days=10), due=today + timedelta(days=15),
            id="A3",
        ),
    ]

    proj_b = Project(
        name="Bravo",
        milestones=[
            Milestone(name="Launch", date=(today + timedelta(days=20)).isoformat()),
        ],
    )
    tasks_b = [
        Task(
            row=0, title="Setup", assignee="Charlie",
            start=today + timedelta(days=1), due=today + timedelta(days=4),
            id="B1",
        ),
        Task(
            row=1, title="Build", assignee="Charlie",
            start=today + timedelta(days=5), due=today + timedelta(days=18),
            id="B2", depends=["B1"],
        ),
    ]
    return [(proj_a, tasks_a), (proj_b, tasks_b)]


# -- Creation ----------------------------------------------------------------


def test_create_without_error(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    assert view is not None


def test_canvas_created(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    assert view._canvas is not None
    sz = view._canvas.sizeHint()
    assert sz.width() >= 400
    assert sz.height() >= 200


# -- setProjects --------------------------------------------------------------


def test_set_projects_populates_lanes(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    data = _sample_projects()
    view.setProjects(data)
    assert len(view._lanes) == 2


def test_set_projects_empty_list(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    view.setProjects([])
    assert len(view._lanes) == 0


def test_lane_count_matches_project_count(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    data = _sample_projects()
    view.setProjects(data)
    assert len(view._lanes) == len(data)


# -- Date range ---------------------------------------------------------------


def test_date_range_covers_tasks(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    data = _sample_projects()
    view.setProjects(data)
    assert view._date_start is not None
    assert view._date_end is not None

    # Collect all task dates
    all_dates: list[date] = []
    for _, tasks in data:
        for t in tasks:
            if t.start:
                all_dates.append(t.start)
            if t.due:
                all_dates.append(t.due)
    assert view._date_start <= min(all_dates)
    assert view._date_end >= max(all_dates)


def test_date_range_empty_projects(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    proj = Project(name="Empty")
    view.setProjects([(proj, [])])
    # Should still have a date range (defaults to around today)
    assert view._date_start is not None
    assert view._date_end is not None


# -- setZoom ------------------------------------------------------------------


def test_set_zoom_all_levels(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    for level in ("day", "week", "month", "quarter"):
        view.setZoom(level)
        assert view._zoom == level


def test_set_zoom_invalid_ignored(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    view.setZoom("month")
    view.setZoom("invalid")
    assert view._zoom == "month"


# -- setToday -----------------------------------------------------------------


def test_set_today(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    today = date.today()
    view.setToday(today)
    assert view._today == today


# -- setCrossLinks ------------------------------------------------------------


def test_set_cross_links(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    links = [
        CrossProjectLink(
            from_project="Alpha", from_id="A2",
            to_project="Bravo", to_id="B1",
        ),
    ]
    view.setCrossLinks(links)
    assert len(view._cross_links) == 1
    assert view._cross_links[0].from_project == "Alpha"


# -- Signals ------------------------------------------------------------------


def test_task_selected_signal_exists(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    received: list[tuple] = []
    view.taskSelected.connect(lambda *a: received.append(a))
    assert hasattr(view, "taskSelected")


def test_milestone_clicked_signal_exists(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    received: list[tuple] = []
    view.milestoneClicked.connect(lambda *a: received.append(a))
    assert hasattr(view, "milestoneClicked")


# -- Milestones ---------------------------------------------------------------


def test_milestones_tracked_per_project(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    data = _sample_projects()
    view.setProjects(data)
    # Alpha has 2 milestones, Bravo has 1
    assert len(view._lanes[0].milestones) == 2
    assert len(view._lanes[1].milestones) == 1


# -- Empty state / render without crash ---------------------------------------


def test_empty_state_renders(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    view.setProjects([])
    view.setToday(date.today())
    view.refresh()  # should not crash


def test_no_dates_renders(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    proj = Project(name="NoDates")
    tasks = [Task(row=0, title="No dates", id="X1")]
    view.setProjects([(proj, tasks)])
    view.refresh()  # should not crash


# -- Keyboard handlers -------------------------------------------------------


def test_keyboard_handlers_exist(app):
    from abax.gui.pm.roadmap_view import _RoadmapCanvas

    assert hasattr(_RoadmapCanvas, "keyPressEvent")


# -- setCritical --------------------------------------------------------------


def test_set_critical(app):
    from abax.gui.pm.roadmap_view import RoadmapView

    view = RoadmapView()
    view.setCritical({"A1", "B2"})
    assert view._critical_ids == {"A1", "B2"}
