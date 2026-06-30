"""RF toolkit dialog — mode switching + per-mode computation."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("qcell.gui._qtcompat")

from qcell.gui._qtcompat import QApplication  # noqa: E402
from qcell.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from qcell.gui.main_window import MainWindow

    return MainWindow(Settings())


def test_rf_dialog_each_mode_computes(win):
    from qcell.gui.dialogs.rf_dialog import RFDialog

    dlg = RFDialog(win)

    rows = dict(dlg.compute_rows())                 # default: Link budget
    assert "Free-space path loss" in rows and "Link margin" in rows

    dlg._mode.setCurrentIndex(1)                     # Coax line
    rows = dict(dlg.compute_rows())
    assert any("Z0" in k for k in rows)

    dlg._mode.setCurrentIndex(2)                     # Antenna dimensions
    rows = dict(dlg.compute_rows())
    dipole = next(v for k, v in rows.items() if "dipole" in k)
    assert "m" in dipole and "ft" in dipole          # dual-unit output

    dlg._mode.setCurrentIndex(3)                     # Matching (L-network)
    rows = dict(dlg.compute_rows())
    assert "Loaded Q" in rows
    assert any("Solution 1" in k for k in rows)


def test_rf_dialog_is_wired_into_window(win):
    assert callable(win.show_rf_tool)
    assert "RF toolkit..." in win._palette_actions()
