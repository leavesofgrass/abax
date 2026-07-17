"""Floating embedded-chart overlays on the grid + the render-backend chooser.

Each :class:`~abax.core.chartobj.ChartObject` on the *active* sheet is shown as
a small widget floating over the cell grid, top-left pinned to the chart's
anchor cell and sized ``width x height``. The overlays are children of the
table's viewport, so they ride scrolling for free once repositioned on the
scrollbars' ``valueChanged``.

Re-rendering piggybacks on the GUI's single repaint choke point: every edit,
recalc, undo/redo, and sheet switch runs ``refresh_table``, which calls the
window's ``_refresh_chart_overlays`` (ToolsMixin) → :meth:`ChartOverlayManager.
refresh`. Renders are pure and uncached (see ``core/chartobj.py``), so a
refresh is simply "render again against current cell values".

Backend policy (the ``chart_backend`` setting): ``auto`` uses matplotlib when
it is installed and the stdlib SVG renderer otherwise; ``svg`` always uses the
stdlib renderer; ``matplotlib`` prefers matplotlib and falls back to SVG with a
one-time status-bar hint. A render failure (dead range, missing sheet, unknown
kind) never crashes the grid — the overlay paints a placeholder box carrying
the error message instead.

Overlays are directly manipulable: drag one to move it (the drop snaps its
anchor to the cell under the top-left corner), drag the bottom-right corner
handle to resize (clamped to ``MIN_WIDTH×MIN_HEIGHT``). Both commit into the
chart object through the document checkpoint — a single undo step each, and
the workbook is marked dirty so the change persists through save/load. Mouse
presses on an overlay never reach the grid, so grabbing a chart cannot move
the cell selection beneath it.
"""

from __future__ import annotations

from ._qtcompat import (
    QByteArray,
    QColor,
    QImage,
    QMenu,
    QPainter,
    QPen,
    QPixmap,
    QRect,
    QRectF,
    Qt,
    QWidget,
)
from ..core.chartobj import ChartError, render_chart
from ..core.reference import to_a1

# Placeholder palette (theme-neutral: readable on any grid).
_PLACEHOLDER_BG = "#f4f4f5"
_PLACEHOLDER_BORDER = "#c2410c"
_PLACEHOLDER_TEXT = "#7f1d1d"
_FRAME_COLOR = "#7a8194"

# Direct manipulation (drag-to-move / corner resize), all in pixels.
HANDLE_SIZE = 12      # hit zone of the bottom-right resize handle
MIN_WIDTH = 80        # smallest committable chart size
MIN_HEIGHT = 60


def resolve_backend(settings) -> str:
    """The renderer (``"svg"`` or ``"matplotlib"``) for the ``chart_backend`` setting.

    ``svg`` short-circuits without touching the optional engine module; the
    other two probe ``abax.engine.chartmpl.HAS_MATPLOTLIB`` at call time (so a
    test can monkeypatch it), degrading to ``svg`` when matplotlib is absent.
    """
    pref = (getattr(settings, "chart_backend", "auto") or "auto").strip().lower()
    if pref == "svg":
        return "svg"
    from ..engine import chartmpl

    return "matplotlib" if chartmpl.HAS_MATPLOTLIB else "svg"


def _svg_to_pixmap(svg: str, width: int, height: int) -> "QPixmap | None":
    """Rasterize SVG text via QtSvg; ``None`` when QtSvg is absent or the SVG is bad."""
    from ._qtcompat import QSvgRenderer

    if QSvgRenderer is None:
        return None
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    if not renderer.isValid():
        return None
    pixmap = QPixmap(max(1, int(width)), max(1, int(height)))
    pixmap.fill(Qt.GlobalColor.white)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, pixmap.width(), pixmap.height()))
    painter.end()
    return pixmap


class ChartOverlay(QWidget):
    """One floating chart. Paints its pre-rendered pixmap, or a placeholder box.

    Directly manipulable: a left-press anywhere grabs the chart (drag moves it
    live), a left-press on the bottom-right corner handle resizes it. Mouse-up
    hands the final widget geometry to the manager, which commits it into the
    :class:`~abax.core.chartobj.ChartObject` (one undo checkpoint each). Every
    press is accepted here so a click on a chart never falls through to the
    grid and re-selects the cell underneath.
    """

    def __init__(self, manager: "ChartOverlayManager", chart) -> None:
        super().__init__(manager.viewport())
        self._manager = manager
        self.chart = chart
        self.pixmap: "QPixmap | None" = None
        self.rendered = None       # last SVG text / PNG bytes (tests + debugging)
        self.backend_used = ""     # "svg" | "matplotlib" (whichever actually drew)
        self.error: "str | None" = None
        self._drag_mode: "str | None" = None    # None | "move" | "resize"
        self._press_global = None               # QPoint at mouse-down
        self._press_geometry = None             # QRect at mouse-down
        self._hover = False
        self.setMouseTracking(True)             # cursor feedback without a button
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def update_render(self, chart, pixmap, rendered, backend: str,
                      error: "str | None") -> None:
        """Adopt a fresh render (the live chart object may have been rebuilt by undo)."""
        self.chart = chart
        self.pixmap = pixmap
        self.rendered = rendered
        self.backend_used = backend
        self.error = error
        self.setToolTip(f"{chart.id}: {chart.kind} of {chart.source}"
                        " — right-click to edit or delete")
        self.resize(max(1, int(chart.width)), max(1, int(chart.height)))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        try:
            rect = self.rect()
            if self.pixmap is not None:
                painter.drawPixmap(rect, self.pixmap)
                painter.setPen(QPen(QColor(_FRAME_COLOR)))
                painter.drawRect(rect.adjusted(0, 0, -1, -1))
            else:
                # Placeholder: a chart must never crash (or blank) the grid paint.
                painter.fillRect(rect, QColor(_PLACEHOLDER_BG))
                painter.setPen(QPen(QColor(_PLACEHOLDER_BORDER)))
                painter.drawRect(rect.adjusted(0, 0, -1, -1))
                painter.setPen(QPen(QColor(_PLACEHOLDER_TEXT)))
                flags = (int(Qt.AlignmentFlag.AlignLeft) | int(Qt.AlignmentFlag.AlignTop)
                         | int(Qt.TextFlag.TextWordWrap))
                message = self.error or "chart unavailable"
                painter.drawText(rect.adjusted(6, 4, -6, -4), flags,
                                 f"[{self.chart.id}] {message}")
            if self._hover or self._drag_mode is not None:
                # The resize affordance: a small filled square in the corner.
                painter.fillRect(self.handle_rect().adjusted(3, 3, -1, -1),
                                 QColor(_FRAME_COLOR))
        finally:
            painter.end()

    def _context_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction("Edit chart…", lambda: self._manager.edit(self.chart))
        menu.addAction("Delete chart", lambda: self._manager.delete(self.chart))
        menu.exec(self.mapToGlobal(pos))

    # -- direct manipulation (drag-to-move / corner resize) -----------------

    def handle_rect(self) -> QRect:
        """The bottom-right resize handle's hit zone, in widget coords."""
        return QRect(self.width() - HANDLE_SIZE, self.height() - HANDLE_SIZE,
                     HANDLE_SIZE, HANDLE_SIZE)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # Swallow every press: a click on a chart must never fall through to
        # the table viewport and change the grid selection underneath.
        event.accept()
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.raise_()   # of stacked charts, the grabbed one comes to the front
        on_handle = self.handle_rect().contains(event.position().toPoint())
        self._drag_mode = "resize" if on_handle else "move"
        self._press_global = event.globalPosition().toPoint()
        self._press_geometry = self.geometry()
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if on_handle
                       else Qt.CursorShape.SizeAllCursor)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # A double-click must not fall through either (it would start a cell
        # edit under the chart); treat it as another grab.
        self.mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        event.accept()
        if self._drag_mode is None:
            # No button down (mouse tracking): pure cursor feedback.
            on_handle = self.handle_rect().contains(event.position().toPoint())
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if on_handle
                           else Qt.CursorShape.SizeAllCursor)
            return
        # Deltas are in *global* coords: the widget itself moves under the
        # cursor mid-drag, so local positions would feed back into themselves.
        delta = event.globalPosition().toPoint() - self._press_global
        if self._drag_mode == "move":
            self.move(self._press_geometry.topLeft() + delta)
        else:
            self.resize(max(MIN_WIDTH, self._press_geometry.width() + delta.x()),
                        max(MIN_HEIGHT, self._press_geometry.height() + delta.y()))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        event.accept()
        if event.button() != Qt.MouseButton.LeftButton or self._drag_mode is None:
            return
        mode, self._drag_mode = self._drag_mode, None
        if self.geometry() == self._press_geometry:
            return   # a plain click: nothing moved, nothing to commit
        if mode == "move":
            self._manager.commit_move(self)
        else:
            self._manager.commit_resize(self)

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = True
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = False
        self.unsetCursor()
        self.update()
        super().leaveEvent(event)


class ChartOverlayManager:
    """Keeps one :class:`ChartOverlay` per chart of the active sheet, in sync."""

    def __init__(self, window) -> None:
        self._win = window
        self._overlays: dict[str, ChartOverlay] = {}
        self._hinted_fallback = False
        table = window._table
        # Overlays are viewport children, so following a scroll is a pure move;
        # row/column resizes (header drags, autofit, zoom) shift anchors too.
        table.verticalScrollBar().valueChanged.connect(self._reposition)
        table.horizontalScrollBar().valueChanged.connect(self._reposition)
        table.horizontalHeader().sectionResized.connect(self._reposition)
        table.verticalHeader().sectionResized.connect(self._reposition)

    # -- host plumbing ------------------------------------------------------

    def viewport(self):
        return self._win._table.viewport()

    def widgets(self) -> "list[ChartOverlay]":
        return list(self._overlays.values())

    def edit(self, chart) -> None:
        self._win.edit_embedded_chart(chart)

    def delete(self, chart) -> None:
        self._win.delete_embedded_chart(chart)

    # -- geometry commits (mouse-up of a drag) -------------------------------

    def commit_move(self, overlay: ChartOverlay) -> None:
        """Persist a finished drag-move: pixels → the model's cell anchor.

        The model stores a plain ``(row, col)`` anchor (no pixel offset), so
        the drop snaps to the cell under the overlay's top-left corner — the
        repaint pins it exactly onto that cell. No-op drops (same cell) just
        snap back without touching the undo stack.
        """
        table = self._win._table
        pos = overlay.pos()
        anchor = (_cell_index(table.rowAt, pos.y(), table.rowCount()),
                  _cell_index(table.columnAt, pos.x(), table.columnCount()))
        if anchor == tuple(overlay.chart.anchor):
            self._reposition()
            return
        chart = overlay.chart
        self._commit("move chart", lambda: setattr(chart, "anchor", anchor),
                     f"moved chart {chart.id} to {to_a1(*anchor)}")

    def commit_resize(self, overlay: ChartOverlay) -> None:
        """Persist a finished handle-drag: the widget size becomes the model size."""
        chart = overlay.chart
        width, height = overlay.width(), overlay.height()
        if (width, height) == (chart.width, chart.height):
            return

        def apply() -> None:
            chart.width, chart.height = width, height

        self._commit("resize chart", apply,
                     f"resized chart {chart.id} to {width}×{height}")

    def _commit(self, label: str, mutate, status: str) -> None:
        """Checkpoint → mutate → repaint: one undo step, same as insert/edit/delete."""
        win = self._win
        win._doc.checkpoint(label)   # snapshot BEFORE the mutation
        mutate()
        win._doc.mark_dirty()
        win.refresh_table()          # re-render + reposition (and title dirty mark)
        win._refresh_undo_history()
        win._set_status(status)

    # -- sync + render -------------------------------------------------------

    def refresh(self) -> None:
        """Mirror the ACTIVE sheet's charts as overlays and re-render each one.

        Called from ``refresh_table`` (the single repaint choke point), so cell
        edits, recalc, undo/redo, and sheet switches all land here. Undo may have
        rebuilt the chart objects from the envelope, hence overlays re-adopt the
        current object for their id on every pass.
        """
        sheet = self._win._doc.workbook.sheet
        charts = {ch.id: ch for ch in getattr(sheet, "charts", [])}
        for chart_id in list(self._overlays):
            if chart_id not in charts:
                self._overlays.pop(chart_id).deleteLater()
        if not charts:
            return
        backend = resolve_backend(self._win._settings)
        self._maybe_hint_fallback(backend)
        for chart_id, chart in charts.items():
            overlay = self._overlays.get(chart_id)
            if overlay is None:
                overlay = self._overlays[chart_id] = ChartOverlay(self, chart)
            overlay.update_render(chart, *self._render(chart, backend))
            overlay.show()
        self._reposition()

    def _maybe_hint_fallback(self, backend: str) -> None:
        """One status-bar hint when 'matplotlib' is asked for but unavailable.

        Deferred one event-loop turn so it lands *after* the status message of
        whatever action triggered this refresh (insert/edit/recalc) instead of
        being overwritten by it.
        """
        pref = (getattr(self._win._settings, "chart_backend", "auto") or "auto").lower()
        if pref == "matplotlib" and backend == "svg" and not self._hinted_fallback:
            self._hinted_fallback = True
            set_status = getattr(self._win, "_set_status", None)
            if set_status is not None:
                from ._qtcompat import QTimer

                QTimer.singleShot(0, lambda: set_status(
                    "matplotlib is not installed — charts use the built-in "
                    'SVG renderer (pip install "abax[charts]")'))

    def _render(self, chart, backend: str):
        """``(pixmap, payload, backend_used, error)`` for one chart; never raises."""
        workbook = self._win._doc.workbook
        host = workbook.sheet.name
        try:
            if backend == "matplotlib":
                from ..engine.chartmpl import render_chart_mpl

                try:
                    png = bytes(render_chart_mpl(workbook, host, chart, fmt="png"))
                except RuntimeError:
                    png = None  # probe said yes but the backend is unusable
                if png is not None:
                    pixmap = QPixmap.fromImage(QImage.fromData(QByteArray(png)))
                    if not pixmap.isNull():
                        return pixmap, png, "matplotlib", None
                # fall through: render the same data with the stdlib SVG path
            svg = render_chart(workbook, host, chart)
            pixmap = _svg_to_pixmap(svg, chart.width, chart.height)
            if pixmap is None:
                return None, svg, "svg", "QtSvg is unavailable — cannot paint the chart"
            return pixmap, svg, "svg", None
        except ChartError as exc:
            return None, None, backend, str(exc)
        except Exception as exc:  # a chart must never crash the grid paint
            return None, None, backend, f"chart render failed: {exc}"

    def _reposition(self, *_args) -> None:
        """Pin every overlay's top-left to its anchor cell (viewport coords)."""
        table = self._win._table
        for overlay in self._overlays.values():
            row, col = overlay.chart.anchor
            overlay.move(table.columnViewportPosition(max(0, int(col))),
                         table.rowViewportPosition(max(0, int(row))))


def _cell_index(at, coord: int, count: int) -> int:
    """The row/column under viewport pixel ``coord``, clamped into the grid.

    ``at`` is the table's ``rowAt``/``columnAt`` (which answer ``-1`` past the
    content's end). A drop above/left of the viewport clamps to the first
    visible row/column; a drop past the last row/column clamps to the last.
    """
    idx = at(max(0, int(coord)))
    return idx if idx >= 0 else max(0, count - 1)
