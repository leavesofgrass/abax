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
    QItemSelection,
    QItemSelectionModel,
    QLineEdit,
    QPainterPath,
    QPen,
    QPointF,
    QStyledItemDelegate,
    Qt,
    QTableView,
    QTableWidgetSelectionRange,
    pyqtSignal,
)

# Excel-style dynamic-array spill outline colour (a calm blue).
_SPILL_COLOR = "#3b82f6"

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
        the visual cues for a note and for a dynamic-array spill respectively."""
        super().paint(painter, option, index)
        sheet = self._win._doc.workbook.sheet
        if sheet.get_comment(index.row(), index.column()) is not None:
            self._paint_comment_marker(painter, option)
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
        return editor

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
        self.setModel(model)
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
        self.selectionModel().currentChanged.connect(self._emit_current_changed)

    # -- current-cell signal ----------------------------------------------

    def _emit_current_changed(self, cur, prev) -> None:
        self.currentCellChanged.emit(
            cur.row() if cur.isValid() else -1,
            cur.column() if cur.isValid() else -1,
            prev.row() if prev.isValid() else -1,
            prev.column() if prev.isValid() else -1)

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
        r = max(0, max(0, self.currentRow()) + dr)
        c = max(0, max(0, self.currentColumn()) + dc)
        self.setCurrentCell(r, c)
        self.scrollTo(self.currentIndex())

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
