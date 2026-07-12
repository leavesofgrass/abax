"""Tests for the PM Kanban and Card/Gallery views."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.core.pm.taskmodel import STATUS_ORDER  # noqa: E402
from abax.core.sheet import Sheet  # noqa: E402
from abax.gui._qtcompat import QApplication  # noqa: E402
from abax.gui.pm.common import (  # noqa: E402
    TASK_MIME_TYPE,
    TaskViewModel,
    write_field,
)
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="session")
def app():
    _app = QApplication.instance() or QApplication([])
    yield _app


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    _win = MainWindow(Settings())
    yield _win
    from abax.gui._qtcompat import QEvent as _QEvent

    _win.deleteLater()
    app.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    app.processEvents()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HEADERS = ["Title", "Status", "Due", "Assignee", "Priority", "%Done", "ID"]
_ROWS = [
    ["Design UI", "Todo", "2026-08-01", "Alice", "High", "0", "T1"],
    ["Write tests", "In Progress", "2026-07-15", "Bob", "Medium", "50", "T2"],
    ["Deploy", "Todo", "2026-09-01", "Alice", "Low", "0", "T3"],
    ["Review PR", "Done", "2026-07-10", "Carol", "High", "100", "T4"],
]


def _make_sheet() -> Sheet:
    """Build a Sheet with task headers and sample data."""
    sheet = Sheet("Tasks")
    for c, h in enumerate(_HEADERS):
        sheet.set_cell(0, c, h)
    for r, row_data in enumerate(_ROWS, start=1):
        for c, val in enumerate(row_data):
            sheet.set_cell(r, c, str(val))
    return sheet


# ---------------------------------------------------------------------------
# TestTaskViewModel
# ---------------------------------------------------------------------------


class TestTaskViewModel:
    def test_parse_tasks(self):
        sheet = _make_sheet()
        model = TaskViewModel(sheet)
        assert len(model.tasks) == len(_ROWS)
        assert model.tasks[0].title == "Design UI"
        assert model.tasks[1].status == "In Progress"
        assert model.col_map["title"] == 0
        assert model.col_map["status"] == 1

    def test_refresh_picks_up_changes(self):
        sheet = _make_sheet()
        model = TaskViewModel(sheet)
        assert model.tasks[0].title == "Design UI"
        sheet.set_cell(1, 0, "Updated Title")
        model.refresh()
        assert model.tasks[0].title == "Updated Title"

    def test_empty_sheet(self):
        sheet = Sheet("Empty")
        model = TaskViewModel(sheet)
        assert model.tasks == []


# ---------------------------------------------------------------------------
# TestWriteField
# ---------------------------------------------------------------------------


class TestWriteField:
    def test_calls_on_set_callback(self):
        sheet = _make_sheet()
        callback = MagicMock()
        model = TaskViewModel(sheet, on_set=callback)
        task = model.tasks[0]

        write_field(model, task, "status", "Done")

        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] is sheet
        assert args[1] == task.row
        # Column 1 is status (first_col=0 + col_map["status"]=1).
        assert args[2] == 1
        assert args[3] == "Done"

    def test_write_field_without_callback(self):
        sheet = _make_sheet()
        model = TaskViewModel(sheet)
        task = model.tasks[0]
        write_field(model, task, "status", "Done")
        # After refresh, the task should have the new status.
        refreshed = [t for t in model.tasks if t.id == task.id]
        assert refreshed
        assert refreshed[0].status == "Done"


# ---------------------------------------------------------------------------
# TestKanbanView
# ---------------------------------------------------------------------------


class TestKanbanView:
    def test_columns_match_status_order(self, app):
        from abax.gui.pm.kanban_view import KanbanView

        sheet = _make_sheet()
        model = TaskViewModel(sheet)
        view = KanbanView()
        view.setModel(model)

        statuses = STATUS_ORDER(model.tasks)
        col_statuses = [c.status for c in view.columns()]
        assert col_statuses == statuses

    def test_card_count_per_column(self, app):
        from abax.gui.pm.kanban_view import KanbanView

        sheet = _make_sheet()
        model = TaskViewModel(sheet)
        view = KanbanView()
        view.setModel(model)

        columns = view.columns()
        counts = {c.status: len(c.cards) for c in columns}
        assert counts["Todo"] == 2
        assert counts["In Progress"] == 1
        assert counts["Done"] == 1

    def test_write_field_and_refresh(self, app):
        from abax.gui.pm.kanban_view import KanbanView

        sheet = _make_sheet()
        model = TaskViewModel(sheet)
        view = KanbanView()
        view.setModel(model)

        task = model.tasks[0]
        assert task.status == "Todo"
        write_field(model, task, "status", "Done")
        view.refresh()

        columns = view.columns()
        counts = {c.status: len(c.cards) for c in columns}
        assert counts["Todo"] == 1
        assert counts["Done"] == 2

    def test_task_selected_signal(self, app):
        from abax.gui.pm.kanban_view import KanbanView

        sheet = _make_sheet()
        model = TaskViewModel(sheet)
        view = KanbanView()
        view.setModel(model)

        received = []
        view.taskSelected.connect(received.append)

        columns = view.columns()
        if columns and columns[0].cards:
            columns[0].cards[0].doubleClicked.emit(
                columns[0].cards[0].task.row,
            )
        assert len(received) == 1
        assert received[0] == model.tasks[0].row


# ---------------------------------------------------------------------------
# TestCardView
# ---------------------------------------------------------------------------


class TestCardView:
    def test_cards_present(self, app):
        from abax.gui.pm.card_view import CardView

        sheet = _make_sheet()
        model = TaskViewModel(sheet)
        view = CardView()
        view.setModel(model)

        assert len(view.card_widgets()) == len(_ROWS)

    def test_gallery_toggle(self, app):
        from abax.gui.pm.card_view import CardView

        sheet = _make_sheet()
        model = TaskViewModel(sheet)
        view = CardView()
        view.setModel(model)

        assert not view.gallery
        view.gallery = True
        assert view.gallery
        # Gallery cards are larger.
        if view.card_widgets():
            cw = view.card_widgets()[0]
            assert cw.width() > 220

    def test_task_selected_signal(self, app):
        from abax.gui.pm.card_view import CardView

        sheet = _make_sheet()
        model = TaskViewModel(sheet)
        view = CardView()
        view.setModel(model)

        received = []
        view.taskSelected.connect(received.append)

        cws = view.card_widgets()
        if cws:
            cws[0].doubleClicked.emit(cws[0].task.row)
        assert len(received) == 1


# ---------------------------------------------------------------------------
# MIME type constant
# ---------------------------------------------------------------------------


class TestMimeType:
    def test_mime_type_string(self):
        assert TASK_MIME_TYPE == "application/x-abax-pm-task"
