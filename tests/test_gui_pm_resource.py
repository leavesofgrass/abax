"""Tests for the ResourceView workload heatmap widget."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, QColor, QEvent  # noqa: E402
from abax.gui.pm.resource_view import (  # noqa: E402
    ResourceView,
    _load_ratio_color,
    _tasks_in_week,
    _week_iso,
)
from abax.gui.theming import Theme  # noqa: E402
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


@pytest.fixture()
def rv(app):
    """Standalone ResourceView (no MainWindow parent)."""
    w = ResourceView()
    yield w
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _make_task(
    tid: str = "T1",
    assignee: str = "Alice",
    start: datetime.date | None = None,
    due: datetime.date | None = None,
    effort: float = 8.0,
    row: int = 0,
):
    return SimpleNamespace(
        id=tid,
        assignee=assignee,
        start=start or datetime.date(2026, 1, 5),
        due=due or datetime.date(2026, 1, 9),
        effort=effort,
        tags=[],
        row=row,
    )


# ------------------------------------------------------------------
# _week_iso helper
# ------------------------------------------------------------------


class TestWeekIso:
    def test_basic(self):
        assert _week_iso(datetime.date(2026, 1, 5)) == "2026-W02"

    def test_year_boundary(self):
        # 2025-12-29 is ISO week 1 of 2026 (Mon)
        assert _week_iso(datetime.date(2025, 12, 29)) == "2026-W01"


# ------------------------------------------------------------------
# _load_ratio_color
# ------------------------------------------------------------------


class TestLoadRatioColor:
    def test_green_when_low(self):
        theme = Theme()
        c = _load_ratio_color(0.5, theme)
        assert c == theme.q_color("success")

    def test_green_at_boundary(self):
        c = _load_ratio_color(0.8, None)
        assert isinstance(c, QColor)

    def test_amber_above_80(self):
        theme = Theme()
        c = _load_ratio_color(0.9, theme)
        assert c == theme.q_color("warning")

    def test_red_over_100(self):
        theme = Theme()
        c = _load_ratio_color(1.5, theme)
        assert c == theme.q_color("error")

    def test_fallback_no_theme(self):
        c = _load_ratio_color(0.5, None)
        assert c == QColor("#a6e3a1")

    def test_fallback_warning_no_theme(self):
        c = _load_ratio_color(0.9, None)
        assert c == QColor("#f9e2af")

    def test_fallback_error_no_theme(self):
        c = _load_ratio_color(1.5, None)
        assert c == QColor("#f38ba8")


# ------------------------------------------------------------------
# _tasks_in_week
# ------------------------------------------------------------------


class TestTasksInWeek:
    def test_matching(self):
        t = _make_task(assignee="Alice", start=datetime.date(2026, 1, 5),
                       due=datetime.date(2026, 1, 9))
        result = _tasks_in_week([t], "Alice", "2026-W02")
        assert result == [t]

    def test_wrong_assignee(self):
        t = _make_task(assignee="Alice")
        assert _tasks_in_week([t], "Bob", "2026-W02") == []

    def test_outside_week(self):
        t = _make_task(start=datetime.date(2026, 1, 5),
                       due=datetime.date(2026, 1, 9))
        assert _tasks_in_week([t], "Alice", "2026-W10") == []

    def test_none_dates_skipped(self):
        t = _make_task()
        t.start = None
        assert _tasks_in_week([t], "Alice", "2026-W02") == []


# ------------------------------------------------------------------
# ResourceView data + grid
# ------------------------------------------------------------------


class TestResourceViewData:
    def test_empty_data(self, rv):
        rv.setData({})
        assert rv.row_count == 0
        assert rv.column_count == 0

    def test_single_assignee(self, rv):
        rv.setData({"Alice": {"2026-W02": 20.0}})
        assert rv.row_count == 1
        assert rv.column_count == 1

    def test_multiple_assignees_and_weeks(self, rv):
        rv.setData({
            "Alice": {"2026-W02": 20.0, "2026-W03": 30.0},
            "Bob": {"2026-W02": 40.0},
        })
        assert rv.row_count == 2
        assert rv.column_count == 2

    def test_cell_text(self, rv):
        rv.setData({"Alice": {"2026-W02": 20.0}})
        item = rv._table.item(0, 0)
        assert item is not None
        assert item.text() == "20.0"

    def test_cell_data_metadata(self, rv):
        rv.setData({"Alice": {"2026-W02": 32.0}})
        md = rv.cell_data(0, 0)
        assert md is not None
        assert md["assignee"] == "Alice"
        assert md["week"] == "2026-W02"
        assert md["hours"] == 32.0
        assert md["capacity"] == 40.0
        assert md["ratio"] == pytest.approx(0.8)

    def test_cell_color_green(self, rv):
        rv.setData({"Alice": {"2026-W02": 20.0}})
        c = rv.cell_color(0, 0)
        assert c is not None
        # Without a theme parent we get the fallback green
        assert c == QColor("#a6e3a1")

    def test_cell_color_overallocated(self, rv):
        rv.setData({"Alice": {"2026-W02": 50.0}})
        c = rv.cell_color(0, 0)
        assert c == QColor("#f38ba8")

    def test_custom_capacity(self, rv):
        rv.setData({"Alice": {"2026-W02": 20.0}}, default_capacity=20.0)
        md = rv.cell_data(0, 0)
        assert md is not None
        assert md["ratio"] == pytest.approx(1.0)

    def test_people_capacity(self, rv):
        person = SimpleNamespace(name="Alice", weekly_capacity=20.0)
        rv.setData({"Alice": {"2026-W02": 20.0}}, people=[person])
        md = rv.cell_data(0, 0)
        assert md is not None
        assert md["capacity"] == 20.0
        assert md["ratio"] == pytest.approx(1.0)


# ------------------------------------------------------------------
# setTasks / setContext
# ------------------------------------------------------------------


class TestResourceViewTasks:
    def test_setTasks(self, rv):
        tasks = [_make_task()]
        rv.setTasks(tasks)
        assert len(rv._tasks) == 1

    def test_setContext(self, rv):
        rv.setContext(sheet="s", col_map={"a": 0}, first_col=1, on_set=lambda: None)
        assert rv._sheet == "s"
        assert rv._first_col == 1


# ------------------------------------------------------------------
# Reassignment logic
# ------------------------------------------------------------------


class TestReassignment:
    def test_do_reassign_updates_task(self, rv):
        task = _make_task(tid="T1", assignee="Alice")
        rv.setData({"Alice": {"2026-W02": 10}, "Bob": {"2026-W02": 5}})
        rv.setTasks([task])

        signals: list[tuple[str, str, str]] = []
        rv.taskReassigned.connect(lambda *a: signals.append(a))

        # No sheet context => skip write_task, just emit signal
        rv._do_reassign(task, "Alice", "Bob")

        assert task.assignee == "Bob"
        assert len(signals) == 1
        assert signals[0] == ("T1", "Alice", "Bob")

    def test_reassign_emits_signal(self, rv):
        task = _make_task(tid="T5", assignee="X")
        rv.setData({"X": {"2026-W01": 10}, "Y": {"2026-W01": 5}})

        received = []
        rv.taskReassigned.connect(lambda tid, old, new: received.append((tid, old, new)))
        rv._do_reassign(task, "X", "Y")
        assert received == [("T5", "X", "Y")]


# ------------------------------------------------------------------
# cell_color / cell_data edge cases
# ------------------------------------------------------------------


class TestEdgeCases:
    def test_cell_color_out_of_range(self, rv):
        rv.setData({})
        assert rv.cell_color(99, 99) is None

    def test_cell_data_out_of_range(self, rv):
        rv.setData({})
        assert rv.cell_data(99, 99) is None

    def test_rebuild_clears_previous(self, rv):
        rv.setData({"Alice": {"2026-W02": 10.0}})
        assert rv.row_count == 1
        rv.setData({"A": {"W1": 1}, "B": {"W1": 2}, "C": {"W1": 3}})
        assert rv.row_count == 3


# ------------------------------------------------------------------
# Integration with MainWindow theme
# ------------------------------------------------------------------


class TestWithMainWindow:
    def test_child_gets_theme_colors(self, win, app):
        rv = ResourceView(win)
        rv.setData({"Alice": {"2026-W02": 20.0}})
        c = rv.cell_color(0, 0)
        assert c is not None
        # Should use the theme's success colour, not fallback
        theme = getattr(win, "_theme", None)
        if theme is not None:
            assert c == theme.q_color("success")
        rv.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
