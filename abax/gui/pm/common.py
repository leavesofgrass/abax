"""Shared infrastructure for PM views — model adapter, card painter, MIME type."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from abax.core.pm.taskmodel import (
    Task,
    detect_columns,
    parse_tasks,
    write_task,
)
from abax.gui._qtcompat import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QRect,
    QRectF,
    Qt,
)

__all__ = [
    "TASK_MIME_TYPE",
    "TaskViewModel",
    "paint_task_card",
    "write_field",
]

TASK_MIME_TYPE = "application/x-abax-pm-task"


class TaskViewModel:
    """Adapter that holds a parsed task list and the write-back context.

    The integrator wires *on_set* to the window's commit path so every
    mutation goes through undo/recording.
    """

    def __init__(
        self,
        sheet: Any,
        *,
        header_row: int = 0,
        first_col: int = 0,
        last_col: int | None = None,
        first_data_row: int | None = None,
        last_data_row: int | None = None,
        on_set: Callable[[Any, int, int, Any], None] | None = None,
    ) -> None:
        self.sheet = sheet
        self.header_row = header_row
        self.first_col = first_col
        self.last_col = last_col
        self.first_data_row = first_data_row
        self.last_data_row = last_data_row
        self.on_set = on_set

        self.col_map: dict[str, int] = {}
        self.tasks: list[Task] = []
        self.refresh()

    def refresh(self) -> None:
        """Re-parse tasks from the sheet and rebuild the column map."""
        if self.last_col is None:
            _, ncols = self.sheet.used_bounds()
            effective_last = ncols - 1
        else:
            effective_last = self.last_col
        width = effective_last - self.first_col + 1
        if width <= 0:
            self.col_map = {}
            self.tasks = []
            return
        headers = [
            str(v) if v is not None else ""
            for v in [
                self.sheet.get_value(self.header_row, self.first_col + c)
                for c in range(width)
            ]
        ]
        self.col_map = detect_columns(headers)
        self.tasks = parse_tasks(
            self.sheet,
            header_row=self.header_row,
            first_col=self.first_col,
            last_col=effective_last,
            first_data_row=self.first_data_row,
            last_data_row=self.last_data_row,
        )


def write_field(
    model: TaskViewModel,
    task: Task,
    field: str,
    value: Any,
) -> None:
    """Write one field through the model's write-back context, then refresh."""
    write_task(
        model.sheet,
        task,
        field,
        value,
        col_map=model.col_map,
        first_col=model.first_col,
        on_set=model.on_set,
    )
    setattr(task, field, value)
    model.refresh()


# ---------------------------------------------------------------------------
# Card painting
# ---------------------------------------------------------------------------

_CARD_PADDING = 6
_PROGRESS_HEIGHT = 4


def paint_task_card(
    painter: QPainter,
    rect: QRect | QRectF,
    task: Task,
    *,
    today: date | None = None,
    colors: dict[str, QColor] | None = None,
) -> None:
    """Paint a task card within *rect*.

    *colors* keys (all optional, theme-derived by the caller):
        ``"card_bg"``, ``"card_border"``, ``"title_fg"``, ``"subtitle_fg"``,
        ``"overdue_fg"``, ``"progress_bg"``, ``"progress_fg"``,
        ``"priority_bg"``, ``"priority_fg"``.

    If *colors* is ``None`` the painter's current palette is used for
    reasonable defaults.
    """
    c = colors or {}
    # Fallback palette-based colours when the caller doesn't supply them.
    _card_bg = c.get("card_bg", QColor(255, 255, 255))
    _card_border = c.get("card_border", QColor(200, 200, 200))
    _title_fg = c.get("title_fg", QColor(0, 0, 0))
    _subtitle_fg = c.get("subtitle_fg", QColor(100, 100, 100))
    _overdue_fg = c.get("overdue_fg", QColor(200, 0, 0))
    _progress_bg = c.get("progress_bg", QColor(220, 220, 220))
    _progress_fg = c.get("progress_fg", QColor(76, 175, 80))
    _priority_bg = c.get("priority_bg", QColor(255, 193, 7))
    _priority_fg = c.get("priority_fg", QColor(0, 0, 0))

    r = QRectF(rect) if isinstance(rect, QRect) else rect
    painter.save()

    # Card background + border.
    painter.setPen(QPen(_card_border, 1))
    painter.setBrush(_card_bg)
    painter.drawRoundedRect(r.adjusted(1, 1, -1, -1), 4, 4)

    inner = r.adjusted(
        _CARD_PADDING + 1, _CARD_PADDING + 1,
        -_CARD_PADDING - 1, -_CARD_PADDING - 1,
    )
    y = inner.top()

    # Title (bold).
    title_font = QFont(painter.font())
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(_title_fg)
    title_rect = QRectF(inner.left(), y, inner.width(), inner.height())
    br = painter.boundingRect(
        title_rect, Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
        task.title,
    )
    painter.drawText(
        QRectF(inner.left(), y, inner.width(), br.height()),
        Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
        task.title,
    )
    y += br.height() + 2

    # Subtitle font for assignee / due / priority.
    sub_font = QFont(painter.font())
    sub_font.setBold(False)
    sub_font.setPointSizeF(sub_font.pointSizeF() * 0.9)
    painter.setFont(sub_font)

    # Assignee.
    if task.assignee:
        painter.setPen(_subtitle_fg)
        painter.drawText(
            QRectF(inner.left(), y, inner.width(), 16),
            Qt.AlignmentFlag.AlignLeft,
            task.assignee,
        )
        y += 16

    # Due date (red if overdue).
    if task.due:
        is_overdue = today is not None and task.due < today
        painter.setPen(_overdue_fg if is_overdue else _subtitle_fg)
        painter.drawText(
            QRectF(inner.left(), y, inner.width(), 16),
            Qt.AlignmentFlag.AlignLeft,
            f"Due: {task.due.isoformat()}",
        )
        y += 16

    # Priority chip.
    if task.priority:
        fm = painter.fontMetrics()
        chip_w = fm.horizontalAdvance(task.priority) + 10
        chip_h = fm.height() + 4
        chip_rect = QRectF(inner.left(), y, chip_w, chip_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_priority_bg)
        painter.drawRoundedRect(chip_rect, 3, 3)
        painter.setPen(_priority_fg)
        painter.drawText(chip_rect, Qt.AlignmentFlag.AlignCenter, task.priority)
        y += chip_h + 2

    # Progress bar.
    if task.percent_done > 0:
        bar_top = max(y, inner.bottom() - _PROGRESS_HEIGHT - 2)
        bar_rect = QRectF(inner.left(), bar_top, inner.width(), _PROGRESS_HEIGHT)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_progress_bg)
        painter.drawRect(bar_rect)
        fill_w = inner.width() * (task.percent_done / 100.0)
        painter.setBrush(_progress_fg)
        painter.drawRect(QRectF(inner.left(), bar_top, fill_w, _PROGRESS_HEIGHT))

    painter.restore()
