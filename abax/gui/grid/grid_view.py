"""CellTableView — the virtualized grid widget and its editing delegate.

A ``QTableView`` over :class:`~abax.gui.grid_model.AbaxTableModel` that:

1. **emulates the slice of the old QTableWidget API** the rest of the GUI calls
   (``currentRow``/``currentColumn``, ``setCurrentCell``, ``rowCount``/
   ``columnCount``, ``selectedRanges``/``setRangeSelected``, ``item`` proxy,
   ``scrollToItem``) — so existing call sites stay put — and re-emits a
   ``currentCellChanged`` signal so the formula bar / status keep updating; and
2. **owns Excel-faithful keyboard navigation in one place**: Enter advances down
   (Shift+Enter up), Tab right (Shift+Tab left), F2 edits in place, a printable
   key starts a replace-mode edit, Ctrl+Arrow jumps to the data edge, Ctrl+Home/
   End jump to A1 / last used cell. ``:`` and the vim movement keys are left to
   propagate to the window, so the command palette and vim mode are unaffected.
"""

from __future__ import annotations

from .._qtcompat import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QBrush,
    QColor,
    QComboBox,
    QEvent,
    QFont,
    QItemSelection,
    QItemSelectionModel,
    QLineEdit,
    QPainter,
    QPainterPath,
    QPen,
    QPointF,
    QRect,
    QRectF,
    QStyledItemDelegate,
    Qt,
    QTableView,
    QTableWidgetSelectionRange,
    QToolTip,
    pyqtSignal,
)
from ...core.reference import to_a1

# Excel-style dynamic-array spill outline colour (a calm blue).
_SPILL_COLOR = "#3b82f6"

# Drag fill-handle: the little square at the bottom-right of the selection.
_FILL_HANDLE_SIZE = 6

# Cell-border rendering: the fidelity model's three weights map to pen widths,
# drawn in a neutral dark grey that reads on any theme's cell fill.
_BORDER_COLOR = "#1f2430"
_BORDER_WIDTH = {"thin": 1, "medium": 2, "thick": 3}

# Comment marker: a small red triangle tucked into the cell's top-right corner.
_COMMENT_COLOR = "#dc2626"
_COMMENT_MARKER_SIZE = 6

_VIM_KEYS = frozenset("jkhlgG/")


class GridDelegate(QStyledItemDelegate):
    """Editor delegate: list-validation dropdowns + Excel commit-and-move.

    A list-validated cell edits through a combo box pre-filled with the allowed
    values (still editable; a typed value is checked by the normal on-commit
    validation). Pressing Enter/Tab inside any editor commits and then moves the
    selection (down/right; Shift reverses). The pending move is stashed on the
    view and applied from :meth:`CellTableView.closeEditor` once Qt has written
    the value back, so the value lands before the cursor moves.
    """

    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window

    def paint(self, painter, option, index):  # noqa: N802 (Qt override)
        """Draw the cell, then overlay a small red triangle on any commented cell
        and trace the dashed spill outline on any region edge passing through it —
        the visual cues for a note and for a dynamic-array spill respectively.
        A cell whose computed value is a Sparkline paints as an inline SVG chart
        (falling back to its unicode text form when QtSvg is unavailable)."""
        if self._paint_sparkline(painter, option, index):
            sheet = self._win._doc.workbook.sheet
            self._paint_cell_borders(painter, option, sheet, index)
            return
        super().paint(painter, option, index)
        sheet = self._win._doc.workbook.sheet
        self._paint_cell_borders(painter, option, sheet, index)
        if sheet.get_comment(index.row(), index.column()) is not None:
            self._paint_comment_marker(painter, option)
        self._maybe_paint_fill_handle(painter, option, index)
        edges = sheet.spill_edges(index.row(), index.column())
        if not edges:
            return
        painter.save()
        pen = QPen(QColor(_SPILL_COLOR))
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        rect = option.rect.adjusted(0, 0, -1, -1)
        if "top" in edges:
            painter.drawLine(rect.topLeft(), rect.topRight())
        if "bottom" in edges:
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if "left" in edges:
            painter.drawLine(rect.topLeft(), rect.bottomLeft())
        if "right" in edges:
            painter.drawLine(rect.topRight(), rect.bottomRight())
        painter.restore()

    def _paint_sparkline(self, painter, option, index) -> bool:
        """Paint an in-cell SPARKLINE as SVG; True when the cell was handled.

        Returns False for non-Sparkline cells AND when QtSvg is unavailable or
        the SVG fails to parse — the caller then falls through to the default
        text paint, which draws the Sparkline's unicode ``str()`` form.
        """
        from ...core.sparkcell import Sparkline

        sheet = self._win._doc.workbook.sheet
        val = sheet.get_value(index.row(), index.column())
        if not isinstance(val, Sparkline):
            return False
        from .._qtcompat import QByteArray, QSvgRenderer

        if QSvgRenderer is None:
            return False
        try:
            rect = option.rect.adjusted(1, 1, -1, -1)
            svg = val.to_svg(width=max(8, rect.width()), height=max(6, rect.height()))
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            if not renderer.isValid():
                return False
            painter.save()
            renderer.render(painter, QRectF(rect))
            painter.restore()
            return True
        except Exception:  # noqa: BLE001 — never let a chart crash the grid paint
            return False

    def _paint_comment_marker(self, painter, option) -> None:
        """Fill a small red triangle in the cell's top-right corner (the note cue)."""
        rect = option.rect
        size = _COMMENT_MARKER_SIZE
        top_right = rect.topRight()
        path = QPainterPath()
        path.moveTo(QPointF(top_right.x() - size, top_right.y() + 1))
        path.lineTo(QPointF(top_right.x() + 1, top_right.y() + 1))
        path.lineTo(QPointF(top_right.x() + 1, top_right.y() + size + 1))
        path.closeSubpath()
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(path, QBrush(QColor(_COMMENT_COLOR)))
        painter.restore()

    def _paint_cell_borders(self, painter, option, sheet, index) -> None:
        """Stroke the per-edge borders set on this cell (fidelity model).

        Each edge in ``sheet.cell_border`` carries a weight (thin/medium/thick);
        the line is drawn just inside the cell rect so it reads on the cell's own
        fill rather than fighting the grid line."""
        border = sheet.cell_border(index.row(), index.column())
        if not border:
            return
        rect = option.rect
        painter.save()
        for edge, style in border.items():
            width = _BORDER_WIDTH.get(style, 1)
            pen = QPen(QColor(_BORDER_COLOR))
            pen.setWidth(width)
            painter.setPen(pen)
            # Inset by half the pen width so the stroke stays within the cell.
            off = width // 2
            if edge == "top":
                y = rect.top() + off
                painter.drawLine(rect.left(), y, rect.right(), y)
            elif edge == "bottom":
                y = rect.bottom() - off
                painter.drawLine(rect.left(), y, rect.right(), y)
            elif edge == "left":
                x = rect.left() + off
                painter.drawLine(x, rect.top(), x, rect.bottom())
            elif edge == "right":
                x = rect.right() - off
                painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.restore()

    def _maybe_paint_fill_handle(self, painter, option, index) -> None:
        """Draw the drag fill-handle on the bottom-right cell of the selection."""
        table = self._win._table
        br = table._selection_bounds()
        if (br is None or index.row() != br[2] or index.column() != br[3]
                or table.state() == QAbstractItemView.State.EditingState):
            return
        r = option.rect
        s = _FILL_HANDLE_SIZE
        painter.save()
        painter.setPen(QPen(QColor("#ffffff")))
        painter.setBrush(QBrush(QColor(_SPILL_COLOR)))
        painter.drawRect(r.right() - s, r.bottom() - s, s, s)
        painter.restore()

    def _list_rule(self, index):
        sheet = self._win._doc.workbook.sheet
        rule = sheet.validation_for(index.row(), index.column())
        if rule is not None and rule.kind == "list" and rule.values:
            return rule
        return None

    def createEditor(self, parent, option, index):  # noqa: N802 (Qt override)
        rule = self._list_rule(index)
        if rule is not None:
            combo = QComboBox(parent)
            combo.setEditable(True)
            combo.addItems(list(rule.values))
            return combo
        editor = super().createEditor(parent, option, index)
        # Give the in-cell editor the same formula autocomplete as the formula bar
        # (function names + the workbook's defined names / sheet names). Held on the
        # editor so it lives for the edit and is torn down with it.
        if isinstance(editor, QLineEdit):
            from ..completion import FormulaCompleter
            editor._abax_completer = FormulaCompleter(
                editor, context=getattr(self._win, "_completion_context", None))
            # Show the same function argument-hint tooltip the formula bar shows,
            # anchored to the in-cell editor, whenever its text is a formula.
            editor.textEdited.connect(lambda _t, e=editor: self._show_arg_hint(e))
            editor.cursorPositionChanged.connect(
                lambda _o, _n, e=editor: self._show_arg_hint(e))
        return editor

    @staticmethod
    def arg_hint_text(text: str, cursor: int | None = None) -> str | None:
        """Rendered argument hint for a formula ``text`` under ``cursor``, or None.

        Returns ``None`` for non-formula text (not starting with ``=``) or when no
        call is active. Reuses the formula-bar hint logic so the in-cell tooltip
        matches it exactly.
        """
        if not text.startswith("="):
            return None
        from ...core.completion import format_hint, signature_hint

        hint = signature_hint(text, cursor)
        if hint is None:
            return None
        return format_hint(hint, ("<b>", "</b>"))

    def _show_arg_hint(self, editor) -> None:
        """Float the argument hint under the in-cell editor (or hide it)."""
        rendered = self.arg_hint_text(editor.text(), editor.cursorPosition())
        if rendered is None:
            QToolTip.hideText()
            return
        pos = editor.mapToGlobal(editor.rect().bottomLeft())
        QToolTip.showText(pos, rendered, editor)

    def setEditorData(self, editor, index):  # noqa: N802 (Qt override)
        if isinstance(editor, QComboBox):
            text = index.data(Qt.ItemDataRole.EditRole) or ""
            i = editor.findText(text)
            if i >= 0:
                editor.setCurrentIndex(i)
            else:
                editor.setEditText(text)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):  # noqa: N802 (Qt override)
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)
        else:
            super().setModelData(editor, model, index)

    def eventFilter(self, editor, event):  # noqa: N802 (Qt override)
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            move = None
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                move = (-1, 0) if shift else (1, 0)
            elif key == Qt.Key.Key_Tab:
                move = (0, 1)
            elif key == Qt.Key.Key_Backtab:
                move = (0, -1)
            if move is not None:
                self._win._table._pending_move = move
                self.commitData.emit(editor)
                self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
                return True
        return super().eventFilter(editor, event)


class _ItemProxy:
    """Minimal stand-in for a QTableWidgetItem's read API (display text only)."""

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text = text

    def text(self) -> str:  # noqa: D401
        return self._text


class CellTableView(QTableView):
    # QTableWidget-compatible signal: (row, col, prevRow, prevCol). Existing
    # wiring connects this to update the formula bar / status on the active cell.
    currentCellChanged = pyqtSignal(int, int, int, int)

    def __init__(self, window, model) -> None:
        super().__init__(window)
        self._win = window
        self._pending_move: tuple[int, int] | None = None
        self._filling = False
        self._fill_src: tuple[int, int, int, int] | None = None
        # Anchor cells the view currently spans (for merges); reset before each
        # re-span in apply_merges so a merge that shrinks/moves is cleaned up.
        self._spanned: list[tuple[int, int]] = []
        self.setModel(model)
        self.setMouseTracking(True)   # for the fill-handle hover cursor
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        # Typing a printable char starts a replace-mode edit; F2 / double-click
        # edit in place. ':' and vim keys are intercepted in keyPressEvent so
        # they reach the window instead of starting an edit.
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        # Screen-reader identity for the grid itself. The model serves per-cell
        # AccessibleText/Description roles; Qt announces the focused cell on move,
        # and we mirror the current cell onto the view's description as a fallback.
        self.setAccessibleName("Spreadsheet grid")
        self.setAccessibleDescription(
            "Spreadsheet cells. Arrow keys move; type to edit; F2 edits in place.")
        self.selectionModel().currentChanged.connect(self._emit_current_changed)
        self.selectionModel().currentChanged.connect(self._announce_current)

    # -- current-cell signal ----------------------------------------------

    def _emit_current_changed(self, cur, prev) -> None:
        self.currentCellChanged.emit(
            cur.row() if cur.isValid() else -1,
            cur.column() if cur.isValid() else -1,
            prev.row() if prev.isValid() else -1,
            prev.column() if prev.isValid() else -1)

    def _announce_current(self, cur, prev) -> None:
        """Mirror the active cell onto the view's accessible description.

        Qt already raises a focus event that names the cell (via the model's
        AccessibleTextRole) as the current index moves; this keeps the view's own
        description in sync so a reader querying the grid hears the live cell too.
        """
        if not cur.isValid():
            return
        text = cur.data(Qt.ItemDataRole.AccessibleTextRole)
        if text:
            self.setAccessibleDescription(str(text))

    # -- merged cells: spanning + speak-on-move ---------------------------

    def apply_merges(self) -> None:
        """Re-apply ``setSpan`` for every merge region on the active sheet.

        QTableView tracks spans by (row, col) span sizes; there is no bulk-clear,
        so we track the spans we set on ``_spanned`` and reset each (to 1x1)
        before laying down the current sheet's merges. Called from the model's
        ``refresh`` (the single repaint choke point) so a merge/unmerge, an
        undo/redo, or a sheet switch all keep the spans correct.
        """
        for r, c in self._spanned:
            # Only reset a still-in-range cell; a shrunk grid drops it naturally.
            if r < self.rowCount() and c < self.columnCount():
                self.setSpan(r, c, 1, 1)
        spanned: list[tuple[int, int]] = []
        for (r1, c1, r2, c2) in self._win._doc.workbook.sheet.merges:
            self.setSpan(r1, c1, r2 - r1 + 1, c2 - c1 + 1)
            spanned.append((r1, c1))
        self._spanned = spanned

    def speak_current(self, row: int, col: int) -> None:
        """Speak the active cell (A1 ref + value) when speak-on-move is enabled.

        Guarded: the TTS backend (``abax.engine.tts.speak``) is optional and may
        not be installed, so an ImportError (or any speak failure) degrades to a
        silent no-op. Wired to the current-cell signal by the integrator; harmless
        until the backend lands and the ``speak_on_move`` setting is turned on.
        """
        if not getattr(self._win._settings, "speak_on_move", False):
            return
        if row < 0 or col < 0:
            return
        try:
            from ...engine.tts import speak
        except ImportError:
            return
        sheet = self._win._doc.workbook.sheet
        # Land the utterance on the merge anchor's value when the cell is merged.
        anchor = sheet.merge_anchor(row, col)
        ar, ac = anchor if anchor is not None else (row, col)
        ref = to_a1(ar, ac)
        shown = sheet.display(ar, ac)
        phrase = f"{ref} {shown}" if shown else ref
        try:
            speak(phrase)
        except Exception:
            # A backend hiccup must never break navigation.
            pass

    # -- empty-sheet onboarding hint --------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().paintEvent(event)
        # A subtle getting-started hint over a blank sheet. It disappears the
        # instant any cell is populated (every edit triggers a full-extent
        # repaint) or the user starts typing (an editor is open) — so it never
        # sits behind real content.
        try:
            if self.state() == QAbstractItemView.State.EditingState:
                return
            if self._win._model.populated_cells():
                return
        except Exception:
            return
        vp = self.viewport()
        rect = vp.rect()
        if rect.width() < 300 or rect.height() < 170:
            return  # too cramped to read; skip rather than clutter

        painter = QPainter(vp)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        base = self.palette().text().color()
        strong = QColor(base)
        strong.setAlpha(140)
        faint = QColor(base)
        faint.setAlpha(105)

        title_font = QFont(self.font())
        title_font.setPointSizeF(max(12.0, title_font.pointSizeF() + 4))
        title_font.setBold(True)
        hint_font = QFont(self.font())

        top = rect.center().y() - 28
        painter.setFont(title_font)
        painter.setPen(strong)
        th = painter.fontMetrics().height()
        painter.drawText(QRect(rect.left(), top, rect.width(), th),
                         Qt.AlignmentFlag.AlignHCenter, "Blank sheet")

        painter.setFont(hint_font)
        painter.setPen(faint)
        hh = painter.fontMetrics().height()
        y1 = top + th + 10
        painter.drawText(QRect(rect.left(), y1, rect.width(), hh),
                         Qt.AlignmentFlag.AlignHCenter,
                         "Type to enter data — start a formula with  =")
        y2 = y1 + hh + 4
        painter.drawText(QRect(rect.left(), y2, rect.width(), hh),
                         Qt.AlignmentFlag.AlignHCenter,
                         "Ctrl+Shift+P  commands       F1  shortcuts       Ctrl+K  calculator")
        painter.end()

    # -- drag fill handle -------------------------------------------------

    def _selection_bounds(self):
        """(top, left, bottom, right) spanning the whole selection, or None."""
        sel = self.selectionModel().selection()
        if not sel:
            return None
        return (min(r.top() for r in sel), min(r.left() for r in sel),
                max(r.bottom() for r in sel), max(r.right() for r in sel))

    def _fill_handle_rect(self):
        """Grab rect (viewport coords) for the fill handle, or None."""
        br = self._selection_bounds()
        if br is None or self.state() == QAbstractItemView.State.EditingState:
            return None
        cell = self.visualRect(self.model().index(br[2], br[3]))
        if cell.width() <= 0 or cell.height() <= 0:
            return None
        g = _FILL_HANDLE_SIZE + 3
        return QRect(cell.right() - g, cell.bottom() - g, g + 3, g + 3)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            hr = self._fill_handle_rect()
            if hr is not None and hr.contains(event.position().toPoint()):
                self._fill_src = self._selection_bounds()
                self._filling = True
                self.setCursor(Qt.CursorShape.CrossCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        pt = event.position().toPoint()
        if self._filling and self._fill_src is not None:
            idx = self.indexAt(pt)
            if idx.isValid():
                top, left, bottom, right = self._fill_src
                r, c = idx.row(), idx.column()
                # Grow along whichever edge the pointer has moved furthest past;
                # the fill handle drags in any of the four directions (Excel-like).
                down, up = max(0, r - bottom), max(0, top - r)
                rgt, lft = max(0, c - right), max(0, left - c)
                m = max(down, up, rgt, lft)
                if m == 0:                        # back within the source
                    r1, c1, r2, c2 = top, left, bottom, right
                elif m == down:
                    r1, c1, r2, c2 = top, left, r, right
                elif m == up:
                    r1, c1, r2, c2 = r, left, bottom, right
                elif m == rgt:
                    r1, c1, r2, c2 = top, left, bottom, c
                else:                             # left
                    r1, c1, r2, c2 = top, c, bottom, right
                model = self.model()
                self.selectionModel().select(
                    QItemSelection(model.index(r1, c1), model.index(r2, c2)),
                    QItemSelectionModel.SelectionFlag.ClearAndSelect)
            event.accept()
            return
        # hover: show the cross cursor when over the handle
        hr = self._fill_handle_rect()
        if hr is not None and hr.contains(pt):
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self.cursor().shape() == Qt.CursorShape.CrossCursor:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._filling:
            self._filling = False
            self.unsetCursor()
            src, self._fill_src = self._fill_src, None
            cur = self._selection_bounds()
            if src is not None and cur is not None and cur != src:
                # the selection grew past the source — extend the series into it
                self._win._fill_from_handle(src, cur)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # -- QTableWidget-compatible API --------------------------------------

    def rowCount(self) -> int:  # noqa: N802
        return self.model().rowCount()

    def columnCount(self) -> int:  # noqa: N802
        return self.model().columnCount()

    def setRowCount(self, n: int) -> None:  # noqa: N802
        self.model().ensure_extent(n, self.model().columnCount())

    def setColumnCount(self, n: int) -> None:  # noqa: N802
        self.model().ensure_extent(self.model().rowCount(), n)

    def setHorizontalHeaderLabels(self, labels) -> None:  # noqa: N802 - model serves headers
        pass

    def setVerticalHeaderLabels(self, labels) -> None:  # noqa: N802 - model serves headers
        pass

    def currentRow(self) -> int:  # noqa: N802
        idx = self.currentIndex()
        return idx.row() if idx.isValid() else -1

    def currentColumn(self) -> int:  # noqa: N802
        idx = self.currentIndex()
        return idx.column() if idx.isValid() else -1

    def setCurrentCell(self, row: int, col: int) -> None:  # noqa: N802
        if row < 0 or col < 0:
            return
        # Landing anywhere inside a merge selects the whole region — the cursor
        # sits on the anchor (Excel semantics), so a click/goto/enter into a
        # merged interior never leaves the active cell on a hidden interior cell.
        anchor = self._win._doc.workbook.sheet.merge_anchor(row, col)
        if anchor is not None:
            row, col = anchor
        model = self.model()
        model.ensure_extent(row + 1, col + 1)
        self.setCurrentIndex(model.index(row, col))

    def item(self, row: int, col: int) -> _ItemProxy:
        model = self.model()
        text = model.data(model.index(row, col), Qt.ItemDataRole.DisplayRole) or ""
        return _ItemProxy(text)

    def setItem(self, row: int, col: int, item) -> None:  # noqa: N802 - model-backed; no-op
        pass

    def scrollToItem(self, item, hint=QAbstractItemView.ScrollHint.EnsureVisible) -> None:  # noqa: N802
        self.scrollTo(self.currentIndex(), hint)

    def selectedRanges(self):  # noqa: N802
        return [QTableWidgetSelectionRange(sr.top(), sr.left(), sr.bottom(), sr.right())
                for sr in self.selectionModel().selection()]

    def setRangeSelected(self, rng, on: bool) -> None:  # noqa: N802
        model = self.model()
        sel = QItemSelection(model.index(rng.topRow(), rng.leftColumn()),
                             model.index(rng.bottomRow(), rng.rightColumn()))
        flag = (QItemSelectionModel.SelectionFlag.Select if on
                else QItemSelectionModel.SelectionFlag.Deselect)
        self.selectionModel().select(sel, flag)

    # -- navigation (the Excel feel) --------------------------------------

    def move_cursor_by(self, dr: int, dc: int) -> None:
        cur_r, cur_c = max(0, self.currentRow()), max(0, self.currentColumn())
        r = max(0, cur_r + dr)
        c = max(0, cur_c + dc)
        r, c = self._resolve_merge_move(cur_r, cur_c, r, c, dr, dc)
        self.setCurrentCell(r, c)
        self.scrollTo(self.currentIndex())

    def _resolve_merge_move(self, cur_r: int, cur_c: int,
                            r: int, c: int, dr: int, dc: int) -> tuple[int, int]:
        """Resolve a step by ``(dr, dc)`` so merged regions act as one cell.

        A merge occupies a single logical position (Excel semantics), so:

        * **Entering** a merge — the naive target lands in a region the cursor was
          *not* already in — snaps to that region's anchor (``setCurrentCell``
          does this), i.e. one keypress lands *on* the merge, not on a hidden
          interior cell.
        * **Exiting** a merge — the cursor started inside the region — steps to the
          cell just past the region's far edge in the travel direction, so the
          next keypress leaves the merge rather than re-snapping to its anchor and
          trapping the cursor.
        """
        sheet = self._win._doc.workbook.sheet
        start = sheet.merge_region(cur_r, cur_c)
        target = sheet.merge_region(r, c)
        # Leaving the merge we started in: jump past its far edge in the travel
        # direction so we actually exit (else setCurrentCell snaps us back).
        if start is not None and target == start:
            r1, c1, r2, c2 = start
            if dr > 0:
                return (r2 + dr, c)
            if dr < 0:
                return (max(0, r1 + dr), c)
            if dc > 0:
                return (r, c2 + dc)
            if dc < 0:
                return (r, max(0, c1 + dc))
        # Entering a (different) merge, or a plain move: setCurrentCell lands us
        # on the anchor when the target is inside a region.
        return (r, c)

    def closeEditor(self, editor, hint) -> None:  # noqa: N802 (Qt override)
        super().closeEditor(editor, hint)
        move, self._pending_move = self._pending_move, None
        if move is not None:
            self.move_cursor_by(*move)

    def _jump_edge(self, key) -> None:
        from ...core.navigation import jump_edge

        dr, dc = {Qt.Key.Key_Up: (-1, 0), Qt.Key.Key_Down: (1, 0),
                  Qt.Key.Key_Left: (0, -1), Qt.Key.Key_Right: (0, 1)}[key]
        populated = self._win._model.populated_cells()  # cached; rebuilt on mutation
        r, c = max(0, self.currentRow()), max(0, self.currentColumn())
        nr, nc = jump_edge(populated, r, c, dr, dc,
                           self.rowCount() - 1, self.columnCount() - 1)
        self.setCurrentCell(nr, nc)
        self.scrollTo(self.currentIndex())

    def _vim_on(self) -> bool:
        return bool(getattr(self._win._settings, "vim_mode", True))

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # While editing, the editor (and GridDelegate.eventFilter) own the keys.
        if self.state() == QAbstractItemView.State.EditingState:
            super().keyPressEvent(event)
            return
        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        text = event.text()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.move_cursor_by(-1 if shift else 1, 0)
            event.accept()
            return
        if key == Qt.Key.Key_Tab:
            self.move_cursor_by(0, 1)
            event.accept()
            return
        if key == Qt.Key.Key_Backtab:  # Shift+Tab arrives as Backtab
            self.move_cursor_by(0, -1)
            event.accept()
            return
        if key == Qt.Key.Key_F2:
            self.edit(self.currentIndex())
            event.accept()
            return
        if ctrl and key in (Qt.Key.Key_Up, Qt.Key.Key_Down,
                            Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._jump_edge(key)
            event.accept()
            return
        if key == Qt.Key.Key_Home:
            self.setCurrentCell(0, 0) if ctrl else \
                self.setCurrentCell(max(0, self.currentRow()), 0)
            self.scrollTo(self.currentIndex())
            event.accept()
            return
        if ctrl and key == Qt.Key.Key_End:
            ur, uc = self._win._doc.workbook.sheet.used_bounds()
            self.setCurrentCell(max(0, ur - 1), max(0, uc - 1))
            self.scrollTo(self.currentIndex())
            event.accept()
            return

        # Clipboard, owned directly by the view so it works regardless of the
        # menu shortcut's context (a focused editor or an ambiguous WindowShortcut
        # can otherwise swallow Ctrl+C/X/V). Qt only delivers these as a keypress
        # when the matching shortcut did NOT fire, so there is no double action.
        if ctrl and not shift and key == Qt.Key.Key_C:
            self._win.copy_selection()
            event.accept()
            return
        if ctrl and not shift and key == Qt.Key.Key_X:
            self._win.cut_selection()
            event.accept()
            return
        if ctrl and not shift and key == Qt.Key.Key_V:
            self._win.paste_at_cursor()
            event.accept()
            return

        # Keys the window owns — let them propagate (palette, vim, clear).
        if text == ":" or key == Qt.Key.Key_Delete:
            event.ignore()
            return
        if self._vim_on() and text in _VIM_KEYS:
            event.ignore()
            return
        super().keyPressEvent(event)
