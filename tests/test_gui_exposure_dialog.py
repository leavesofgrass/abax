"""RF exposure dialog — evaluation chain, graph, and accessibility."""

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


def _raw(**over):
    raw = {"freq_mhz": "28.4", "power_w": "1500", "loss_db": "0", "gain_dbi": "8",
           "duty_pct": "100", "tx_pct": "100", "reflection": 4.0, "distance_m": "10"}
    raw.update(over)
    return raw


def test_compute_exposure_matches_core():
    from abax.core.science import rf_exposure as X
    from abax.gui.dialogs.exposure_dialog import compute_exposure

    res = compute_exposure(_raw())
    ev = res["eval"]
    eirp = 1500 * 10 ** 0.8
    assert ev["eirp_w"] == pytest.approx(eirp)
    assert ev["compliance_m"]["uncontrolled"] == pytest.approx(
        X.compliance_distance(eirp, 28.4, "uncontrolled", 4.0))
    # 1500 W into 8 dBi at 10 m with full reflection exceeds the uncontrolled
    # limit (compliance distance > 10 m); both tiers' rows state it in words
    assert ev["compliance_m"]["uncontrolled"] > 10
    at_rows = [v for k, v in res["rows"] if k.startswith("  At 10.00 m")]
    assert len(at_rows) == 2 and "ABOVE the limit" in at_rows[1]   # uncontrolled row
    assert "Estimate only" in res["description"]
    # the compliance distances appear in the data table
    ds = [row[0] for row in res["table"]]
    for t in X.TIERS:
        assert ev["compliance_m"][t] in ds


def test_low_power_is_below_limits_and_exempt():
    from abax.gui.dialogs.exposure_dialog import compute_exposure

    res = compute_exposure(_raw(freq_mhz="146", power_w="5", gain_dbi="2.15",
                                reflection=1.0, distance_m="10"))
    assert all(p < 100 for p in res["eval"]["percent"].values())
    assert res["eval"]["exempt"] is True
    assert "exempt from routine evaluation" in dict(res["rows"])["§ 1.1307 exemption"]


def test_dialog_accessibility_and_errors(win):
    from abax.gui.dialogs.exposure_dialog import DISCLAIMER, ExposureDialog

    dlg = ExposureDialog(win)
    plot = dlg.panel.plot
    assert plot.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert plot.accessibleDescription() == dlg.panel.summary.text()
    assert "mW/cm²" in plot.accessibleDescription()
    for le in dlg.findChildren(QLineEdit):
        assert le.accessibleName(), le.text()
    assert any(DISCLAIMER == lbl.text() for lbl in dlg.findChildren(type(dlg.panel.summary)))
    # custom reflection factor is only editable when "Custom" is chosen
    assert not dlg.custom.isEnabled()
    dlg.refl.setCurrentIndex(2)
    assert dlg.custom.isEnabled()
    dlg.custom.setText("2.5")
    dlg.compute()
    assert dlg.reflection() == 2.5
    before = plot.accessibleDescription()
    dlg.power.setText("50")
    dlg.compute()
    assert plot.accessibleDescription() != before
    dlg.f.setText("0.1375")                      # 2200 m: below the FCC table
    dlg.compute()
    assert "Could not compute" in dlg.panel.results.toPlainText()
    dlg.close()


def test_render_and_to_sheet(win):
    from abax.gui.dialogs.exposure_dialog import ExposureDialog

    dlg = ExposureDialog(win)
    dlg.show()
    QApplication.processEvents()
    img = dlg.panel.plot.grab()
    assert not img.isNull()
    out = os.environ.get("ABAX_SNAPSHOT_DIR")
    if out:
        img.save(os.path.join(out, "exposure.png"))
    n = len(win._doc.workbook.sheets)
    dlg.panel.to_sheet.click()
    assert len(win._doc.workbook.sheets) == n + 1
    assert win._doc.workbook.sheets[-1].get("A1") == "Distance (m)"
    dlg.close()


def test_menu_wiring(win):
    assert callable(win.show_rf_exposure)
