"""Tests for the GUI wiring of three PM engine features:

1. **Project > Schedule (CPM)…** — computes the critical path and pushes it to
   the Gantt / Roadmap views via ``setCritical``.
2. **Live scenario delta** — the scenario editor recomputes ``scenario_delta``
   whenever an override changes.
3. **Scenario persistence** — scenarios round-trip on the ``Project`` object.
"""

from __future__ import annotations

import json
import os
from datetime import date

import pytest

from abax.core.pm.projects import Project, ProjectRegistry, Scenario
from abax.core.pm.taskmodel import Task

# ---------------------------------------------------------------------------
# Pure (no Qt) — scenario persistence on the Project object
# ---------------------------------------------------------------------------


class TestScenarioPersistence:
    def test_scenario_roundtrip(self):
        sc = Scenario(name="Crash", overrides={"T1": {"cost": "200", "due": "2026-08-01"}})
        d = sc.to_dict()
        sc2 = Scenario.from_dict(d)
        assert sc2.name == "Crash"
        assert sc2.overrides == {"T1": {"cost": "200", "due": "2026-08-01"}}

    def test_scenario_defaults(self):
        sc = Scenario.from_dict({"name": "Empty"})
        assert sc.name == "Empty"
        assert sc.overrides == {}

    def test_project_carries_scenarios(self):
        proj = Project(
            name="Alpha",
            sheet="Tasks",
            scenarios=[
                Scenario(name="s1", overrides={"T2": {"effort": "40"}}),
                Scenario(name="s2", overrides={}),
            ],
        )
        d = proj.to_dict()
        assert "scenarios" in d
        p2 = Project.from_dict(d)
        assert [s.name for s in p2.scenarios] == ["s1", "s2"]
        assert p2.scenarios[0].overrides == {"T2": {"effort": "40"}}

    def test_no_scenarios_omitted_from_dict(self):
        proj = Project(name="Bare", sheet="Tasks")
        assert "scenarios" not in proj.to_dict()

    def test_registry_json_roundtrip(self):
        reg = ProjectRegistry()
        reg.add(Project(
            name="P",
            sheet="Tasks",
            scenarios=[Scenario(name="what-if", overrides={"T1": {"status": "Done"}})],
        ))
        blob = json.dumps(reg.to_dict())
        reg2 = ProjectRegistry.from_dict(json.loads(blob))
        proj = reg2.get("P")
        assert proj is not None
        assert proj.scenarios[0].name == "what-if"
        assert proj.scenarios[0].overrides == {"T1": {"status": "Done"}}


# ---------------------------------------------------------------------------
# Qt-backed tests (offscreen)
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


def _setup_dependent_project(win) -> Project:
    """A → B (long) and A → C (short); critical path is A, B."""
    wb = win._doc.workbook
    sheet = wb.sheet
    sheet.set_cell(0, 0, "Title")
    sheet.set_cell(0, 1, "Status")
    sheet.set_cell(0, 2, "Effort")
    sheet.set_cell(0, 3, "Depends")
    sheet.set_cell(1, 0, "A")
    sheet.set_cell(1, 2, "8")
    sheet.set_cell(2, 0, "B")
    sheet.set_cell(2, 2, "40")
    sheet.set_cell(2, 3, "T1")
    sheet.set_cell(3, 0, "C")
    sheet.set_cell(3, 2, "8")
    sheet.set_cell(3, 3, "T1")
    proj = Project(name="Sched", sheet=sheet.name, last_col=3)
    wb.projects.add(proj)
    return proj


# -- Feature 1: Schedule (CPM) menu entry -----------------------------------


class TestScheduleMenu:
    def test_menu_has_schedule_entry(self, win):
        for menu_action in win.menuBar().actions():
            if menu_action.text().replace("&", "") == "Project":
                actions = [
                    a.text().replace("&", "")
                    for a in menu_action.menu().actions()
                    if a.text()
                ]
                assert "Schedule (CPM)..." in actions
                return
        pytest.fail("Project menu not found")

    def test_palette_has_schedule_entry(self, win):
        assert "Project: Schedule (CPM)..." in win._palette_actions()

    def test_schedule_pushes_critical_to_gantt(self, win):
        _setup_dependent_project(win)
        win._pm_ensure_host()
        win._pm_host.reload_projects()

        win.pm_schedule()

        assert win._pm_host._critical_ids == {"T1", "T2"}
        gantt = win._pm_host._views.get("gantt")
        assert gantt is not None
        assert gantt._critical_ids == {"T1", "T2"}

        win._doc.workbook.projects.remove("Sched")

    def test_set_critical_reaches_live_view(self, win):
        _setup_dependent_project(win)
        win._pm_ensure_host()
        win._pm_host.reload_projects()
        # Materialize the gantt view first, then push critical ids.
        win._pm_show_view("gantt")
        win._pm_host.set_critical({"T1", "T2"})

        gantt = win._pm_host._views.get("gantt")
        assert gantt is not None
        assert gantt._critical_ids == {"T1", "T2"}

        win._doc.workbook.projects.remove("Sched")

    def test_schedule_reports_cycle(self, win):
        wb = win._doc.workbook
        sheet = wb.sheet
        sheet.set_cell(0, 0, "Title")
        sheet.set_cell(0, 1, "Depends")
        sheet.set_cell(1, 0, "X")
        sheet.set_cell(1, 1, "T2")
        sheet.set_cell(2, 0, "Y")
        sheet.set_cell(2, 1, "T1")
        proj = Project(name="Cyc", sheet=sheet.name, last_col=1)
        wb.projects.add(proj)
        win._pm_ensure_host()
        win._pm_host.reload_projects()

        # Should not raise — the cycle is reported via the status bar.
        win.pm_schedule()

        wb.projects.remove("Cyc")


# -- Feature 2 & 3: scenario dialog delta + persistence ---------------------


def _scenario_tasks() -> list[Task]:
    return [
        Task(row=1, title="A", effort=8.0, cost=100.0,
             start=date(2026, 7, 1), due=date(2026, 7, 5)),
        Task(row=2, title="B", effort=40.0, cost=500.0,
             start=date(2026, 7, 6), due=date(2026, 7, 20), depends=["T1"]),
    ]


class TestScenarioDelta:
    def test_initial_delta_shows_project(self, win):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        proj = Project(name="Alpha", sheet="Tasks")
        dlg = PmScenarioDialog(win, _scenario_tasks(), project=proj)
        # A starter scenario with no overrides still renders a zero delta.
        text = dlg._delta_display.toPlainText()
        assert "Alpha" in text
        assert "Cost" in text
        dlg.deleteLater()

    def test_adding_cost_override_updates_delta(self, win):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        proj = Project(name="Alpha", sheet="Tasks")
        dlg = PmScenarioDialog(win, _scenario_tasks(), project=proj)

        dlg._task_combo.setCurrentIndex(0)  # task T1
        dlg._field_combo.setCurrentText("cost")
        dlg._new_value_edit.setText("300")
        dlg._on_add_override()

        text = dlg._delta_display.toPlainText()
        # Cost 100 → 300 across the project (500 + 100 → 500 + 300).
        assert "+200.00" in text
        dlg.deleteLater()

    def test_setdelta_formats_scenario_delta(self, win):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        dlg = PmScenarioDialog(win, _scenario_tasks())
        dlg.setDelta({
            "projects": [{
                "name": "Beta",
                "old_finish": date(2026, 7, 20),
                "new_finish": date(2026, 7, 25),
                "finish_delta_days": 5,
                "old_cost": 600.0,
                "new_cost": 800.0,
                "cost_delta": 200.0,
            }],
        })
        text = dlg._delta_display.toPlainText()
        assert "Beta" in text
        assert "+5 days" in text
        assert "+200.00" in text
        dlg.deleteLater()


class TestScenarioDialogPersistenceApi:
    def test_result_scenarios_returns_edits(self, win):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenario, PmScenarioDialog

        proj = Project(name="Alpha", sheet="Tasks")
        dlg = PmScenarioDialog(win, _scenario_tasks(), project=proj)
        dlg._task_combo.setCurrentIndex(0)
        dlg._field_combo.setCurrentText("status")
        dlg._new_value_edit.setText("Blocked")
        dlg._on_add_override()

        scenarios = dlg.result_scenarios()
        assert len(scenarios) >= 1
        assert isinstance(scenarios[0], PmScenario)
        assert scenarios[0].overrides["T1"]["status"] == "Blocked"
        dlg.deleteLater()

    def test_existing_scenarios_reload(self, win):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenario, PmScenarioDialog

        existing = [PmScenario(name="Kept", overrides={"T2": {"effort": "60"}})]
        dlg = PmScenarioDialog(
            win, _scenario_tasks(), scenarios=existing,
            project=Project(name="Alpha", sheet="Tasks"),
        )
        # The scenario list shows the reloaded scenario, and its override row
        # is populated in the table.
        assert dlg._scenario_list.item(0).text() == "Kept"
        assert dlg._override_table.rowCount() == 1
        assert dlg._override_table.item(0, 0).text() == "T2"
        assert dlg._override_table.item(0, 1).text() == "effort"
        dlg.deleteLater()
