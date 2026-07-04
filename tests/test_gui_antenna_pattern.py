"""Antenna Modeler radiation-pattern read-back (offscreen).

Minimal GUI coverage: the module-level pattern_cut helper prefers a solver and
returns free-space samples; the dialog's compute_pattern stores them; and the
sheet writer emits a labelled ``(free space)`` block through the checkpoint path.
"""

from __future__ import annotations

import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication  # noqa: E402
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


def test_module_pattern_cut_dipole_azimuth():
    from abax.gui.dialogs.antenna_modeler_dialog import pattern_cut

    samples, source = pattern_cut("dipole", {"driven": 0.47}, plane="azimuth",
                                  count=73, decibels=True)
    assert source in ("mom", "pynec")
    assert len(samples) == 73
    # Azimuth cut of a z-dipole is omnidirectional -> flat at the peak.
    vals = [v for _a, v in samples]
    assert max(vals) == pytest.approx(1.0, abs=1e-6)
    assert max(vals) - min(vals) < 1e-3


def test_module_pattern_cut_yagi_has_forward_lobe():
    from abax.gui.dialogs.antenna_modeler_dialog import pattern_cut

    params = {
        "driven": 0.47, "reflector": 0.5, "director": 0.44,
        "refl_spacing": 0.2, "dir_spacing": 0.15,
    }
    samples, _source = pattern_cut("yagi", params, plane="azimuth",
                                   count=361, decibels=False)
    by_deg = {round(math.degrees(a)): v for a, v in samples}
    assert by_deg[0] == pytest.approx(1.0, abs=1e-6)   # beams toward +x
    assert by_deg[0] > by_deg[180]                     # forward lobe


def test_dialog_compute_pattern_stores_samples(win):
    from abax.gui.dialogs.antenna_modeler_dialog import AntennaModelerDialog

    dlg = AntennaModelerDialog(win)
    samples, source = dlg.compute_pattern(count=91)
    assert samples
    assert dlg._pattern == samples          # cached on the dialog
    assert dlg._pattern_source == source


def test_dialog_plot_pattern_updates_widget_and_readout(win):
    from abax.gui.dialogs.antenna_modeler_dialog import AntennaModelerDialog

    dlg = AntennaModelerDialog(win)
    dlg._plane.setCurrentIndex(1)           # Elevation
    dlg._plot_pattern()
    assert dlg._plotw._samples               # plotted into the polar viewer
    assert "free space" in dlg._readout.text().lower()


def test_dialog_pattern_to_sheet_writes_free_space_block(win, monkeypatch):
    from abax.gui._qtcompat import QMessageBox
    from abax.gui.dialogs import antenna_modeler_dialog as mod
    from abax.gui.dialogs.antenna_modeler_dialog import AntennaModelerDialog

    # Auto-confirm the "write to sheet?" prompt.
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    dlg = AntennaModelerDialog(win)
    dlg.compute_pattern(count=37)
    before = len(win._doc.workbook.sheets)
    dlg._pattern_to_sheet()
    wb = win._doc.workbook
    assert len(wb.sheets) == before + 1
    sheet = wb.sheets[-1]
    # Row 0 carries the free-space title; row 1 the headers.
    assert mod.FREE_SPACE in str(sheet.get_value(0, 0))
    assert str(sheet.get_value(1, 0)) == "Angle (deg)"
    # A data row exists (37 samples -> row 2 is the first sample at 0 deg).
    assert str(sheet.get_value(2, 0)) == "0.0"
