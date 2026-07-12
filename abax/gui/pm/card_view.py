"""Card / Gallery view — responsive grid of task cards with sort and filter."""

from __future__ import annotations

from datetime import date
from typing import Any

from abax.core.pm.taskmodel import Task
from abax.gui._qtcompat import (
    QColor,
    QComboBox,
    QFont,
    QHBoxLayout,
    QLabel,
    QPainter,
    QRect,
    QRectF,
    QScrollArea,
    Qt,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)

from .common import TaskViewModel, paint_task_card

__all__ = ["CardView"]

_CARD_WIDTH = 220
_CARD_HEIGHT = 140
_GALLERY_CARD_WIDTH = 280
_GALLERY_CARD_HEIGHT = 220
_CARD_SPACING = 10
_COVER_HEIGHT = 60


# ---------------------------------------------------------------------------
# Flow layout — arranges children left-to-right, wrapping to the next row
# ---------------------------------------------------------------------------

class _FlowLayout(QVBoxLayout):
    """Minimal flow layout that wraps widgets into rows based on parent width.

    This is a simplified approach: it re-lays out child widgets into rows of
    QHBoxLayouts whenever the parent is resized.  Avoids the complexity of a
    full custom QLayout subclass while giving the responsive wrapping effect.
    """

    pass  # Marker; the CardView manages the re-flow manually.


# ---------------------------------------------------------------------------
# Single card widget
# ---------------------------------------------------------------------------

class _CardItemWidget(QWidget):
    """One card in the grid — painted with the shared card helper."""

    doubleClicked = pyqtSignal(int)

    def __init__(
        self,
        task: Task,
        *,
        gallery: bool = False,
        today: date | None = None,
        colors: dict[str, QColor] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._task = task
        self._gallery = gallery
        self._today = today
        self._colors = colors
        w, h = self._card_dims()
        self.setFixedSize(w, h)
        self.setAccessibleName(f"Card: {task.title}")

    @property
    def task(self) -> Task:
        return self._task

    def _card_dims(self) -> tuple[int, int]:
        if self._gallery:
            return _GALLERY_CARD_WIDTH, _GALLERY_CARD_HEIGHT
        return _CARD_WIDTH, _CARD_HEIGHT

    def set_gallery(self, gallery: bool) -> None:
        self._gallery = gallery
        w, h = self._card_dims()
        self.setFixedSize(w, h)
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._gallery:
            self._paint_cover(painter)
            card_rect = QRect(0, _COVER_HEIGHT, self.width(),
                              self.height() - _COVER_HEIGHT)
        else:
            card_rect = QRect(0, 0, self.width(), self.height())

        paint_task_card(
            painter, card_rect, self._task,
            today=self._today, colors=self._colors,
        )
        painter.end()

    def _paint_cover(self, painter: QPainter) -> None:
        """Gallery mode: coloured rectangle with large initials."""
        cover_rect = QRectF(1, 1, self.width() - 2, _COVER_HEIGHT - 1)
        # Derive a colour from the task title hash for visual variety.
        hue = (hash(self._task.assignee or self._task.title) % 360)
        bg = QColor.fromHsv(hue, 80, 200)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(cover_rect, 4, 4)

        initials = _initials(self._task.assignee or self._task.title)
        cover_font = QFont(painter.font())
        cover_font.setPointSizeF(cover_font.pointSizeF() * 2.0)
        cover_font.setBold(True)
        painter.setFont(cover_font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(cover_rect, Qt.AlignmentFlag.AlignCenter, initials)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        self.doubleClicked.emit(self._task.row)


def _initials(text: str) -> str:
    """Return up to two uppercase initials from *text*."""
    parts = text.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if parts:
        return parts[0][:2].upper()
    return "?"


# ---------------------------------------------------------------------------
# Sort/filter bar
# ---------------------------------------------------------------------------

_SORT_FIELDS = [
    ("Title", "title"),
    ("Status", "status"),
    ("Due", "due"),
    ("Assignee", "assignee"),
    ("Priority", "priority"),
]


class _ToolBar(QWidget):
    """Sort + filter controls at the top of the card grid."""

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        lay.addWidget(QLabel("Sort:"))
        self._sort = QComboBox()
        self._sort.setAccessibleName("Sort field")
        for label, key in _SORT_FIELDS:
            self._sort.addItem(label, key)
        self._sort.currentIndexChanged.connect(lambda _: self.changed.emit())
        lay.addWidget(self._sort)

        lay.addWidget(QLabel("Filter status:"))
        self._filter = QComboBox()
        self._filter.setAccessibleName("Status filter")
        self._filter.addItem("(all)", "")
        self._filter.currentIndexChanged.connect(lambda _: self.changed.emit())
        lay.addWidget(self._filter)

        lay.addStretch()

    @property
    def sort_key(self) -> str:
        return self._sort.currentData() or "title"

    @property
    def filter_status(self) -> str:
        return self._filter.currentData() or ""

    def set_statuses(self, statuses: list[str]) -> None:
        current = self._filter.currentData()
        self._filter.blockSignals(True)
        self._filter.clear()
        self._filter.addItem("(all)", "")
        for s in statuses:
            self._filter.addItem(s, s)
        if current:
            idx = self._filter.findData(current)
            if idx >= 0:
                self._filter.setCurrentIndex(idx)
        self._filter.blockSignals(False)


# ---------------------------------------------------------------------------
# CardView — the top-level widget
# ---------------------------------------------------------------------------

class CardView(QWidget):
    """Responsive card grid with optional gallery mode and sort/filter bar."""

    taskSelected = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Card view")
        self._model: TaskViewModel | None = None
        self._gallery = False
        self._today: date | None = date.today()
        self._colors: dict[str, QColor] | None = None
        self._card_widgets: list[_CardItemWidget] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._toolbar = _ToolBar()
        self._toolbar.changed.connect(self.refresh)
        outer.addWidget(self._toolbar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self._grid_container = QWidget()
        self._grid_container.setAccessibleName("Card grid")
        self._scroll.setWidget(self._grid_container)
        outer.addWidget(self._scroll)

    # -- Properties --

    @property
    def gallery(self) -> bool:
        return self._gallery

    @gallery.setter
    def gallery(self, value: bool) -> None:
        if self._gallery != value:
            self._gallery = value
            for cw in self._card_widgets:
                cw.set_gallery(value)
            self._reflow()

    def setModel(self, model: TaskViewModel) -> None:
        self._model = model
        self.refresh()

    def model(self) -> TaskViewModel | None:
        return self._model

    def card_widgets(self) -> list[_CardItemWidget]:
        return list(self._card_widgets)

    # -- Refresh / rebuild --

    def refresh(self) -> None:
        if self._model is None:
            return
        from abax.core.pm.taskmodel import STATUS_ORDER

        # Update status filter options.
        statuses = STATUS_ORDER(self._model.tasks)
        self._toolbar.set_statuses(statuses)

        # Filter.
        tasks = list(self._model.tasks)
        filt = self._toolbar.filter_status
        if filt:
            tasks = [t for t in tasks if t.status == filt]

        # Sort.
        sort_key = self._toolbar.sort_key
        tasks = _sort_tasks(tasks, sort_key)

        # Rebuild card widgets.
        for cw in self._card_widgets:
            cw.setParent(None)
            cw.deleteLater()
        self._card_widgets.clear()

        for task in tasks:
            cw = _CardItemWidget(
                task,
                gallery=self._gallery,
                today=self._today,
                colors=self._colors,
            )
            cw.doubleClicked.connect(self.taskSelected.emit)
            self._card_widgets.append(cw)

        self._reflow()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._reflow()

    def _reflow(self) -> None:
        """Lay out card widgets in a wrapping grid."""
        if not self._card_widgets:
            return
        card_w = _GALLERY_CARD_WIDTH if self._gallery else _CARD_WIDTH
        card_h = _GALLERY_CARD_HEIGHT if self._gallery else _CARD_HEIGHT
        avail_w = max(self._scroll.viewport().width(), card_w + _CARD_SPACING)
        cols = max(1, (avail_w + _CARD_SPACING) // (card_w + _CARD_SPACING))

        row = 0
        col = 0
        for cw in self._card_widgets:
            x = col * (card_w + _CARD_SPACING) + _CARD_SPACING
            y = row * (card_h + _CARD_SPACING) + _CARD_SPACING
            cw.setParent(self._grid_container)
            cw.move(x, y)
            cw.show()
            col += 1
            if col >= cols:
                col = 0
                row += 1

        total_rows = row + (1 if col > 0 else 0)
        total_h = total_rows * (card_h + _CARD_SPACING) + _CARD_SPACING
        self._grid_container.setMinimumHeight(total_h)


def _sort_tasks(tasks: list[Task], key: str) -> list[Task]:
    """Sort tasks by *key*, handling None values gracefully."""
    def _sortval(t: Task) -> Any:
        v = getattr(t, key, "")
        if v is None:
            return ""
        if isinstance(v, date):
            return v.isoformat()
        return str(v).lower()

    return sorted(tasks, key=_sortval)
