"""Tests for what-if analysis — data tables and scenarios (``abax/core/whatif.py``)
plus a headless smoke test of the GUI dialog (``abax/gui/dialogs/whatif_dialog.py``).
"""

from __future__ import annotations

import os

import pytest

from abax.core import whatif
from abax.core.errors import CellError
from abax.core.sheet import Sheet

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# --- one-variable data table ---------------------------------------------


def test_one_var_table_recovers_doubles_and_restores() -> None:
    sheet = Sheet()
    sheet.set("A1", "5")
    sheet.set("B1", "=A1*2")
    results = whatif.one_var_data_table(sheet, "A1", [1, 2, 3], "B1")
    assert results == [2, 4, 6]
    # The input cell is left exactly as it was (raw text AND value).
    assert sheet.get_raw(0, 0) == "5"
    assert sheet.get_value(0, 1) == 10  # B1 recomputed against the restored A1


def test_one_var_table_reads_string_values() -> None:
    sheet = Sheet()
    sheet.set("A1", "x")
    sheet.set("B1", '=A1&"!"')
    results = whatif.one_var_data_table(sheet, "A1", ["a", "b"], "B1")
    assert results == ["a!", "b!"]
    assert sheet.get_raw(0, 0) == "x"


# --- two-variable data table ---------------------------------------------


def test_two_var_table_over_sum_and_restores() -> None:
    sheet = Sheet()
    sheet.set("A1", "0")  # row input
    sheet.set("B1", "0")  # col input
    sheet.set("C1", "=A1+B1")
    grid = whatif.two_var_data_table(sheet, "A1", [1, 2, 3], "B1", [10, 20], "C1")
    # rows correspond to col_values [10, 20]; columns to row_values [1, 2, 3].
    assert grid == [[11, 12, 13], [21, 22, 23]]
    # Both inputs restored.
    assert sheet.get_raw(0, 0) == "0"
    assert sheet.get_raw(0, 1) == "0"
    assert sheet.get_value(0, 2) == 0


# --- restoration under errors --------------------------------------------


def test_error_value_does_not_break_table_and_restores() -> None:
    # A trial value that makes the formula error (#DIV/0!) must not abort the
    # sweep, and the input is still restored.
    sheet = Sheet()
    sheet.set("A1", "1")
    sheet.set("B1", "=1/A1")
    results = whatif.one_var_data_table(sheet, "A1", [1, 0, 2], "B1")
    assert results[0] == 1
    assert isinstance(results[1], CellError)  # 1/0
    assert results[2] == 0.5
    assert sheet.get_raw(0, 0) == "1"


def test_input_restored_when_exception_propagates(monkeypatch) -> None:
    # If something raises mid-run, the try/finally still restores the input.
    sheet = Sheet()
    sheet.set("A1", "5")
    sheet.set("B1", "=A1*2")
    calls = {"n": 0}
    original = whatif._recalc

    def boom(s):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom mid-run")
        return original(s)

    monkeypatch.setattr(whatif, "_recalc", boom)
    with pytest.raises(RuntimeError):
        whatif.one_var_data_table(sheet, "A1", [1, 2, 3], "B1")
    assert sheet.get_raw(0, 0) == "5"


# --- scenarios ------------------------------------------------------------


def test_scenario_apply_undo_roundtrip() -> None:
    sheet = Sheet()
    sheet.set("A1", "10")
    sheet.set("B1", "20")
    sheet.set("C1", "=A1+B1")
    assert sheet.get_value(0, 2) == 30

    scenario = whatif.Scenario("High", {"A1": "100", "B1": "200"})
    prior = whatif.apply(scenario, sheet)
    assert prior == {"A1": "10", "B1": "20"}
    assert sheet.get_value(0, 2) == 300  # dependents recomputed

    # Undo by re-applying the captured prior values.
    whatif.apply(whatif.Scenario("undo", prior), sheet)
    assert sheet.get_raw(0, 0) == "10"
    assert sheet.get_raw(0, 1) == "20"
    assert sheet.get_value(0, 2) == 30


def test_capture_scenario_snapshots_cells() -> None:
    sheet = Sheet()
    sheet.set("A1", "1")
    sheet.set("A2", "2")
    sheet.set("B1", "=A1*10")
    snap = whatif.capture(sheet, ["A1:A2", "B1"], "snap")
    assert snap.name == "snap"
    assert snap.changes == {"A1": "1", "A2": "2", "B1": "=A1*10"}


def test_scenarioset_to_dict_from_dict_roundtrip() -> None:
    ss = whatif.ScenarioSet()
    ss.add(whatif.Scenario("A", {"A1": "1"}))
    ss.add(whatif.Scenario("B", {"B1": "2", "B2": "3"}))
    assert ss.names() == ["A", "B"]
    assert ss.version == 2

    restored = whatif.ScenarioSet.from_dict(ss.to_dict())
    assert restored.names() == ["A", "B"]
    assert restored.get("B").changes == {"B1": "2", "B2": "3"}

    ss.remove("A")
    assert ss.names() == ["B"]
    assert ss.version == 3  # mutation counter bumped


# --- headless GUI smoke ---------------------------------------------------


@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PySide6")
    from abax.gui._qtcompat import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui._qtcompat import QEvent
    from abax.gui.main_window import MainWindow
    from abax.settings import Settings

    _win = MainWindow(Settings())
    yield _win
    _win.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_whatif_dialog_one_var_writes_and_restores(win) -> None:
    from abax.gui.dialogs.whatif_dialog import WhatIfDialog

    s = win._doc.workbook.sheet
    s.set_cell(0, 0, "5")       # A1
    s.set_cell(0, 1, "=A1*2")   # B1
    dlg = WhatIfDialog(win)
    results = dlg.run_one_var("A1", [1, 2, 3], "B1", "A3")
    assert results == [2, 4, 6]
    # Input cell restored after the sweep.
    assert s.get_raw(0, 0) == "5"
    # Table laid into the grid: inputs in column A, results in column B (from A3).
    assert s.get_value(2, 0) == 1 and s.get_value(2, 1) == 2
    assert s.get_value(4, 0) == 3 and s.get_value(4, 1) == 6


def test_whatif_dialog_scenarios(win) -> None:
    from abax.gui.dialogs.whatif_dialog import WhatIfDialog

    s = win._doc.workbook.sheet
    s.set_cell(0, 0, "10")      # A1
    s.set_cell(0, 2, "=A1+1")   # C1
    dlg = WhatIfDialog(win)
    dlg.add_scenario("Big", {"A1": "999"})
    # ScenarioSet is attached to the workbook so it persists / can serialize.
    assert isinstance(win._doc.workbook.scenarios, whatif.ScenarioSet)
    dlg.apply_scenario("Big")
    assert s.get_value(0, 2) == 1000
    dlg.undo_scenario()
    assert s.get_raw(0, 0) == "10"
    assert s.get_value(0, 2) == 11
