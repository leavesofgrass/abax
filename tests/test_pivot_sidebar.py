"""Headless test of the PivotTable Fields sidebar (drag-drop dock).

Drives the dock through its programmatic API (add_to / current_spec / build /
do_insert) rather than synthesizing real drag events, so the Qt shell is
exercised end-to-end against the pure build_pivot logic and the live sheet.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from abax.gui._qtcompat import QApplication  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _window_with_data():
    from abax.gui.main_window import MainWindow
    from abax.settings import Settings

    win = MainWindow(Settings(), state=None)
    sheet = win._doc.workbook.sheet
    rows = [
        ["region", "quarter", "sales"],
        ["West", "Q1", "10"],
        ["West", "Q2", "20"],
        ["East", "Q1", "5"],
    ]
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            sheet.set_cell(r, c, val)
    return win


def test_sidebar_builds_and_inserts():
    _app()
    win = _window_with_data()
    from abax.gui.dialogs.pivot_sidebar import PivotSidebar

    dock = PivotSidebar(win)
    dock._range.setText("A1:C4")
    dock.reload_fields()
    assert dock._source.count() == 3  # region, quarter, sales

    dock.add_to("rows", "region")
    dock.add_to("columns", "quarter")
    dock.add_to("values", "sales", "sum")

    spec = dock.current_spec()
    assert spec.row_fields == ["region"]
    assert spec.column_field == "quarter"
    assert spec.value_fields == ["sales"]

    out = dock.build()
    assert out is not None
    assert out[0] == ["region", "Q1", "Q2"]
    body = {r[0]: r for r in out[1:]}
    assert body["West"] == ["West", "10", "20"]
    assert body["East"] == ["East", "5", ""]

    dock._out.setText("A10")
    dock.do_insert()
    sheet = win._doc.workbook.sheet
    assert str(sheet.get_value(9, 0)) == "region"
    assert str(sheet.get_value(10, 0)) == "East"  # sorted first


def test_sidebar_values_agg_and_remove():
    _app()
    win = _window_with_data()
    from abax.gui.dialogs.pivot_sidebar import PivotSidebar

    dock = PivotSidebar(win)
    dock._range.setText("A1:C4")
    dock.reload_fields()
    dock.add_to("rows", "region")
    dock.add_to("values", "sales", "max")
    out = dock.build()
    assert out[0] == ["region", "max(sales)"]
    body = {r[0]: r[1] for r in out[1:]}
    assert body["West"] == "20"

    # Remove the values field → build now reports the missing-values error.
    dock._areas["values"].setCurrentRow(0)
    dock._areas["values"].takeItem(0)
    dock._on_changed()
    assert dock.build() is None
    assert "Values" in dock._status.text()


def test_sidebar_menu_toggle_creates_dock():
    _app()
    win = _window_with_data()
    win.show_pivot_sidebar()
    assert getattr(win, "_pivot_sidebar", None) is not None
    # Idempotent — a second call reuses the same dock.
    first = win._pivot_sidebar
    win.show_pivot_sidebar()
    assert win._pivot_sidebar is first
