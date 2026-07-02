"""Antenna Modeler dialog + Radio-menu wiring (offscreen)."""

from __future__ import annotations

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


def _menu_labels(win, title):
    bar = win.menuBar()
    for act in bar.actions():
        if act.text().replace("&", "") == "Tools":
            for sub in act.menu().actions():
                if sub.menu() and sub.menu().title().replace("&", "") == title:
                    return [a.text().replace("&", "") for a in sub.menu().actions()]
    return []


def test_dialog_constructs(win):
    from abax.gui.dialogs.antenna_modeler_dialog import AntennaModelerDialog

    dlg = AntennaModelerDialog(win)
    # A dipole runs on construction and produces a readout + a plotted pattern.
    assert "dBi" in dlg._readout.text()
    assert dlg._plotw._samples


def test_dipole_gain_and_impedance():
    from abax.gui.dialogs.antenna_modeler_dialog import build_geometry, directivity_dbi
    from abax.core.science import wire_mom

    wires, feed = build_geometry("dipole", {"driven": 0.47})
    result = wire_mom.solve(wires, [(0, feed, 1.0)])
    zin = result["feed_impedance"][(0, feed)]
    gain = directivity_dbi(wires, result)
    # A resonant half-wave dipole: ~73 Ω-ish resistive, ~2.15 dBi.
    assert 40.0 < zin.real < 120.0
    assert 1.0 < gain < 3.5


def test_yagi_has_forward_gain_and_fb():
    from abax.gui.dialogs.antenna_modeler_dialog import build_geometry, directivity_dbi
    from abax.core.science import wire_mom

    params = {
        "driven": 0.47, "reflector": 0.5, "director": 0.44,
        "refl_spacing": 0.2, "dir_spacing": 0.15,
    }
    wires, feed = build_geometry("yagi", params)
    result = wire_mom.solve(wires, [(0, feed, 1.0)])
    gain = directivity_dbi(wires, result)
    fb = wire_mom.front_to_back_db(wires, result)
    # A 3-element Yagi beams forward: more gain than a dipole, positive F/B.
    assert gain > 4.0
    assert fb > 3.0


def test_analyze_via_dialog(win):
    from abax.gui.dialogs.antenna_modeler_dialog import AntennaModelerDialog

    dlg = AntennaModelerDialog(win)
    dlg._kind.setCurrentIndex(1)          # Yagi
    res = dlg.analyze()
    assert res["kind"] == "yagi"
    assert res["front_to_back_db"] is not None
    assert res["pattern"]


def test_radio_menu_has_new_entries(win):
    labels = _menu_labels(win, "Radio")
    assert "Antenna modeler..." in labels
    assert "Open logbook (ADIF)..." in labels


def test_palette_has_new_entries(win):
    actions = win._palette_actions()
    assert "Antenna modeler..." in actions
    assert "Open logbook (ADIF)..." in actions
