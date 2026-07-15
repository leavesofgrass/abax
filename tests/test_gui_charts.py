"""GUI embedded charts — insert dialog, floating overlays, backend chooser, undo.

Driven offscreen (QT_QPA_PLATFORM=offscreen) like the other GUI tests.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.core.chartobj import CHART_KINDS, ChartObject  # noqa: E402
from abax.gui._qtcompat import (  # noqa: E402
    QApplication,
    QEvent,
    QTableWidgetSelectionRange,
)
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    _win = MainWindow(Settings())
    # The stdlib SVG backend keeps the render deterministic and fast; the
    # matplotlib path has its own dedicated tests below.
    _win._settings.chart_backend = "svg"
    yield _win
    _win.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _fill_numbers(win, rows=5):
    """One header + ``rows`` numbers in column A."""
    sheet = win._doc.workbook.sheet
    sheet.set_cell(0, 0, "alpha")
    for r in range(1, rows + 1):
        sheet.set_cell(r, 0, str(r * 2))
    win.refresh_table()
    return sheet


def _select(win, r1, c1, r2, c2):
    win._table.setCurrentCell(r1, c1)
    win._table.clearSelection()
    win._table.setRangeSelected(QTableWidgetSelectionRange(r1, c1, r2, c2), True)


def _insert_line_chart(win, source="A1:A6", **over):
    values = {"kind": "line", "source": source, "labels": "", "title": "trend",
              "width": 320, "height": 200}
    values.update(over)
    win.insert_embedded_chart(values)
    return win._doc.workbook.sheet.charts[-1]


class TestChartDialog:
    def test_source_prefilled_from_selection(self, win):
        from abax.gui.dialogs.chart_dialog import ChartDialog

        _fill_numbers(win)
        _select(win, 0, 0, 5, 1)
        dlg = ChartDialog(win)
        assert dlg._source.text() == "A1:B6"
        assert [dlg._kind.itemText(i) for i in range(dlg._kind.count())] == \
               list(CHART_KINDS)
        dlg.deleteLater()

    def test_edit_mode_seeds_and_round_trips_values(self, win):
        from abax.gui.dialogs.chart_dialog import ChartDialog

        chart = ChartObject(id="chart9", kind="bar", source="A1:A4", title="T",
                            labels="B1:B4", width=300, height=200)
        dlg = ChartDialog(win, chart=chart)
        assert dlg.windowTitle() == "Edit embedded chart"
        assert dlg.values() == {"kind": "bar", "source": "A1:A4",
                                "labels": "B1:B4", "title": "T",
                                "width": 300, "height": 200}
        dlg.deleteLater()


class TestInsertUndoDelete:
    def test_insert_appends_and_undo_removes(self, win):
        _fill_numbers(win)
        _select(win, 0, 0, 5, 0)
        chart = _insert_line_chart(win)
        sheet = win._doc.workbook.sheet
        assert len(sheet.charts) == 1
        assert chart.id == "chart1"
        assert chart.anchor == (0, 2)   # just right of the selection, top-aligned
        assert len(win._chart_overlays.widgets()) == 1

        win.undo_edit()                 # one checkpoint -> one undo step
        assert win._doc.workbook.sheet.charts == []
        assert win._chart_overlays.widgets() == []

        win.redo_edit()
        assert len(win._doc.workbook.sheet.charts) == 1
        assert len(win._chart_overlays.widgets()) == 1

    def test_delete_removes_overlay_and_undo_restores(self, win):
        _fill_numbers(win)
        _select(win, 0, 0, 5, 0)
        chart = _insert_line_chart(win)
        win.delete_embedded_chart(chart)
        assert win._doc.workbook.sheet.charts == []
        assert win._chart_overlays.widgets() == []

        win.undo_edit()
        assert len(win._doc.workbook.sheet.charts) == 1
        assert len(win._chart_overlays.widgets()) == 1

    def test_edit_via_dialog_is_one_undo_step(self, win, monkeypatch):
        from abax.gui.dialogs.chart_dialog import ChartDialog

        _fill_numbers(win)
        _select(win, 0, 0, 5, 0)
        chart = _insert_line_chart(win)
        before = win._chart_overlays.widgets()[0].rendered

        monkeypatch.setattr(ChartDialog, "exec", lambda self: 1)
        monkeypatch.setattr(ChartDialog, "values", lambda self: {
            "kind": "bar", "source": "A2:A6", "labels": "", "title": "bars",
            "width": 320, "height": 200})
        win.edit_embedded_chart(chart)
        assert chart.kind == "bar"
        assert win._chart_overlays.widgets()[0].rendered != before

        win.undo_edit()
        assert win._doc.workbook.sheet.charts[0].kind == "line"


class TestRenderLifecycle:
    def test_cell_edit_rerenders_the_chart(self, win):
        _fill_numbers(win)
        _select(win, 1, 0, 5, 0)
        _insert_line_chart(win, source="A2:A6", kind="bar")
        first = win._chart_overlays.widgets()[0].rendered
        assert first and first.startswith("<svg")

        # An in-grid edit routes through _commit_cell -> refresh_table.
        win._commit_cell(1, 0, "999")
        second = win._chart_overlays.widgets()[0].rendered
        assert second != first

    def test_recalc_rerenders_the_chart(self, win):
        sheet = _fill_numbers(win)
        _select(win, 1, 0, 5, 0)
        _insert_line_chart(win, source="A2:A6", kind="bar")
        first = win._chart_overlays.widgets()[0].rendered

        sheet.set_cell(1, 0, "777")     # bypass the GUI commit path…
        win._recalculate()              # …then F9 re-renders via refresh_table
        assert win._chart_overlays.widgets()[0].rendered != first

    def test_dead_range_paints_placeholder_not_crash(self, win):
        _fill_numbers(win)
        _select(win, 0, 0, 0, 0)
        _insert_line_chart(win, source="Nope!A1:B2")
        overlay = win._chart_overlays.widgets()[0]
        assert overlay.pixmap is None
        assert "Nope" in (overlay.error or "")
        overlay.repaint()               # placeholder paint path must not raise

    def test_overlay_pinned_to_anchor_and_follows_scroll(self, win):
        _fill_numbers(win)
        _select(win, 0, 0, 5, 0)
        _insert_line_chart(win)
        table = win._table
        overlay = win._chart_overlays.widgets()[0]
        assert overlay.width() == 320 and overlay.height() == 200
        assert overlay.pos().x() == table.columnViewportPosition(2)
        assert overlay.pos().y() == table.rowViewportPosition(0)

        bar = table.verticalScrollBar()
        bar.setValue(min(bar.maximum(), 120))   # per-pixel scroll mode
        assert overlay.pos().y() == table.rowViewportPosition(0)

    def test_only_active_sheet_charts_show(self, win):
        _fill_numbers(win)
        _select(win, 0, 0, 5, 0)
        _insert_line_chart(win)
        wb = win._doc.workbook
        wb.add_sheet("Empty")
        wb.active = len(wb.sheets) - 1
        win.refresh_table()
        assert win._chart_overlays.widgets() == []

        wb.active = 0
        win.refresh_table()
        assert len(win._chart_overlays.widgets()) == 1


class TestBackendChooser:
    def test_resolve_backend_matrix(self, monkeypatch):
        import abax.engine.chartmpl as chartmpl
        from abax.gui.chart_overlay import resolve_backend

        s = Settings()
        monkeypatch.setattr(chartmpl, "HAS_MATPLOTLIB", False)
        for pref in ("auto", "svg", "matplotlib"):
            s.chart_backend = pref
            assert resolve_backend(s) == "svg"

        monkeypatch.setattr(chartmpl, "HAS_MATPLOTLIB", True)
        expected = {"auto": "matplotlib", "svg": "svg", "matplotlib": "matplotlib"}
        for pref, backend in expected.items():
            s.chart_backend = pref
            assert resolve_backend(s) == backend

    def test_auto_without_matplotlib_uses_svg(self, win, monkeypatch):
        import abax.engine.chartmpl as chartmpl

        monkeypatch.setattr(chartmpl, "HAS_MATPLOTLIB", False)
        win._settings.chart_backend = "auto"
        _fill_numbers(win)
        _select(win, 0, 0, 5, 0)
        _insert_line_chart(win)
        overlay = win._chart_overlays.widgets()[0]
        assert overlay.backend_used == "svg"
        assert overlay.rendered.startswith("<svg")

    def test_matplotlib_missing_falls_back_with_hint(self, app, win, monkeypatch):
        import abax.engine.chartmpl as chartmpl

        monkeypatch.setattr(chartmpl, "HAS_MATPLOTLIB", False)
        win._settings.chart_backend = "matplotlib"
        _fill_numbers(win)
        _select(win, 0, 0, 5, 0)
        _insert_line_chart(win)
        overlay = win._chart_overlays.widgets()[0]
        assert overlay.backend_used == "svg"
        # The hint is deferred a turn so the insert's own status doesn't bury it.
        app.processEvents()
        assert "matplotlib" in win.statusBar().currentMessage()

    def test_matplotlib_backend_renders_png(self, win):
        pytest.importorskip("matplotlib")
        win._settings.chart_backend = "matplotlib"
        _fill_numbers(win)
        _select(win, 0, 0, 5, 0)
        _insert_line_chart(win)
        overlay = win._chart_overlays.widgets()[0]
        assert overlay.backend_used == "matplotlib"
        assert overlay.rendered[:8] == b"\x89PNG\r\n\x1a\n"
        assert overlay.pixmap is not None and not overlay.pixmap.isNull()


class TestMenuAndPalette:
    def test_insert_menu_has_embedded_chart(self, win):
        for menu_action in win.menuBar().actions():
            if menu_action.text().replace("&", "") == "Insert":
                labels = [a.text().replace("&", "")
                          for a in menu_action.menu().actions() if a.text()]
                assert "Embedded chart (on sheet)..." in labels
                return
        pytest.fail("Insert menu not found")

    def test_palette_has_insert_embedded_chart(self, win):
        assert "Insert embedded chart (on sheet)..." in win._palette_actions()


class TestPreferencesRow:
    def test_backend_combo_loads_and_applies(self, win, tmp_path, monkeypatch):
        from abax import _runtime as rt
        from abax.gui.dialogs.preferences_dialog import PreferencesDialog

        monkeypatch.setattr(rt, "CONFIG_DIR", tmp_path)  # keep persistence off the real config
        win._settings.chart_backend = "svg"
        dlg = PreferencesDialog(win)
        assert dlg._chart_backend.currentData() == "svg"
        dlg._select(dlg._chart_backend, "matplotlib")
        dlg._apply()
        assert win._settings.chart_backend == "matplotlib"
        dlg.deleteLater()
