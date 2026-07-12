"""Month-grid calendar view for the PM layer.

Displays tasks on their due dates, supports drag-to-reschedule, milestone
markers, today highlighting, multi-day span shading, and keyboard navigation.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any, Callable

from abax.core.pm.taskmodel import Task, write_task
from abax.gui._qtcompat import (
    QBrush,
    QColor,
    QDrag,
    QFont,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMimeData,
    QPainter,
    QPen,
    QPushButton,
    QRect,
    QSize,
    Qt,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)

__all__ = [
    "CalendarView",
    "DayCell",
]

_WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Colours (kept muted so they work on light and dark palettes).
_TODAY_BORDER = QColor(66, 133, 244)
_SPAN_BG = QColor(66, 133, 244, 30)
_MILESTONE_COLOR = QColor(220, 120, 20)
_TASK_TEXT = QColor(40, 40, 40)
_DAY_NUM_COLOR = QColor(100, 100, 100)
_OUTSIDE_MONTH_BG = QColor(240, 240, 240, 60)
_CELL_BORDER = QColor(210, 210, 210)
_DIAMOND = "◆"


# ------------------------------------------------------------------
# DayCell — one day in the month grid
# ------------------------------------------------------------------

class DayCell(QWidget):
    """A single day cell that paints its day number and task items."""

    taskDropped = pyqtSignal(int, object)  # task.row, new date
    taskDoubleClicked = pyqtSignal(int)  # task.row
    dayClicked = pyqtSignal(object)  # date

    def __init__(
        self,
        day_date: date | None,
        in_month: bool,
        parent: CalendarView | None = None,
    ) -> None:
        super().__init__(parent)
        self.day_date = day_date
        self.in_month = in_month
        self.tasks: list[Task] = []
        self._calendar_view: CalendarView | None = parent
        self._drag_start_pos = None

        self.setMinimumSize(QSize(80, 60))
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        if day_date is not None:
            self.setAccessibleName(f"Day {day_date.isoformat()}")
        else:
            self.setAccessibleName("Empty cell")

    # -- Tasks ----------------------------------------------------------

    def setTasks(self, tasks: list[Task]) -> None:
        self.tasks = list(tasks)
        self.update()

    def addTask(self, task: Task) -> None:
        self.tasks.append(task)
        self.update()

    # -- Painting -------------------------------------------------------

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        # Background
        if not self.in_month:
            painter.fillRect(rect, QBrush(_OUTSIDE_MONTH_BG))

        # Today highlight
        is_today = self.day_date == date.today()
        if is_today:
            pen = QPen(_TODAY_BORDER, 2)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

        # Span background (set externally by CalendarView)
        if getattr(self, "_span_highlight", False):
            painter.fillRect(rect.adjusted(2, 2, -2, -2), QBrush(_SPAN_BG))

        # Cell border
        painter.setPen(QPen(_CELL_BORDER, 0.5))
        painter.drawRect(rect)

        # Day number
        if self.day_date is not None:
            day_font = QFont()
            day_font.setPointSize(9)
            day_font.setBold(is_today)
            painter.setFont(day_font)
            painter.setPen(_TODAY_BORDER if is_today else _DAY_NUM_COLOR)
            painter.drawText(
                QRect(rect.x() + 4, rect.y() + 2, rect.width() - 8, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                str(self.day_date.day),
            )

        # Task items
        task_font = QFont()
        task_font.setPointSize(8)
        painter.setFont(task_font)
        y_offset = 20
        max_tasks = max(1, (rect.height() - 24) // 14)
        for i, task in enumerate(self.tasks):
            if i >= max_tasks:
                painter.setPen(_DAY_NUM_COLOR)
                remaining = len(self.tasks) - max_tasks
                painter.drawText(
                    QRect(rect.x() + 4, rect.y() + y_offset, rect.width() - 8, 14),
                    Qt.AlignmentFlag.AlignLeft,
                    f"+{remaining} more",
                )
                break
            painter.setPen(_TASK_TEXT)
            prefix = f"{_DIAMOND} " if task.milestone else ""
            title = prefix + task.title
            # Truncate
            avail_width = rect.width() - 10
            metrics = painter.fontMetrics()
            elided = metrics.elidedText(
                title, Qt.TextElideMode.ElideRight, avail_width
            )
            painter.drawText(
                QRect(rect.x() + 4, rect.y() + y_offset, rect.width() - 8, 14),
                Qt.AlignmentFlag.AlignLeft,
                elided,
            )
            y_offset += 14

        painter.end()

    # -- Drag-and-drop (source) -----------------------------------------

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.tasks:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        if (
            self._drag_start_pos is not None
            and (event.pos() - self._drag_start_pos).manhattanLength() > 10
        ):
            task = self._task_at_pos(self._drag_start_pos)
            if task is not None:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(str(task.row))
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.MoveAction)
            self._drag_start_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
        self._drag_start_pos = None
        if event.button() == Qt.MouseButton.LeftButton and self.day_date is not None:
            task = self._task_at_pos(event.pos())
            if task is None:
                self.dayClicked.emit(self.day_date)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: Any) -> None:  # noqa: N802
        task = self._task_at_pos(event.pos())
        if task is not None:
            self.taskDoubleClicked.emit(task.row)
        super().mouseDoubleClickEvent(event)

    # -- Drag-and-drop (target) -----------------------------------------

    def dragEnterEvent(self, event: Any) -> None:  # noqa: N802
        if event.mimeData().hasText() and self.day_date is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: Any) -> None:  # noqa: N802
        if event.mimeData().hasText() and self.day_date is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: Any) -> None:  # noqa: N802
        if self.day_date is None:
            event.ignore()
            return
        text = event.mimeData().text()
        try:
            task_row = int(text)
        except (ValueError, TypeError):
            event.ignore()
            return
        event.acceptProposedAction()
        self.taskDropped.emit(task_row, self.day_date)

    # -- Helpers --------------------------------------------------------

    def _task_at_pos(self, pos: Any) -> Task | None:
        """Return the task under *pos*, or None."""
        y = pos.y()
        if y < 20 or not self.tasks:
            return None
        idx = (y - 20) // 14
        if 0 <= idx < len(self.tasks):
            return self.tasks[idx]
        return None


# ------------------------------------------------------------------
# CalendarView — the full month-grid widget
# ------------------------------------------------------------------

class CalendarView(QWidget):
    """Month-grid calendar displaying tasks on their due dates."""

    taskSelected = pyqtSignal(int)  # task.row
    newTaskRequested = pyqtSignal(object)  # date

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tasks: list[Task] = []
        self._year: int = date.today().year
        self._month: int = date.today().month
        self._sheet: Any = None
        self._col_map: dict[str, int] = {}
        self._first_col: int = 0
        self._on_set: Callable[..., Any] | None = None

        self._day_cells: list[DayCell] = []
        self._focused_cell_index: int = -1

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Calendar view")

        self._build_ui()
        self._populate_grid()

    # -- Public API -----------------------------------------------------

    def setTasks(self, tasks: list[Task]) -> None:  # noqa: N802
        self._tasks = list(tasks)
        self._populate_grid()

    def setContext(  # noqa: N802
        self,
        sheet: Any,
        col_map: dict[str, int],
        first_col: int,
        on_set: Callable[..., Any] | None,
    ) -> None:
        self._sheet = sheet
        self._col_map = col_map
        self._first_col = first_col
        self._on_set = on_set

    def setSheet(self, sheet: Any) -> None:  # noqa: N802
        self._sheet = sheet

    def setColMap(self, col_map: dict[str, int]) -> None:  # noqa: N802
        self._col_map = col_map

    def setFirstCol(self, first_col: int) -> None:  # noqa: N802
        self._first_col = first_col

    def setOnSet(self, callback: Callable[..., Any] | None) -> None:  # noqa: N802
        self._on_set = callback

    def setDate(self, year: int, month: int) -> None:  # noqa: N802
        self._year = year
        self._month = month
        self._month_label.setText(f"{calendar.month_name[month]} {year}")
        self._populate_grid()

    def refresh(self) -> None:
        self._populate_grid()

    def tasks_on_date(self, d: date) -> list[Task]:
        """Return tasks whose due date matches *d*."""
        return [t for t in self._tasks if t.due == d]

    def currentYear(self) -> int:  # noqa: N802
        return self._year

    def currentMonth(self) -> int:  # noqa: N802
        return self._month

    # -- UI construction ------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(2)

        # Header row: ← Month Year →
        header = QHBoxLayout()
        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedSize(28, 28)
        self._prev_btn.setAccessibleName("Previous month")
        self._prev_btn.clicked.connect(self._go_prev)

        self._month_label = QLabel()
        self._month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        month_font = QFont()
        month_font.setPointSize(12)
        month_font.setBold(True)
        self._month_label.setFont(month_font)
        self._month_label.setText(
            f"{calendar.month_name[self._month]} {self._year}"
        )
        self._month_label.setAccessibleName("Current month")

        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedSize(28, 28)
        self._next_btn.setAccessibleName("Next month")
        self._next_btn.clicked.connect(self._go_next)

        header.addWidget(self._prev_btn)
        header.addStretch()
        header.addWidget(self._month_label)
        header.addStretch()
        header.addWidget(self._next_btn)
        root.addLayout(header)

        # Weekday labels
        weekday_row = QHBoxLayout()
        weekday_row.setSpacing(2)
        for name in _WEEKDAY_NAMES:
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wf = QFont()
            wf.setPointSize(9)
            wf.setBold(True)
            lbl.setFont(wf)
            lbl.setAccessibleName(f"Weekday {name}")
            weekday_row.addWidget(lbl, stretch=1)
        root.addLayout(weekday_row)

        # Grid container
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(1)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._grid_widget, stretch=1)

    # -- Grid population ------------------------------------------------

    def _populate_grid(self) -> None:
        # Clear existing cells
        for cell in self._day_cells:
            cell.setParent(None)
            cell.deleteLater()
        self._day_cells.clear()

        cal = calendar.Calendar(firstweekday=0)  # Monday first
        weeks = cal.monthdatescalendar(self._year, self._month)

        # Precompute span dates (tasks with both start and due spanning days)
        span_dates: set[date] = set()
        for task in self._tasks:
            if task.start and task.due and task.start < task.due:
                d = task.start
                while d <= task.due:
                    span_dates.add(d)
                    d += timedelta(days=1)

        # Build day-to-tasks map
        day_tasks: dict[date, list[Task]] = {}
        for task in self._tasks:
            if task.due is not None:
                day_tasks.setdefault(task.due, []).append(task)

        for row_idx, week in enumerate(weeks):
            for col_idx, day_date in enumerate(week):
                in_month = day_date.month == self._month
                cell = DayCell(day_date, in_month, parent=self)
                cell.setTasks(day_tasks.get(day_date, []))
                cell._span_highlight = day_date in span_dates

                # Wire signals
                cell.taskDropped.connect(self._on_task_dropped)
                cell.taskDoubleClicked.connect(self.taskSelected.emit)
                cell.dayClicked.connect(self.newTaskRequested.emit)

                self._grid_layout.addWidget(cell, row_idx, col_idx)
                self._day_cells.append(cell)

        self._focused_cell_index = -1
        self.update()

    # -- Navigation -----------------------------------------------------

    def _go_prev(self) -> None:
        if self._month == 1:
            self.setDate(self._year - 1, 12)
        else:
            self.setDate(self._year, self._month - 1)

    def _go_next(self) -> None:
        if self._month == 12:
            self.setDate(self._year + 1, 1)
        else:
            self.setDate(self._year, self._month + 1)

    # -- Drag-and-drop handling -----------------------------------------

    def _on_task_dropped(self, task_row: int, new_date: date) -> None:
        task = self._find_task_by_row(task_row)
        if task is None:
            return
        task.due = new_date
        write_task(
            self._sheet,
            task,
            "due",
            new_date,
            col_map=self._col_map,
            first_col=self._first_col,
            on_set=self._on_set,
        )
        self._populate_grid()

    def _find_task_by_row(self, row: int) -> Task | None:
        for task in self._tasks:
            if task.row == row:
                return task
        return None

    # -- Keyboard navigation --------------------------------------------

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_PageUp:
            self._go_prev()
            return
        if key == Qt.Key.Key_PageDown:
            self._go_next()
            return

        if not self._day_cells:
            super().keyPressEvent(event)
            return

        num_cols = 7
        total = len(self._day_cells)
        idx = self._focused_cell_index

        if key == Qt.Key.Key_Left:
            idx = max(0, idx - 1) if idx >= 0 else 0
        elif key == Qt.Key.Key_Right:
            idx = min(total - 1, idx + 1) if idx >= 0 else 0
        elif key == Qt.Key.Key_Up:
            idx = max(0, idx - num_cols) if idx >= 0 else 0
        elif key == Qt.Key.Key_Down:
            idx = min(total - 1, idx + num_cols) if idx >= 0 else 0
        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            if 0 <= idx < total:
                cell = self._day_cells[idx]
                if cell.tasks:
                    self.taskSelected.emit(cell.tasks[0].row)
                elif cell.day_date is not None:
                    self.newTaskRequested.emit(cell.day_date)
            return
        else:
            super().keyPressEvent(event)
            return

        self._focused_cell_index = idx
        if 0 <= idx < total:
            self._day_cells[idx].setFocus()

    # -- Size hint ------------------------------------------------------

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(600, 500)
