"""Business chart dialog — pure selection->SVG mapping and safe construction."""

from __future__ import annotations

import os
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.core.workbook import Workbook  # noqa: E402
from abax.gui._qtcompat import QApplication, QWidget  # noqa: E402
from abax.gui.dialogs.business_chart_dialog import BusinessChartDialog  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _StubWindow(QWidget):
    """Minimal window: a QWidget (valid QDialog parent) exposing the read API."""

    def __init__(self, workbook, bounds):
        super().__init__()
        self._doc = types.SimpleNamespace(workbook=workbook)
        self._bounds = bounds

    def _selected_bounds(self):
        return self._bounds


def _window(app):
    wb = Workbook()
    sheet = wb.sheet
    # Two columns: labels in col 0, numbers in col 1 (with a non-numeric row).
    for r, (label, value) in enumerate(
        [("A", "10"), ("B", "-3"), ("C", "notanumber"), ("D", "7")]
    ):
        sheet.set_cell(r, 0, label)
        sheet.set_cell(r, 1, value)
    return _StubWindow(wb, (0, 0, 3, 1))


ROWS = [("A", 10.0), ("B", -3.0), ("C", 7.0)]


def test_chart_svg_all_kinds(app):
    dlg = BusinessChartDialog(_window(app))
    for kind in ("Waterfall", "Sunburst", "Treemap", "Sparkline"):
        svg = dlg.chart_svg(kind, ROWS)
        assert svg.startswith("<svg"), kind
        assert "</svg>" in svg, kind


def test_chart_svg_empty_is_placeholder(app):
    dlg = BusinessChartDialog(_window(app))
    svg = dlg.chart_svg("Waterfall", [])
    assert svg.startswith("<svg")


def test_construction_and_read_rows(app):
    dlg = BusinessChartDialog(_window(app))
    # Selection spans two columns: labels from col 0, values from col 1,
    # the non-numeric row is skipped.
    rows = dlg._read_rows()
    assert rows == [("A", 10.0), ("B", -3.0), ("D", 7.0)]
    # Constructing already ran refresh() without raising and produced SVG.
    assert dlg._svg is not None and dlg._svg.startswith("<svg")


def test_single_column_uses_row_index_labels(app):
    wb = Workbook()
    sheet = wb.sheet
    for r, v in enumerate(["5", "6", "7"]):
        sheet.set_cell(r, 3, v)
    win = _StubWindow(wb, (0, 3, 2, 3))  # single column selection
    dlg = BusinessChartDialog(win)
    assert dlg._read_rows() == [("1", 5.0), ("2", 6.0), ("3", 7.0)]
