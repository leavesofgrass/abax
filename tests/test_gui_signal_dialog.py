"""Signal tool — the Welch PSD operation (real one-sided + I/Q two-sided)."""

from __future__ import annotations

import math
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


def _set_op(dlg, prefix: str) -> None:
    for i in range(dlg._op.count()):
        if dlg._op.itemText(i).startswith(prefix):
            dlg._op.setCurrentIndex(i)
            return
    raise AssertionError(f"no operation starting with {prefix!r}")


def test_welch_psd_real_writes_two_columns(win):
    from qcell.gui.dialogs.signal_dialog import SignalDialog

    sheet = win._doc.workbook.sheet
    sr, f, n = 256.0, 40.0, 512
    for i in range(n):
        sheet.set_cell(i, 0, str(math.sin(2 * math.pi * f * i / sr)))

    dlg = SignalDialog(win)
    dlg._in.setText("A1:A512")
    dlg._param.setText("256")          # sample rate
    dlg._out.setText("C1")
    _set_op(dlg, "Welch PSD")
    dlg._apply()

    assert "real one-sided" in win.statusBar().currentMessage()
    # freq column starts at 0 Hz; the PSD peak sits on the tone's bin
    assert sheet.get_value(0, 2) == 0
    freqs, psd = [], []
    r = 0
    while True:
        fv = sheet.get_value(r, 2)
        pv = sheet.get_value(r, 3)
        if not isinstance(fv, (int, float)):
            break
        freqs.append(float(fv))
        psd.append(float(pv))
        r += 1
    assert len(freqs) == 256 // 2 + 1
    peak = max(range(len(psd)), key=lambda k: psd[k])
    assert abs(freqs[peak] - f) <= sr / 256


def test_welch_psd_iq_two_column_selection(win):
    from qcell.gui.dialogs.signal_dialog import SignalDialog

    sheet = win._doc.workbook.sheet
    sr, f, n = 1000.0, 125.0, 512
    for i in range(n):
        ph = 2 * math.pi * f * i / sr
        sheet.set_cell(i, 0, str(math.cos(ph)))   # I
        sheet.set_cell(i, 1, str(math.sin(ph)))   # Q

    dlg = SignalDialog(win)
    dlg._in.setText("A1:B512")          # two columns -> quadrature
    dlg._param.setText("1000")
    dlg._out.setText("E1")
    _set_op(dlg, "Welch PSD")
    dlg._apply()

    assert "I/Q two-sided" in win.statusBar().currentMessage()
    # two-sided spectrum spans negative through positive frequencies
    first = sheet.get_value(0, 4)
    assert isinstance(first, (int, float)) and first < 0
