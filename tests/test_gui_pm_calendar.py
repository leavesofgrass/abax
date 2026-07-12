"""Tests for the PM calendar view."""

from __future__ import annotations

import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.core.pm.taskmodel import Task  # noqa: E402
from abax.gui._qtcompat import QApplication, QEvent  # noqa: E402
from abax.gui.pm.calendar_view import CalendarView  # noqa: E402
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
    return [
        Task(row=1, title="Fix bug", due=date(2026, 7, 15)),
        Task(row=2, title="Write docs", due=date(2026, 7, 15)),
        Task(row=3, title="Release v1", due=date(2026, 7, 20), milestone=True),
        Task(
            row=4,
            title="Sprint",
            start=date(2026, 7, 6),
            due=date(2026, 7, 10),
        ),
        Task(row=5, title="Review PR", due=date(2026, 7, 1)),
    ]


class TestCalendarView:
    def test_creation(self, win):
        cal = CalendarView(parent=win)
        assert cal is not None
        assert cal.currentMonth() == date.today().month
        assert cal.currentYear() == date.today().year

    def test_set_tasks_and_date(self, win):
        cal = CalendarView(parent=win)
        tasks = _sample_tasks()
        cal.setTasks(tasks)
        cal.setDate(2026, 7)

        assert cal.currentYear() == 2026
        assert cal.currentMonth() == 7

        due_15 = cal.tasks_on_date(date(2026, 7, 15))
        assert len(due_15) == 2
        titles = {t.title for t in due_15}
        assert "Fix bug" in titles
        assert "Write docs" in titles

    def test_tasks_on_specific_date(self, win):
        cal = CalendarView(parent=win)
        cal.setTasks(_sample_tasks())
        cal.setDate(2026, 7)

        assert len(cal.tasks_on_date(date(2026, 7, 20))) == 1
        assert cal.tasks_on_date(date(2026, 7, 20))[0].title == "Release v1"
        assert len(cal.tasks_on_date(date(2026, 7, 25))) == 0

    def test_milestone_tracked(self, win):
        cal = CalendarView(parent=win)
        cal.setTasks(_sample_tasks())
        cal.setDate(2026, 7)

        milestones = [t for t in cal.tasks_on_date(date(2026, 7, 20)) if t.milestone]
        assert len(milestones) == 1
        assert milestones[0].title == "Release v1"

    def test_month_navigation(self, win):
        cal = CalendarView(parent=win)
        cal.setDate(2026, 7)
        assert cal.currentMonth() == 7

        cal.setDate(2026, 8)
        assert cal.currentMonth() == 8
        assert cal.currentYear() == 2026

        cal.setDate(2026, 1)
        assert cal.currentMonth() == 1

    def test_month_navigation_year_wrap(self, win):
        cal = CalendarView(parent=win)
        cal.setDate(2026, 12)
        cal._go_next()
        assert cal.currentYear() == 2027
        assert cal.currentMonth() == 1

        cal.setDate(2026, 1)
        cal._go_prev()
        assert cal.currentYear() == 2025
        assert cal.currentMonth() == 12

    def test_set_context(self, win):
        cal = CalendarView(parent=win)
        callback = lambda s, r, c, v: None  # noqa: E731
        cal.setContext(
            sheet="mock_sheet",
            col_map={"due": 4},
            first_col=0,
            on_set=callback,
        )
        assert cal._sheet == "mock_sheet"
        assert cal._col_map == {"due": 4}
        assert cal._first_col == 0
        assert cal._on_set is callback

    def test_set_context_individual(self, win):
        cal = CalendarView(parent=win)
        cal.setSheet("sheet2")
        cal.setColMap({"title": 0})
        cal.setFirstCol(2)
        cb = lambda: None  # noqa: E731
        cal.setOnSet(cb)
        assert cal._sheet == "sheet2"
        assert cal._col_map == {"title": 0}
        assert cal._first_col == 2
        assert cal._on_set is cb

    def test_signal_exists(self, win):
        cal = CalendarView(parent=win)
        assert hasattr(cal, "taskSelected")
        assert hasattr(cal, "newTaskRequested")

    def test_day_cells_created_for_month(self, win):
        cal = CalendarView(parent=win)
        cal.setDate(2026, 7)
        assert len(cal._day_cells) > 0
        # July 2026 has days from Mon 29 Jun to Sun 2 Aug (5 weeks)
        # or 6 weeks depending on calendar
        assert len(cal._day_cells) % 7 == 0

    def test_day_cells_contain_tasks(self, win):
        cal = CalendarView(parent=win)
        cal.setTasks(_sample_tasks())
        cal.setDate(2026, 7)

        cells_with_tasks = [c for c in cal._day_cells if c.tasks]
        assert len(cells_with_tasks) > 0

        # Find the cell for July 15
        cell_15 = [
            c for c in cal._day_cells
            if c.day_date == date(2026, 7, 15)
        ]
        assert len(cell_15) == 1
        assert len(cell_15[0].tasks) == 2

    def test_span_highlight(self, win):
        cal = CalendarView(parent=win)
        cal.setTasks(_sample_tasks())
        cal.setDate(2026, 7)

        # Task 4 spans July 6-10; cells in that range should be highlighted
        for day in range(6, 11):
            cells = [
                c for c in cal._day_cells
                if c.day_date == date(2026, 7, day)
            ]
            assert len(cells) == 1
            assert cells[0]._span_highlight, f"Day {day} should be span-highlighted"

    def test_refresh(self, win):
        cal = CalendarView(parent=win)
        cal.setTasks(_sample_tasks())
        cal.setDate(2026, 7)
        old_count = len(cal._day_cells)
        cal.refresh()
        assert len(cal._day_cells) == old_count

    def test_drop_reschedules_task(self, win):
        cal = CalendarView(parent=win)
        tasks = _sample_tasks()
        on_set_calls: list[tuple] = []

        def mock_on_set(sheet, row, col, value):
            on_set_calls.append((row, col, value))

        cal.setTasks(tasks)
        cal.setDate(2026, 7)
        cal.setContext(
            sheet=None,
            col_map={"due": 4},
            first_col=0,
            on_set=mock_on_set,
        )

        # Simulate a drop: task row 1 moved to July 22
        cal._on_task_dropped(1, date(2026, 7, 22))

        # The task's due date should be updated
        task1 = cal._find_task_by_row(1)
        assert task1 is not None
        assert task1.due == date(2026, 7, 22)

        # on_set callback should have been called
        assert len(on_set_calls) == 1
        assert on_set_calls[0] == (1, 4, "2026-07-22")

    def test_accessible_names(self, win):
        cal = CalendarView(parent=win)
        cal.setDate(2026, 7)
        assert cal.accessibleName() == "Calendar view"

        for cell in cal._day_cells:
            name = cell.accessibleName()
            assert name, "Every day cell must have an accessible name"
            if cell.day_date is not None:
                assert cell.day_date.isoformat() in name
