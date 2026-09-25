"""Every Radio-menu dialog exposes a name for every control, and every
custom-painted chart is reachable by keyboard and described in words.

The name checked is the one Qt's accessibility layer reports — what a screen
reader announces — so a form field named by its buddy label passes, while a
field with only placeholder text fails (placeholders are not reliably
announced). Widgets internal to a combo box or spin box are named through
their parent and are skipped.
"""

from __future__ import annotations

import importlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QAccessible, QApplication, Qt, QWidget  # noqa: E402
from abax.settings import Settings  # noqa: E402

DIALOGS = [
    ("rf_dialog", "RFDialog"),
    ("smith_dialog", "SmithDialog"),
    ("circuit_dialog", "CircuitDialog"),
    ("exposure_dialog", "ExposureDialog"),
    ("antenna_dialog", "AntennaDialog"),
    ("antenna_modeler_dialog", "AntennaModelerDialog"),
    ("rf_reference_dialog", "RfReferenceDialog"),
    ("hamlog_dialog", "HamLogDialog"),
    ("satellite_dialog", "SatelliteDialog"),
]


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


def _internal(w, dlg) -> bool:
    p = w.parent()
    while p is not None and p is not dlg:
        if p.inherits("QComboBox") or p.inherits("QAbstractSpinBox"):
            return True
        p = p.parent()
    return False


@pytest.mark.parametrize("module, cls", DIALOGS, ids=[c for _, c in DIALOGS])
def test_radio_dialog_is_accessible(win, module, cls):
    dlg = getattr(importlib.import_module(f"abax.gui.dialogs.{module}"), cls)(win)
    unnamed = []
    for w in dlg.findChildren(QWidget):
        if w.focusPolicy() == Qt.FocusPolicy.NoFocus or not w.isEnabled() or _internal(w, dlg):
            continue
        iface = QAccessible.queryAccessibleInterface(w)
        if not (iface and (iface.text(QAccessible.Text.Name) or "").strip()):
            unnamed.append(type(w).__name__)
    assert not unnamed, f"{cls}: controls with no accessible name: {unnamed}"

    # custom-painted abax canvases (charts) must be focusable and described
    for w in dlg.findChildren(QWidget):
        if type(w).__module__.startswith("abax") and type(w).paintEvent is not QWidget.paintEvent:
            assert w.focusPolicy() != Qt.FocusPolicy.NoFocus, f"{cls}: {type(w).__name__}"
            assert w.accessibleName(), f"{cls}: {type(w).__name__} has no name"
            assert w.accessibleDescription(), f"{cls}: {type(w).__name__} not described"
    dlg.deleteLater()
