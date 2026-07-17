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
    QMouseEvent,
    QPoint,
    QPointF,
    Qt,
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


_LEFT = Qt.MouseButton.LeftButton
_NONE = Qt.MouseButton.NoButton
_NO_MOD = Qt.KeyboardModifier.NoModifier


def _send_mouse(widget, etype, global_pos, button, buttons):
    """Deliver one synthetic mouse event (positions given in global coords).

    Global coordinates keep a multi-event drag coherent: the overlay moves
    between events, so widget-local positions are recomputed per event.
    """
    local = QPointF(widget.mapFromGlobal(global_pos))
    QApplication.sendEvent(widget, QMouseEvent(
        etype, local, QPointF(global_pos), button, buttons, _NO_MOD))


def _drag(widget, start, delta):
    """Left-press at widget-local ``start``, drag by ``delta`` px, release."""
    g0 = widget.mapToGlobal(QPoint(*start))
    g1 = g0 + QPoint(*delta)
    _send_mouse(widget, QEvent.Type.MouseButtonPress, g0, _LEFT, _LEFT)
    _send_mouse(widget, QEvent.Type.MouseMove, g1, _NONE, _LEFT)
    _send_mouse(widget, QEvent.Type.MouseButtonRelease, g1, _LEFT, _NONE)


def _hover(widget, pos):
    """A buttonless mouse move (mouse-tracking hover) at widget-local ``pos``."""
    _send_mouse(widget, QEvent.Type.MouseMove,
                widget.mapToGlobal(QPoint(*pos)), _NONE, _NONE)


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
                                "width": 300, "height": 200, "options": {}}
        dlg.deleteLater()


class TestChartOptionRows:
    """Per-kind renderer options in the dialog (bins / total / first_col_x)."""

    OPTION_WIDGETS = {"histogram": "_bins", "waterfall": "_total",
                      "line": "_first_col_x"}

    def test_only_the_active_kinds_options_show(self, win):
        from abax.gui.dialogs.chart_dialog import ChartDialog

        dlg = ChartDialog(win)
        for kind in list(self.OPTION_WIDGETS) + ["bar", "scatter", "heatmap"]:
            dlg._kind.setCurrentText(kind)
            for owner, attr in self.OPTION_WIDGETS.items():
                widget = getattr(dlg, attr)
                assert widget.isHidden() == (owner != kind)
                assert dlg._form.labelForField(widget).isHidden() == \
                       (owner != kind)
        dlg.deleteLater()

    def test_values_emit_only_non_defaults_of_the_active_kind(self, win):
        from abax.gui.dialogs.chart_dialog import ChartDialog

        dlg = ChartDialog(win)
        dlg._kind.setCurrentText("histogram")
        assert dlg.values()["options"] == {}          # default bins omitted
        dlg._bins.setValue(25)
        assert dlg.values()["options"] == {"bins": 25}

        dlg._kind.setCurrentText("waterfall")         # bins=25 now irrelevant
        assert dlg.values()["options"] == {}
        dlg._total.setChecked(False)
        assert dlg.values()["options"] == {"total": False}

        dlg._kind.setCurrentText("line")
        dlg._first_col_x.setChecked(True)
        assert dlg.values()["options"] == {"first_col_x": True}
        dlg._first_col_x.setChecked(False)            # back to default -> gone
        assert dlg.values()["options"] == {}
        dlg.deleteLater()

    def test_edit_mode_prefills_options_and_round_trips(self, win):
        from abax.gui.dialogs.chart_dialog import ChartDialog

        chart = ChartObject(id="c1", kind="histogram", source="A1:A9",
                            options={"bins": 30})
        dlg = ChartDialog(win, chart=chart)
        assert dlg._bins.value() == 30
        assert not dlg._bins.isHidden()
        assert dlg.values()["options"] == {"bins": 30}
        dlg._bins.setValue(10)                        # clear back to default
        assert dlg.values()["options"] == {}
        dlg.deleteLater()

        chart = ChartObject(id="c2", kind="waterfall", source="A1:A5",
                            options={"total": False})
        dlg = ChartDialog(win, chart=chart)
        assert not dlg._total.isChecked()
        assert dlg.values()["options"] == {"total": False}
        dlg._total.setChecked(True)
        assert dlg.values()["options"] == {}
        dlg.deleteLater()

    def test_insert_applies_options_and_renders_with_bins(self, win):
        _fill_numbers(win, rows=8)
        _select(win, 1, 0, 8, 0)
        win.insert_embedded_chart({
            "kind": "histogram", "source": "A2:A9", "labels": "",
            "title": "spread", "width": 320, "height": 200,
            "options": {"bins": 4}})
        chart = win._doc.workbook.sheet.charts[-1]
        assert chart.options == {"bins": 4}
        overlay = win._chart_overlays.widgets()[0]
        assert not overlay.error
        assert overlay.rendered.startswith("<svg")

    def test_edit_via_dialog_applies_and_clears_options(self, win, monkeypatch):
        from abax.gui.dialogs.chart_dialog import ChartDialog

        _fill_numbers(win)
        _select(win, 0, 0, 5, 0)
        chart = _insert_line_chart(win)
        assert chart.options == {}

        base = {"kind": "line", "source": "A1:A6", "labels": "", "title": "t",
                "width": 320, "height": 200}
        monkeypatch.setattr(ChartDialog, "exec", lambda self: 1)
        monkeypatch.setattr(ChartDialog, "values", lambda self: dict(
            base, options={"first_col_x": True}))
        win.edit_embedded_chart(chart)
        assert chart.options == {"first_col_x": True}

        monkeypatch.setattr(ChartDialog, "values", lambda self: dict(
            base, options={}))
        win.edit_embedded_chart(chart)                # defaults -> key removed
        assert chart.options == {}


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


class TestDragAndResize:
    """Direct manipulation: drag-to-move + the bottom-right resize handle."""

    def _chart_and_overlay(self, win):
        _fill_numbers(win)
        _select(win, 0, 0, 5, 0)
        chart = _insert_line_chart(win)          # 320x200 anchored at (0, 2)
        return chart, win._chart_overlays.widgets()[0]

    def test_drag_moves_live_and_commits_anchor(self, win):
        chart, overlay = self._chart_and_overlay(win)
        table = win._table
        assert chart.anchor == (0, 2)
        win._doc.dirty = False
        # Aim the top-left 3 px inside cell (3, 4): the drop snaps to that cell.
        dx = table.columnViewportPosition(4) + 3 - overlay.x()
        dy = table.rowViewportPosition(3) + 3 - overlay.y()
        g0 = overlay.mapToGlobal(QPoint(20, 20))
        g1 = g0 + QPoint(dx, dy)
        _send_mouse(overlay, QEvent.Type.MouseButtonPress, g0, _LEFT, _LEFT)
        _send_mouse(overlay, QEvent.Type.MouseMove, g1, _NONE, _LEFT)
        # Live move: the widget already follows the cursor before mouse-up…
        assert overlay.pos().x() == table.columnViewportPosition(4) + 3
        assert chart.anchor == (0, 2)            # …but the model is untouched
        _send_mouse(overlay, QEvent.Type.MouseButtonRelease, g1, _LEFT, _NONE)
        # Mouse-up commits pixels -> cell anchor and re-pins onto the cell.
        assert chart.anchor == (3, 4)
        assert overlay.pos().x() == table.columnViewportPosition(4)
        assert overlay.pos().y() == table.rowViewportPosition(3)
        assert win._doc.dirty                    # a move marks the doc modified

    def test_move_is_one_undo_step(self, win):
        chart, overlay = self._chart_and_overlay(win)
        table = win._table
        dx = table.columnViewportPosition(5) + 2 - overlay.x()
        _drag(overlay, (20, 20), (dx, 2))
        assert win._doc.workbook.sheet.charts[0].anchor == (0, 5)
        win.undo_edit()
        assert win._doc.workbook.sheet.charts[0].anchor == (0, 2)
        win.redo_edit()
        assert win._doc.workbook.sheet.charts[0].anchor == (0, 5)

    def test_resize_commits_size_and_undoes(self, win):
        chart, overlay = self._chart_and_overlay(win)
        win._doc.dirty = False
        _drag(overlay, (overlay.width() - 4, overlay.height() - 4), (60, 40))
        assert (chart.width, chart.height) == (380, 240)
        assert (overlay.width(), overlay.height()) == (380, 240)
        assert chart.anchor == (0, 2)            # a resize never moves the anchor
        assert win._doc.dirty
        win.undo_edit()
        chart = win._doc.workbook.sheet.charts[0]
        assert (chart.width, chart.height) == (320, 200)

    def test_resize_respects_minimum(self, win):
        chart, overlay = self._chart_and_overlay(win)
        from abax.gui.chart_overlay import MIN_HEIGHT, MIN_WIDTH

        _drag(overlay, (overlay.width() - 4, overlay.height() - 4), (-1000, -1000))
        assert (chart.width, chart.height) == (MIN_WIDTH, MIN_HEIGHT) == (80, 60)
        assert (overlay.width(), overlay.height()) == (MIN_WIDTH, MIN_HEIGHT)

    def test_drag_leaves_grid_selection_alone(self, win):
        chart, overlay = self._chart_and_overlay(win)
        table = win._table
        _select(win, 1, 0, 3, 0)
        table.setCurrentCell(1, 0)
        snapshot = lambda: (  # noqa: E731 - tiny local closure
            table.currentRow(), table.currentColumn(),
            [(r.topRow(), r.leftColumn(), r.bottomRow(), r.rightColumn())
             for r in table.selectedRanges()])
        before = snapshot()
        _drag(overlay, (15, 15), (40, 25))       # move…
        _drag(overlay, (overlay.width() - 4, overlay.height() - 4), (30, 20))  # …resize
        assert snapshot() == before

    def test_plain_click_commits_nothing(self, win):
        chart, overlay = self._chart_and_overlay(win)
        labels_before = win._doc.undo_history()[0]
        win._doc.dirty = False
        _drag(overlay, (15, 15), (0, 0))         # press + release, no motion
        assert chart.anchor == (0, 2)
        assert not win._doc.dirty
        assert win._doc.undo_history()[0] == labels_before

    def test_cursor_feedback_and_handle_paint(self, win):
        chart, overlay = self._chart_and_overlay(win)
        _hover(overlay, (15, 15))
        assert overlay.cursor().shape() == Qt.CursorShape.SizeAllCursor
        _hover(overlay, (overlay.width() - 3, overlay.height() - 3))
        assert overlay.cursor().shape() == Qt.CursorShape.SizeFDiagCursor
        overlay._hover = True
        overlay.repaint()                        # handle-paint path must not raise

    def test_geometry_round_trips_through_native_save(self, win, tmp_path):
        chart, overlay = self._chart_and_overlay(win)
        table = win._table
        dx = table.columnViewportPosition(4) + 3 - overlay.x()
        dy = table.rowViewportPosition(2) + 3 - overlay.y()
        _drag(overlay, (20, 20), (dx, dy))       # move to (2, 4)
        _drag(overlay, (overlay.width() - 4, overlay.height() - 4), (60, 40))
        assert win._doc.dirty
        path = tmp_path / "book.abax"
        win._doc.save(path)
        assert not win._doc.dirty

        from abax.core.workbook import Workbook

        loaded = Workbook.load_json(path).sheet.charts[0]
        assert loaded.anchor == chart.anchor == (2, 4)
        assert (loaded.width, loaded.height) == (chart.width, chart.height) \
               == (380, 240)


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
