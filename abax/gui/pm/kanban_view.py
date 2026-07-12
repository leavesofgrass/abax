"""Kanban board view — status columns with draggable task cards."""

from __future__ import annotations

from datetime import date
from typing import Any

from abax.core.pm.taskmodel import STATUS_ORDER, Task
from abax.gui._qtcompat import (
    QColor,
    QDrag,
    QFont,
    QHBoxLayout,
    QLabel,
    QMimeData,
    QPainter,
    QRect,
    QScrollArea,
    QSize,
    Qt,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)

from .common import TASK_MIME_TYPE, TaskViewModel, paint_task_card, write_field

__all__ = ["KanbanView"]

_CARD_HEIGHT = 120
_CARD_MARGIN = 6
_COLUMN_MIN_WIDTH = 200


# ---------------------------------------------------------------------------
# Individual card widget
# ---------------------------------------------------------------------------

class _CardWidget(QWidget):
    """A single task card that supports painting, double-click, and drag."""

    doubleClicked = pyqtSignal(int)  # task.row

    def __init__(self, task: Task, *, today: date | None = None,
                 colors: dict[str, QColor] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task = task
        self._today = today
        self._colors = colors
        self.setMinimumHeight(_CARD_HEIGHT)
        self.setMaximumHeight(_CARD_HEIGHT)
        self.setSizePolicy(
            QWidget().sizePolicy()  # type: ignore[arg-type]
        )
        self.setAccessibleName(f"Task card: {task.title}")
        self._drag_start = None

    @property
    def task(self) -> Task:
        return self._task

    def sizeHint(self) -> QSize:
        return QSize(_COLUMN_MIN_WIDTH - 2 * _CARD_MARGIN, _CARD_HEIGHT)

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_task_card(
            painter,
            QRect(0, 0, self.width(), self.height()),
            self._task,
            today=self._today,
            colors=self._colors,
        )
        painter.end()

    def mouseDoubleClickEvent(self, event: Any) -> None:
        self.doubleClicked.emit(self._task.row)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:
        if (self._drag_start is not None
                and (event.pos() - self._drag_start).manhattanLength() > 10):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(TASK_MIME_TYPE, self._task.id.encode("utf-8"))
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)
            self._drag_start = None
        super().mouseMoveEvent(event)


# ---------------------------------------------------------------------------
# Column widget (one per status)
# ---------------------------------------------------------------------------

class _ColumnWidget(QWidget):
    """A vertical lane for one status — header + scrollable card list."""

    cardDropped = pyqtSignal(str, str)  # (task_id, new_status)

    def __init__(self, status: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = status
        self.setAcceptDrops(True)
        self.setAccessibleName(f"Kanban column: {status}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self._header = QLabel(status)
        header_font = QFont(self._header.font())
        header_font.setBold(True)
        self._header.setFont(header_font)
        self._header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(_CARD_MARGIN)
        self._inner_layout.addStretch()
        self._scroll.setWidget(self._inner)
        layout.addWidget(self._scroll)

        self.setMinimumWidth(_COLUMN_MIN_WIDTH)
        self._cards: list[_CardWidget] = []

    @property
    def status(self) -> str:
        return self._status

    @property
    def cards(self) -> list[_CardWidget]:
        return list(self._cards)

    def set_header_count(self, count: int) -> None:
        self._header.setText(f"{self._status} ({count})")

    def add_card(self, card: _CardWidget) -> None:
        self._cards.append(card)
        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1, card,
        )

    def clear_cards(self) -> None:
        for card in self._cards:
            self._inner_layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

    # -- Drag-and-drop target --

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasFormat(TASK_MIME_TYPE):
            event.acceptProposedAction()

    def dragMoveEvent(self, event: Any) -> None:
        if event.mimeData().hasFormat(TASK_MIME_TYPE):
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:
        mime = event.mimeData()
        if mime.hasFormat(TASK_MIME_TYPE):
            task_id = bytes(mime.data(TASK_MIME_TYPE)).decode("utf-8")
            self.cardDropped.emit(task_id, self._status)
            event.acceptProposedAction()


# ---------------------------------------------------------------------------
# KanbanView — the top-level widget
# ---------------------------------------------------------------------------

class KanbanView(QWidget):
    """Kanban board: one column per status, cards draggable between columns."""

    taskSelected = pyqtSignal(int)  # task sheet row

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Kanban view")
        self._model: TaskViewModel | None = None
        self._columns: list[_ColumnWidget] = []
        self._focused_col = 0
        self._focused_card = 0
        self._today: date | None = date.today()
        self._colors: dict[str, QColor] | None = None

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(6)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def setModel(self, model: TaskViewModel) -> None:
        self._model = model
        self.refresh()

    def model(self) -> TaskViewModel | None:
        return self._model

    def columns(self) -> list[_ColumnWidget]:
        return list(self._columns)

    def refresh(self) -> None:
        if self._model is None:
            return
        # Clear existing columns.
        for col in self._columns:
            self._layout.removeWidget(col)
            col.setParent(None)
            col.deleteLater()
        self._columns.clear()

        statuses = STATUS_ORDER(self._model.tasks)
        tasks_by_status: dict[str, list[Task]] = {s: [] for s in statuses}
        for task in self._model.tasks:
            bucket = tasks_by_status.get(task.status)
            if bucket is not None:
                bucket.append(task)

        for status in statuses:
            col = _ColumnWidget(status)
            col.cardDropped.connect(self._on_card_dropped)
            task_list = tasks_by_status[status]
            col.set_header_count(len(task_list))
            for task in task_list:
                card = _CardWidget(
                    task, today=self._today, colors=self._colors,
                )
                card.doubleClicked.connect(self.taskSelected.emit)
                col.add_card(card)
            self._columns.append(col)
            self._layout.addWidget(col)

        self._focused_col = 0
        self._focused_card = 0

    def _on_card_dropped(self, task_id: str, new_status: str) -> None:
        if self._model is None:
            return
        for task in self._model.tasks:
            if task.id == task_id:
                write_field(self._model, task, "status", new_status)
                self.refresh()
                return

    # -- Keyboard navigation --

    def keyPressEvent(self, event: Any) -> None:
        key = event.key()
        if key == Qt.Key.Key_Right:
            self._move_focus(col_delta=1)
        elif key == Qt.Key.Key_Left:
            self._move_focus(col_delta=-1)
        elif key == Qt.Key.Key_Down:
            self._move_focus(card_delta=1)
        elif key == Qt.Key.Key_Up:
            self._move_focus(card_delta=-1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._activate_focused()
        else:
            super().keyPressEvent(event)

    def _move_focus(
        self, *, col_delta: int = 0, card_delta: int = 0,
    ) -> None:
        if not self._columns:
            return
        self._focused_col = max(
            0, min(self._focused_col + col_delta, len(self._columns) - 1),
        )
        cards = self._columns[self._focused_col].cards
        if cards:
            self._focused_card = max(
                0, min(self._focused_card + card_delta, len(cards) - 1),
            )
        else:
            self._focused_card = 0

    def _activate_focused(self) -> None:
        if not self._columns:
            return
        col = self._columns[self._focused_col]
        cards = col.cards
        if cards and 0 <= self._focused_card < len(cards):
            self.taskSelected.emit(cards[self._focused_card].task.row)
