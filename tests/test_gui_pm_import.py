"""Integration test: Project > Import tasks… writes parsed rows into the sheet.

The dialog historically only parsed the file and reported a count; this checks
that imported tasks are appended to the active project's sheet as one undo step.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.core.pm.projects import Project  # noqa: E402
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


def _setup_project(win, *, with_existing: bool = True) -> Project:
    """Create a task sheet (headers + optionally one task) and register it."""
    wb = win._doc.workbook
    sheet = wb.sheet
    headers = ["Title", "Status", "Due", "Assignee"]
    for c, h in enumerate(headers):
        sheet.set_cell(0, c, h)
    last_data_row = 0
    if with_existing:
        sheet.set_cell(1, 0, "Existing task")
        sheet.set_cell(1, 1, "To Do")
        sheet.set_cell(1, 2, "2026-08-01")
        sheet.set_cell(1, 3, "Alice")
        last_data_row = 1
    proj = Project(
        name="Test", sheet=sheet.name,
        header_row=0, first_col=0, last_col=3,
        first_data_row=1, last_data_row=last_data_row,
    )
    wb.projects.add(proj)
    return proj


def _write_csv(tmp_path) -> str:
    csv = tmp_path / "tasks.csv"
    csv.write_text(
        "Title,Status,Due,Assignee\n"
        "Imported A,In Progress,2026-09-01,Bob\n"
        "Imported B,To Do,2026-09-15,Carol\n",
        encoding="utf-8",
    )
    return str(csv)


class TestImportTasksWriteback:
    def test_appends_rows_and_undo_reverts(self, win, tmp_path, monkeypatch):
        proj = _setup_project(win, with_existing=True)
        csv_path = _write_csv(tmp_path)

        from abax.gui import _qtcompat

        monkeypatch.setattr(
            _qtcompat.QFileDialog, "getOpenFileName",
            staticmethod(lambda *a, **k: (csv_path, "CSV files (*.csv)")),
        )

        win.pm_import_tasks()

        sheet = win._doc.workbook.sheet
        # Existing task untouched at row 1; imports appended at rows 2 and 3.
        assert sheet.get_value(1, 0) == "Existing task"
        assert sheet.get_value(2, 0) == "Imported A"
        assert sheet.get_value(2, 1) == "In Progress"
        assert sheet.get_value(2, 3) == "Bob"
        assert sheet.get_value(3, 0) == "Imported B"
        assert sheet.get_value(3, 3) == "Carol"
        # The project's bounded data range grew to cover the new rows.
        assert proj.last_data_row == 3

        # The whole import is a single undo step. (undo restores an envelope
        # snapshot, which may swap in a fresh sheet object — re-fetch it.)
        win._doc.undo()
        sheet = win._doc.workbook.sheet
        assert sheet.get_value(2, 0) in (None, "")
        assert sheet.get_value(3, 0) in (None, "")
        assert sheet.get_value(1, 0) == "Existing task"

        win._doc.workbook.projects.remove("Test")

    def test_import_into_empty_project(self, win, tmp_path, monkeypatch):
        proj = _setup_project(win, with_existing=False)
        csv_path = _write_csv(tmp_path)

        from abax.gui import _qtcompat

        monkeypatch.setattr(
            _qtcompat.QFileDialog, "getOpenFileName",
            staticmethod(lambda *a, **k: (csv_path, "CSV files (*.csv)")),
        )

        win.pm_import_tasks()

        sheet = win._doc.workbook.sheet
        # No existing tasks → imports start at the project's first_data_row (1).
        assert sheet.get_value(1, 0) == "Imported A"
        assert sheet.get_value(2, 0) == "Imported B"
        assert proj.last_data_row == 2

        win._doc.workbook.projects.remove("Test")

    def test_cancel_dialog_writes_nothing(self, win, monkeypatch):
        _setup_project(win, with_existing=True)

        from abax.gui import _qtcompat

        monkeypatch.setattr(
            _qtcompat.QFileDialog, "getOpenFileName",
            staticmethod(lambda *a, **k: ("", "")),
        )

        win.pm_import_tasks()

        sheet = win._doc.workbook.sheet
        assert sheet.get_value(2, 0) in (None, "")

        win._doc.workbook.projects.remove("Test")
