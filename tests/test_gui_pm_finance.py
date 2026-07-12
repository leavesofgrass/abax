"""Tests for PM GUI widgets: FinanceView, OkrView, PmScenarioDialog."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

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


# ---- minimal stand-in types for testing ----------------------------------

@dataclass
class _Task:
    row: int
    name: str = ""
    task_id: str = ""
    start: date | None = None
    due: date | None = None
    tags: list[str] = field(default_factory=list)


# =====================================================================
# FinanceView
# =====================================================================

class TestFinanceView:
    def test_create(self, app):
        from abax.gui.pm.finance_view import FinanceView

        w = FinanceView()
        assert w is not None
        w.deleteLater()

    def test_set_data_basic(self, app):
        from abax.gui.pm.finance_view import FinanceView

        w = FinanceView()
        bd = {
            "total_budget": 10000,
            "total_cost": 7000,
            "remaining": 3000,
            "per_project": [
                {"name": "Alpha", "budget": 5000, "cost": 3000,
                 "remaining": 2000, "pct_used": 60},
                {"name": "Beta", "budget": 5000, "cost": 6000,
                 "remaining": -1000, "pct_used": 120},
            ],
        }
        ed = {"PV": 8000.0, "EV": 7000.0, "AC": 7500.0,
              "SPI": 0.875, "CPI": 0.933, "EAC": 10714.29}
        w.setData(bd, ed)

        # Check tiles got values
        assert w._tiles["PV"]._value.text() == "8,000.00"
        assert w._tiles["SPI"]._value.text() == "0.88"
        w.deleteLater()

    def test_forecast_under_budget(self, app):
        from abax.gui.pm.finance_view import FinanceView

        w = FinanceView()
        bd = {"total_budget": 10000, "per_project": []}
        ed = {"PV": 0, "EV": 0, "AC": 0, "SPI": 1, "CPI": 1, "EAC": 9000.0}
        w.setData(bd, ed)
        assert "UNDER" in w._forecast.text()
        w.deleteLater()

    def test_forecast_over_budget(self, app):
        from abax.gui.pm.finance_view import FinanceView

        w = FinanceView()
        bd = {"total_budget": 10000, "per_project": []}
        ed = {"PV": 0, "EV": 0, "AC": 0, "SPI": 1, "CPI": 1, "EAC": 12000.0}
        w.setData(bd, ed)
        assert "OVER" in w._forecast.text()
        w.deleteLater()

    def test_forecast_on_budget(self, app):
        from abax.gui.pm.finance_view import FinanceView

        w = FinanceView()
        bd = {"total_budget": 10000, "per_project": []}
        ed = {"PV": 0, "EV": 0, "AC": 0, "SPI": 1, "CPI": 1, "EAC": 10000.0}
        w.setData(bd, ed)
        assert "ON" in w._forecast.text()
        w.deleteLater()

    def test_bars_green_when_under(self, app):
        from abax.gui.pm.finance_view import FinanceView

        w = FinanceView()
        bd = {
            "total_budget": 5000, "per_project": [
                {"name": "X", "budget": 5000, "cost": 2000,
                 "remaining": 3000, "pct_used": 40},
            ],
        }
        ed = {"PV": 0, "EV": 0, "AC": 0, "SPI": 1, "CPI": 1, "EAC": 5000.0}
        w.setData(bd, ed)
        assert len(w._bar_widgets) == 1
        w.deleteLater()

    def test_evm_missing_values(self, app):
        from abax.gui.pm.finance_view import FinanceView

        w = FinanceView()
        bd = {"total_budget": 0, "per_project": []}
        ed = {"PV": None, "EV": None, "AC": None,
              "SPI": None, "CPI": None, "EAC": None}
        w.setData(bd, ed)
        assert w._tiles["PV"]._value.text() == "--"
        assert "insufficient" in w._forecast.text().lower()
        w.deleteLater()


# =====================================================================
# OkrView
# =====================================================================

class TestOkrView:
    def test_create(self, app):
        from abax.gui.pm.okr_view import OkrView

        w = OkrView()
        assert w._table.rowCount() == 0
        w.deleteLater()

    def test_populate_objectives(self, app):
        from abax.gui.pm.okr_view import KeyResult, Objective, OkrView

        objs = [
            Objective(
                objective="Increase Revenue",
                key_results=[
                    KeyResult(name="ARR", target=100, current_formula="75"),
                    KeyResult(name="MRR", target=50, current_formula="50"),
                ],
            ),
        ]
        w = OkrView()
        w.setObjectives(objs, [])
        # 1 objective row + 2 KR rows
        assert w._table.rowCount() == 3
        w.deleteLater()

    def test_objective_aggregate_progress(self, app):
        from abax.gui.pm.okr_view import KeyResult, Objective, OkrView

        objs = [
            Objective(
                objective="Test",
                key_results=[
                    KeyResult(name="K1", target=100, current_formula="100"),
                    KeyResult(name="K2", target=100, current_formula="0"),
                ],
            ),
        ]
        w = OkrView()
        w.setObjectives(objs, [])
        bar = w._table.cellWidget(0, 3)
        assert bar is not None
        assert bar.value() == 50  # average of 100% and 0%
        w.deleteLater()

    def test_kr_non_numeric_formula(self, app):
        from abax.gui.pm.okr_view import KeyResult, Objective, OkrView

        objs = [
            Objective(
                objective="O1",
                key_results=[
                    KeyResult(name="K1", target=100,
                              current_formula="=SUM(A1:A5)"),
                ],
            ),
        ]
        w = OkrView()
        w.setObjectives(objs, [])
        # KR row is row 1; current column should show the formula text
        item = w._table.item(1, 2)
        assert item is not None
        assert item.text() == "=SUM(A1:A5)"
        w.deleteLater()

    def test_linked_task_count(self, app):
        from abax.gui.pm.okr_view import KeyResult, Objective, OkrView

        objs = [
            Objective(
                objective="Ship MVP",
                key_results=[
                    KeyResult(name="K1", target=1, current_formula="0"),
                ],
            ),
        ]
        tasks = [
            _Task(row=1, name="T1", tags=["okr:ship_mvp"]),
            _Task(row=2, name="T2", tags=["okr:ship_mvp"]),
            _Task(row=3, name="T3", tags=["other"]),
        ]
        w = OkrView()
        w.setObjectives(objs, tasks)
        task_item = w._table.item(0, 4)
        assert task_item is not None
        assert task_item.text() == "2"
        w.deleteLater()

    def test_empty_objectives(self, app):
        from abax.gui.pm.okr_view import OkrView

        w = OkrView()
        w.setObjectives([], [])
        assert w._table.rowCount() == 0
        w.deleteLater()


# =====================================================================
# PmScenarioDialog
# =====================================================================

class TestPmScenarioDialog:
    def test_create_empty(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        tasks = [_Task(row=1, name="A", task_id="A")]
        dlg = PmScenarioDialog(None, tasks)
        assert dlg.result_scenario() is None
        assert dlg.result_apply() is False
        dlg.deleteLater()

    def test_create_with_scenarios(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import (
            PmScenario,
            PmScenarioDialog,
        )

        tasks = [_Task(row=1, name="A", task_id="A")]
        sc = PmScenario(name="Best case", overrides={"A": {"cost": "500"}})
        dlg = PmScenarioDialog(None, tasks, scenarios=[sc])
        assert dlg._scenario_list.count() == 1
        assert dlg.result_scenario() is not None
        assert dlg.result_scenario().name == "Best case"
        dlg.deleteLater()

    def test_add_scenario(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        tasks = [_Task(row=1, name="A", task_id="A")]
        dlg = PmScenarioDialog(None, tasks)
        dlg._on_add_scenario()
        assert dlg._scenario_list.count() == 1
        assert dlg.result_scenario() is not None
        dlg.deleteLater()

    def test_remove_scenario(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import (
            PmScenario,
            PmScenarioDialog,
        )

        tasks = [_Task(row=1, name="A", task_id="A")]
        sc = PmScenario(name="X")
        dlg = PmScenarioDialog(None, tasks, scenarios=[sc])
        dlg._scenario_list.setCurrentRow(0)
        dlg._on_remove_scenario()
        assert dlg._scenario_list.count() == 0
        dlg.deleteLater()

    def test_add_override(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        tasks = [_Task(row=1, name="A", task_id="A")]
        dlg = PmScenarioDialog(None, tasks)
        dlg._on_add_scenario()
        dlg._task_combo.setCurrentIndex(0)
        dlg._field_combo.setCurrentText("cost")
        dlg._new_value_edit.setText("999")
        dlg._on_add_override()
        assert dlg._override_table.rowCount() == 1
        sc = dlg.result_scenario()
        assert sc is not None
        assert "A" in sc.overrides
        assert sc.overrides["A"]["cost"] == "999"
        dlg.deleteLater()

    def test_remove_override(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        tasks = [_Task(row=1, name="A", task_id="A")]
        dlg = PmScenarioDialog(None, tasks)
        dlg._on_add_scenario()
        dlg._task_combo.setCurrentIndex(0)
        dlg._field_combo.setCurrentText("cost")
        dlg._new_value_edit.setText("123")
        dlg._on_add_override()
        dlg._override_table.setCurrentCell(0, 0)
        dlg._on_remove_override()
        assert dlg._override_table.rowCount() == 0
        dlg.deleteLater()

    def test_set_delta(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        tasks = [_Task(row=1, name="A", task_id="A")]
        dlg = PmScenarioDialog(None, tasks)
        dlg.setDelta({"finish_date": "2026-08-01 -> 2026-09-01",
                       "cost": "$5000 -> $7000"})
        text = dlg._delta_display.toPlainText()
        assert "finish_date" in text
        assert "cost" in text
        dlg.deleteLater()

    def test_apply_sets_flag(self, app):
        from abax.gui.dialogs.pm_scenario_dialog import PmScenarioDialog

        tasks = [_Task(row=1, name="A", task_id="A")]
        dlg = PmScenarioDialog(None, tasks)
        dlg._on_add_scenario()
        # Simulate "Apply to Sheet"
        dlg._apply = True
        assert dlg.result_apply() is True
        dlg.deleteLater()
