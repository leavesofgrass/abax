"""Activation-log dialog — live dupe highlighting, running score, sheet write."""

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


def _dialog(win):
    from abax.gui.dialogs.hamlog_dialog import HamLogDialog

    return HamLogDialog(win)


def test_dialog_dupe_detection_and_running_score(win):
    dlg = _dialog(win)
    dlg._ruleset.setCurrentText("fieldday")

    assert dlg.add_qso("W1AW", "20M", "SSB", "1200") is False
    assert dlg.add_qso("w1aw/p", "20M", "USB", "1205") is True   # dupe
    assert dlg.add_qso("K1ABC", "40M", "CW", "1210") is False
    dlg._rescore()

    result = dlg.score()
    assert result.qso_count == 2          # dupe not counted
    assert result.dupe_count == 1
    # Field Day: SSB 1 + CW 2 = 3 (the dupe SSB scores 0).
    assert result.point_total == 3
    assert result.score == 3

    # The dupe row is flagged in the table (status column reads DUPE).
    status = {dlg._table.item(r, 6).text() for r in range(dlg._table.rowCount())}
    assert status == {"OK", "DUPE"}
    assert "Valid QSOs: 2" in dlg._tally.text()
    assert "Score: 3" in dlg._tally.text()


def test_dialog_remove_last(win):
    dlg = _dialog(win)
    dlg.add_qso("W1AW", "20M", "SSB")
    dlg.add_qso("K1ABC", "20M", "SSB")
    dlg._remove_last()
    dlg._rescore()
    assert dlg.score().qso_count == 1


def test_dialog_writes_log_to_sheet(win):
    dlg = _dialog(win)
    dlg._ruleset.setCurrentText("pota")
    dlg.add_qso("W1AW", "20M", "SSB", "1200")
    dlg.add_qso("W1AW", "20M", "SSB", "1201")   # dupe
    dlg.add_qso("K1ABC", "40M", "CW", "1210")

    before = len(win._doc.workbook.sheets)
    dlg._write_sheet()
    wb = win._doc.workbook
    assert len(wb.sheets) == before + 1
    sheet = wb.sheets[-1]

    assert "Activation log" in str(sheet.get_value(0, 0))
    # Header row.
    assert [sheet.get_value(1, c) for c in range(3)] == ["Call", "Band", "Mode"]
    # First QSO row.
    assert sheet.get_value(2, 0) == "W1AW"
    # The dupe row carries the Y flag in the Dupe column (index 5).
    assert sheet.get_value(3, 5) == "Y"
    # A summary block with the score exists somewhere below the log.
    values = [
        str(sheet.get_value(r, 0))
        for r in range(sheet.used_bounds()[0])
    ]
    assert "Score" in values and "Valid QSOs" in values


def test_dialog_ruleset_switch_rescore(win):
    # Switching ruleset re-scores the same contacts under the new schedule.
    dlg = _dialog(win)
    dlg._ruleset.setCurrentText("pota")
    dlg.add_qso("W1AW", "20M", "CW")
    dlg.add_qso("K1ABC", "40M", "CW")
    assert dlg.score().point_total == 2          # POTA: 1 pt each
    dlg._ruleset.setCurrentText("fieldday")
    dlg._rescore()
    assert dlg.score().point_total == 4          # Field Day: CW = 2 each


def test_dialog_empty_log_starts_at_zero(win):
    # A fresh dialog has an empty model and a zero tally (no modal involved).
    dlg = _dialog(win)
    assert dlg.score().qso_count == 0
    assert dlg._table.rowCount() == 0
    assert "Valid QSOs: 0" in dlg._tally.text()
