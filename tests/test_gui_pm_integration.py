"""Integration tests for the PM layer — menu, view host, project setup dialog."""

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


class TestProjectMenu:
    def test_project_menu_exists(self, win):
        menus = [a.text().replace("&", "") for a in win.menuBar().actions()]
        assert "Project" in menus

    def test_project_menu_position(self, win):
        menus = [a.text().replace("&", "") for a in win.menuBar().actions()]
        sheet_idx = menus.index("Sheet")
        proj_idx = menus.index("Project")
        tools_idx = menus.index("Tools")
        assert sheet_idx < proj_idx < tools_idx

    def test_project_menu_has_actions(self, win):
        for menu_action in win.menuBar().actions():
            if menu_action.text().replace("&", "") == "Project":
                menu = menu_action.menu()
                actions = [a.text().replace("&", "") for a in menu.actions() if a.text()]
                assert "New project from sheet..." in actions
                assert "Open project views..." in actions
                assert "Kanban board" in actions
                assert "Gantt chart" in actions
                assert "Dashboard" in actions
                assert "Roadmap" in actions
                assert "Export report..." in actions
                return
        pytest.fail("Project menu not found")


class TestPalette:
    def test_pm_entries_in_palette(self, win):
        actions = win._palette_actions()
        assert "Project: new from sheet..." in actions
        assert "Project: Kanban board" in actions
        assert "Project: Gantt chart" in actions
        assert "Project: Timeline" in actions
        assert "Project: Dashboard" in actions
        assert "Project: Roadmap" in actions
        assert "Project: export report..." in actions


class TestViewHost:
    def test_view_host_creation(self, win):
        win._pm_ensure_host()
        assert hasattr(win, "_pm_host")
        assert win._pm_host is not None

    def test_view_host_tabs(self, win):
        win._pm_ensure_host()
        host = win._pm_host
        assert host._tabs.count() == 7
        labels = [host._tabs.tabText(i) for i in range(host._tabs.count())]
        assert labels == ["Kanban", "Card", "Calendar", "Gantt", "Timeline",
                          "Dashboard", "Roadmap"]

    def test_view_host_reload_empty(self, win):
        win._pm_ensure_host()
        host = win._pm_host
        host.reload_projects()
        assert host._project_combo.count() == 0

    def test_view_host_with_project(self, win):
        wb = win._doc.workbook
        sheet = wb.sheet
        sheet.set_cell(0, 0, "Title")
        sheet.set_cell(0, 1, "Status")
        sheet.set_cell(0, 2, "Due")
        sheet.set_cell(1, 0, "Task A")
        sheet.set_cell(1, 1, "To Do")
        sheet.set_cell(1, 2, "2026-08-01")
        proj = Project(name="Test", sheet=sheet.name, last_col=2)
        wb.projects.add(proj)

        win._pm_ensure_host()
        host = win._pm_host
        host.reload_projects()
        assert host._project_combo.count() == 1
        assert host._project is not None
        assert host._project.name == "Test"

        wb.projects.remove("Test")


class TestProjectSetupDialog:
    def test_dialog_creation(self, win):
        from abax.gui.pm.project_setup_dialog import ProjectSetupDialog

        dlg = ProjectSetupDialog(win, win._doc.workbook)
        assert dlg is not None
        assert dlg.windowTitle() == "New project from sheet"
        dlg.deleteLater()

    def test_dialog_edit_mode(self, win):
        from abax.gui.pm.project_setup_dialog import ProjectSetupDialog

        proj = Project(name="EditMe", sheet=win._doc.workbook.sheet.name)
        dlg = ProjectSetupDialog(win, win._doc.workbook, project=proj)
        assert dlg.windowTitle() == "Edit project"
        assert dlg._name_edit.text() == "EditMe"
        dlg.deleteLater()

    def test_column_detection_preview(self, win):
        from abax.gui.pm.project_setup_dialog import ProjectSetupDialog

        wb = win._doc.workbook
        sheet = wb.sheet
        sheet.set_cell(0, 0, "Title")
        sheet.set_cell(0, 1, "Status")
        sheet.set_cell(0, 2, "Due")

        dlg = ProjectSetupDialog(win, wb)
        preview = dlg._preview_label.text()
        assert "title" in preview.lower() or "due" in preview.lower()
        dlg.deleteLater()
