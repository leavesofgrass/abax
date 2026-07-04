"""Antenna Modeler dialog: the Ground option (free space / perfect ground /
height) drives the elevation cut through the image model and labels the plot
accordingly. Offscreen; the free-space path is unchanged.
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


# --- UI-free helpers --------------------------------------------------------

def test_ground_from_choice_maps_correctly():
    from abax.gui.dialogs.antenna_modeler_dialog import (
        GROUND_CHOICES,
        ground_from_choice,
    )

    g, h = ground_from_choice(GROUND_CHOICES[0])
    assert g is None and h == 0.0
    g, h = ground_from_choice(GROUND_CHOICES[1])
    assert g is not None and g.kind == "perfect" and h == 0.0
    g, h = ground_from_choice(GROUND_CHOICES[2], 0.75)
    assert g is not None and g.kind == "perfect" and h == pytest.approx(0.75)


def test_raise_to_height_offsets_z():
    from abax.gui.dialogs.antenna_modeler_dialog import raise_to_height

    wires = [[(0.0, 0.0, -0.25), (0.0, 0.0, 0.25)]]
    out = raise_to_height(wires, 0.5)
    assert out[0][0] == (0.0, 0.0, 0.25)
    assert out[0][1] == (0.0, 0.0, 0.75)
    # zero height is a no-op (identity list).
    assert raise_to_height(wires, 0.0) is wires


def test_pattern_cut_ground_free_space_defers():
    from abax.gui.dialogs.antenna_modeler_dialog import (
        GROUND_CHOICES,
        pattern_cut,
        pattern_cut_ground,
    )

    a = pattern_cut_ground("dipole", {"driven": 0.5}, GROUND_CHOICES[0],
                           plane="elevation", count=91)
    b = pattern_cut("dipole", {"driven": 0.5}, plane="elevation", count=91)
    assert a == b


def test_pattern_cut_ground_elevation_is_over_ground():
    from abax.gui.dialogs.antenna_modeler_dialog import (
        GROUND_CHOICES,
        pattern_cut_ground,
    )

    samples, source = pattern_cut_ground(
        "dipole", {"driven": 0.5}, GROUND_CHOICES[2], height=0.5,
        plane="elevation", count=361, decibels=False)
    assert source == "mom-ground"
    by_deg = {round(math.degrees(a)): v for a, v in samples}
    # Over ground the field below the horizon is zero.
    assert by_deg[135] < 1e-9
    assert by_deg[225] < 1e-9


# --- dialog wiring ----------------------------------------------------------

def test_dialog_has_ground_combobox(win):
    from abax.gui.dialogs.antenna_modeler_dialog import (
        GROUND_CHOICES,
        AntennaModelerDialog,
    )

    dlg = AntennaModelerDialog(win)
    assert dlg._ground.count() == len(GROUND_CHOICES)
    # Default is free space; the height field is only enabled for "+ height".
    assert dlg._ground.currentText() == GROUND_CHOICES[0]
    assert not dlg._height.isEnabled()


def test_dialog_height_field_toggles(win):
    from abax.gui.dialogs.antenna_modeler_dialog import (
        AntennaModelerDialog,
    )

    dlg = AntennaModelerDialog(win)
    dlg._ground.setCurrentIndex(1)                       # perfect ground
    assert not dlg._height.isEnabled()
    dlg._ground.setCurrentIndex(2)                       # perfect ground + height
    assert dlg._height.isEnabled()


def test_dialog_free_space_title_and_source(win):
    from abax.gui.dialogs.antenna_modeler_dialog import (
        FREE_SPACE,
        AntennaModelerDialog,
    )

    dlg = AntennaModelerDialog(win)
    dlg._plane.setCurrentIndex(1)                        # elevation
    samples, source = dlg.compute_pattern(count=91)
    assert source in ("mom", "pynec")
    assert FREE_SPACE in dlg._pattern_title()


def test_dialog_over_ground_title_and_pattern(win):
    from abax.gui.dialogs.antenna_modeler_dialog import (
        OVER_GROUND,
        AntennaModelerDialog,
    )

    dlg = AntennaModelerDialog(win)
    dlg._plane.setCurrentIndex(1)                        # elevation
    dlg._ground.setCurrentIndex(1)                       # perfect ground
    samples, source = dlg.compute_pattern(count=181)
    assert source == "mom-ground"
    title = dlg._pattern_title()
    assert OVER_GROUND in title or "over ground" in title
    # The readout carries the over-ground caveat, not the free-space one.
    assert "take-off" in dlg._readout.text()


def test_dialog_over_ground_height_in_title(win):
    from abax.gui.dialogs.antenna_modeler_dialog import AntennaModelerDialog

    dlg = AntennaModelerDialog(win)
    dlg._plane.setCurrentIndex(1)
    dlg._ground.setCurrentIndex(2)                       # + height
    dlg._height.setText("0.5")
    dlg.compute_pattern(count=91)
    assert "h=0.5" in dlg._pattern_title()


def test_dialog_ground_vertical_dipole_confines_to_upper_hemisphere(win):
    from abax.gui.dialogs.antenna_modeler_dialog import AntennaModelerDialog

    dlg = AntennaModelerDialog(win)
    dlg._plane.setCurrentIndex(1)
    dlg._ground.setCurrentIndex(1)                       # perfect ground
    samples, _src = dlg.compute_pattern(count=361)
    by_deg = {round(math.degrees(a)): v for a, v in samples}
    # dB-mapped: below-horizon samples clamp to the floor (0.0).
    assert by_deg[135] == pytest.approx(0.0, abs=1e-9)
