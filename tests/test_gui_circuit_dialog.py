"""Circuit calculator dialog — computations, graphs, and accessibility."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, QLineEdit, Qt  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    _win = MainWindow(Settings())
    yield _win
    from abax.gui._qtcompat import QEvent as _QEvent
    _win.deleteLater()
    app.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    app.processEvents()


def test_pure_computations_match_pool_answers():
    from abax.gui.dialogs import circuit_dialog as cd

    ohm = dict(cd.compute_ohms({"voltage": "100", "current": "", "resistance": "50",
                                "power": ""}))
    assert ohm["Current (I)"] == "2 A" and ohm["Power (P)"] == "200 W"
    tau = cd.compute_time_constant({"kind": "RC", "r": "500k", "part": "440u",
                                    "direction": "charge"})
    assert tau["tau"] == pytest.approx(220.0)                        # E5B04
    assert "63.2% at 1τ" in tau["description"]                       # E5B01
    res = cd.compute_resonance({"topology": "series", "r": "10", "l": "50u", "c": "40p"})
    assert res["info"]["f0"] == pytest.approx(3.559e6, rel=1e-3)      # E5A02
    assert "3.559 MHz" in res["description"]
    rows = dict(cd.compute_impedance({"freq": "14M", "r": "400", "l": "", "c": "38p",
                                      "topology": "series"}))       # E5C10
    assert rows["Impedance Z (rectangular)"].startswith("400 − j299.2")
    assert "voltage lags current" in rows["Phase angle"]


def test_dialog_builds_and_charts_are_accessible(win):
    from abax.gui.dialogs.circuit_dialog import CircuitDialog

    dlg = CircuitDialog(win)
    for tab in (dlg._tau_tab, dlg._res_tab):
        plot = tab.plot
        assert plot.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert plot.accessibleName().endswith("chart")
        # the description is the same text as the visible summary, and non-empty
        assert plot.accessibleDescription()
        assert plot.accessibleDescription() == tab.summary.text()
        assert tab.table.rowCount() > 0 and tab.table.accessibleName()
    # every text field is labelled for assistive technology
    for le in dlg.findChildren(QLineEdit):
        assert le.accessibleName(), le.text()
    dlg.close()


def test_description_updates_when_values_change(win):
    from abax.gui.dialogs.circuit_dialog import CircuitDialog

    dlg = CircuitDialog(win)
    before = dlg._res_tab.plot.accessibleDescription()
    dlg._res_c.setText("10p")                                         # E5A10: 7.12 MHz
    dlg.compute_resonance()
    after = dlg._res_tab.plot.accessibleDescription()
    assert after != before and "7.118 MHz" in after
    dlg._res_c.setText("bogus")
    dlg.compute_resonance()
    assert "Could not compute" in dlg._res_tab.results.toPlainText()
    dlg.close()


def test_ohms_tab_and_data_to_sheet(win):
    from abax.gui.dialogs.circuit_dialog import CircuitDialog

    dlg = CircuitDialog(win)
    dlg.compute_ohms()
    assert "Current (I)" in dlg._ohm_out.toPlainText()
    dlg._ohm["current"].setText("1")                                  # three values given
    dlg.compute_ohms()
    assert "Could not solve" in dlg._ohm_out.toPlainText()
    n_before = len(win._doc.workbook.sheets)
    dlg._tau_tab.to_sheet.click()
    wb = win._doc.workbook
    assert len(wb.sheets) == n_before + 1
    new = wb.sheets[-1]
    assert new.get("A1") == "Time constants"
    assert new.get("C3") == pytest.approx(63.21, abs=0.01)             # 1τ row
    dlg.close()


def test_charts_render(win, tmp_path):
    from abax.gui.dialogs.circuit_dialog import CircuitDialog

    dlg = CircuitDialog(win)
    dlg.resize(900, 560)
    for i, tab in enumerate((dlg._tau_tab, dlg._res_tab)):
        dlg.tabs.setCurrentWidget(tab)
        dlg.show()
        QApplication.processEvents()
        img = tab.plot.grab()
        assert not img.isNull() and img.width() > 100
        out = os.environ.get("ABAX_SNAPSHOT_DIR")
        if out:
            img.save(os.path.join(out, f"circuit_{i}.png"))
    dlg.close()


def test_menu_wiring(win):
    assert callable(win.show_circuit_calculator)
