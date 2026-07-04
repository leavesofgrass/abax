"""Satellite pass predictor dialog (offscreen).

Construction and the pure-GUI plumbing run without ``sgp4`` (thin CI); the
end-to-end predict -> write-to-sheet path is guarded with
``pytest.importorskip("sgp4")``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

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


def test_dialog_constructs(win):
    from abax.gui.dialogs.satellite_dialog import SatelliteDialog

    dlg = SatelliteDialog(win)
    # Prefilled with a sample ISS TLE and sensible observer defaults.
    assert "1 25544" in dlg._tle.toPlainText()
    assert dlg._table.columnCount() == 9
    # No results yet, so "to sheet" is disabled.
    assert not dlg._to_sheet.isEnabled()


def test_bad_start_time_warns_not_crashes(win, monkeypatch):
    from abax.gui.dialogs import satellite_dialog
    from abax.gui.dialogs.satellite_dialog import SatelliteDialog

    dlg = SatelliteDialog(win)
    dlg._start.setText("not-a-time")
    warned = {}
    monkeypatch.setattr(
        satellite_dialog.QMessageBox,
        "warning",
        lambda *a, **k: warned.setdefault("hit", True),
    )
    dlg.predict()
    assert warned.get("hit")


def test_predict_and_write_to_sheet(win, monkeypatch):
    pytest.importorskip("sgp4")

    from abax.gui.dialogs.satellite_dialog import SatelliteDialog

    dlg = SatelliteDialog(win)
    # Observer near NYC; predict a day near the sample TLE's epoch.
    dlg._lat.setValue(40.7128)
    dlg._lon.setValue(-74.0060)
    dlg._alt.setValue(10.0)
    dlg._start.setText(
        datetime(2024, 6, 21, 0, 0, 0, tzinfo=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )
    dlg._hours.setValue(24.0)
    dlg._min_el.setValue(10.0)

    dlg.predict()
    assert dlg._passes, "expected some ISS passes near epoch"
    assert dlg._table.rowCount() == len(dlg._passes)
    assert dlg._to_sheet.isEnabled()

    before = len(win._doc.workbook.sheets)
    dlg._passes_to_sheet()
    wb = win._doc.workbook
    assert len(wb.sheets) == before + 1
    sheet = wb.sheets[wb.active]
    assert sheet.name.startswith("Passes")
    # Header row written.
    assert sheet.get_value(0, 0) == "Satellite"
