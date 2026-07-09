"""Offscreen tests for the formula dependency-trace dialog."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6", reason="Qt binding required for GUI dialog tests")

from abax.core.workbook import Workbook
from abax.gui._qtcompat import QApplication
from abax.gui.dialogs.deptrace_dialog import DepTraceDialog


class _TableStub:
    def currentRow(self) -> int:  # noqa: N802 (Qt-style API)
        return 0

    def currentColumn(self) -> int:  # noqa: N802 (Qt-style API)
        return 0


class _DocStub:
    def __init__(self, workbook: Workbook) -> None:
        self.workbook = workbook


class _WindowStub:
    """Minimal stand-in exposing the window API the dialog reads."""

    def __init__(self, workbook: Workbook) -> None:
        self._doc = _DocStub(workbook)
        self._table = _TableStub()


def _make_workbook() -> Workbook:
    wb = Workbook()
    sheet = wb.sheet
    sheet.set_cell(0, 0, "=B1+C1")  # A1
    sheet.set_cell(0, 1, "5")        # B1
    sheet.set_cell(0, 2, "=B1*2")    # C1
    return wb


def _dialog() -> DepTraceDialog:
    _ = QApplication.instance() or QApplication([])
    win = _WindowStub(_make_workbook())
    return DepTraceDialog(win)


def test_construction_does_not_raise() -> None:
    dialog = _dialog()
    assert dialog is not None


def test_precedents_include_inputs() -> None:
    dialog = _dialog()
    text = dialog.trace_text("Precedents", 8)
    assert "B1" in text
    assert "C1" in text


def test_dependents_direction_runs() -> None:
    dialog = _dialog()
    text = dialog.trace_text("Dependents", 8)
    # A1 (the current cell) has no dependents in this workbook.
    assert "A1" in text
    assert "no dependents" in text


def test_refresh_sets_view_text() -> None:
    dialog = _dialog()
    dialog.refresh()
    assert dialog._view.toPlainText().strip() != ""
