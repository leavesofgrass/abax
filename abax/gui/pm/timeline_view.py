"""Horizontal-lane timeline view for project management.

Groups tasks by a configurable field (default ``assignee``) and displays
them as bars inside swim-lanes.  Items are draggable between lanes —
dropping a task into a different lane writes the lane field via
``write_task`` for undo support.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from abax.core.pm.taskmodel import Task, write_task
from abax.gui._qtcompat import (
    QColor,
    QComboBox,
    QFont,
    QHBoxLayout,
    QLabel,
    QPainter,
    QPainterPath,
    QPen,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QToolTip,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)

__all__ = ["TimelineView"]

# ── Layout constants ──────────────────────────────────────────────────
_PPD: dict[str, int] = {"day": 40, "week": 10, "month": 3}
_ROW_H = 28
_LANE_HDR_H = 24
_HDR_H = 40
_LIST_W = 160
_BAR_H = 18
_PAD_DAYS = 7

# ── Palette ───────────────────────────────────────────────────────────
_C_BAR = QColor(70, 130, 180)
_C_MILE = QColor(180, 150, 40)
_C_GRID = QColor(230, 230, 230)
_C_HDR = QColor(245, 245, 245)
_C_LANE_BG = QColor(250, 250, 252)
_C_LANE_ALT = QColor(242, 244, 248)
_C_LANE_LBL = QColor(80, 80, 80)
_C_TEXT = QColor(50, 50, 50)
_C_BG = QColor(255, 255, 255)
_C_DIV = QColor(180, 180, 180)
_C_TODAY = QColor(255, 80, 80)
_C_PROG = QColor(40, 80, 120)

# Visual row types
_VR_LANE = "lane"
_VR_TASK = "task"


class _TimelineCanvas(QWidget):
    """Virtualized, custom-painted timeline body."""

    def __init__(self, view: TimelineView) -> None:
        super().__init__(view)
        self._v = view
        self._hoff = 0
        self._voff = 0
        self._drag_idx: int | None = None
        self._drag_orig_lane: str | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Timeline canvas")

    # ── coordinate helpers ────────────────────────────────────────────

    def _ppd(self) -> int:
        return _PPD[self._v._zoom]

    def _date_x(self, d: date) -> float:
        if self._v._date_start is None:
            return 0.0
        return _LIST_W + (d - self._v._date_start).days * self._ppd() - self._hoff

    def _row_y(self, vr: int) -> float:
        y = float(_HDR_H)
        rows = self._v._vrows
        for i in range(min(vr, len(rows))):
            rtype = rows[i][0]
            y += _LANE_HDR_H if rtype == _VR_LANE else _ROW_H
        return y - self._voff

    def _row_height(self, vr: int) -> float:
        if vr < len(self._v._vrows) and self._v._vrows[vr][0] == _VR_LANE:
            return _LANE_HDR_H
        return _ROW_H

    def _vrow_at_y(self, py: float) -> int | None:
        y = float(_HDR_H) - self._voff
        for i, (rtype, _label, _ti) in enumerate(self._v._vrows):
            rh = _LANE_HDR_H if rtype == _VR_LANE else _ROW_H
            if y <= py < y + rh:
                return i
            y += rh
        return None

    def _lane_at_y(self, py: float) -> str | None:
        """Return the lane label for the visual row at *py*."""
        vr = self._vrow_at_y(py)
        if vr is None or vr >= len(self._v._vrows):
            return None
        return self._v._vrows[vr][1]

    # ── painting ──────────────────────────────────────────────────────

    def paintEvent(self, event: Any) -> None:  # noqa: ARG002
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(QRectF(0, 0, w, h), _C_BG)

        if not self._v._vrows:
            p.end()
            return

        # Header
        p.fillRect(QRectF(0, 0, w, _HDR_H), _C_HDR)
        self._paint_header(p, w)

        # Body clip
        p.save()
        p.setClipRect(QRectF(0, _HDR_H, w, h - _HDR_H))

        # Divider
        p.setPen(QPen(_C_DIV))
        p.drawLine(QPointF(_LIST_W, _HDR_H), QPointF(_LIST_W, h))

        # Visible rows (approximate — walk from first potentially-visible)
        self._paint_rows(p, w, h)

        # Today line
        if self._v._today is not None:
            tx = self._date_x(self._v._today)
            if _LIST_W <= tx <= w:
                p.setPen(QPen(_C_TODAY, 2, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(tx, _HDR_H), QPointF(tx, h))

        p.restore()
        p.end()

    def _paint_header(self, p: QPainter, w: int) -> None:
        ds = self._v._date_start
        de = self._v._date_end
        if ds is None or de is None:
            return
        ppd = self._ppd()
        total = (de - ds).days + 1
        view_w = w - _LIST_W
        if view_w <= 0:
            return

        first_d = max(0, self._hoff // ppd)
        last_d = min(total, (self._hoff + view_w) // ppd + 2)

        font = QFont()
        font.setPointSize(8)
        p.setFont(font)
        p.setPen(QPen(_C_TEXT))
        zoom = self._v._zoom

        if zoom == "day":
            for i in range(first_d, last_d):
                d = ds + timedelta(days=i)
                x = _LIST_W + i * ppd - self._hoff
                p.drawText(
                    QRectF(x, 2, ppd, _HDR_H - 4),
                    Qt.AlignmentFlag.AlignCenter,
                    d.strftime("%d"),
                )
        elif zoom == "week":
            seen: set[tuple[int, int]] = set()
            for i in range(first_d, last_d):
                d = ds + timedelta(days=i)
                wk = d.isocalendar()[:2]
                if wk not in seen and d.weekday() == 0:
                    seen.add(wk)
                    x = _LIST_W + i * ppd - self._hoff
                    p.drawText(
                        QRectF(x, 2, 7 * ppd, _HDR_H - 4),
                        Qt.AlignmentFlag.AlignCenter,
                        d.strftime("%b %d"),
                    )
        else:
            import calendar

            seen_m: set[tuple[int, int]] = set()
            for i in range(first_d, last_d):
                d = ds + timedelta(days=i)
                mk = (d.year, d.month)
                if mk not in seen_m and d.day == 1:
                    seen_m.add(mk)
                    x = _LIST_W + i * ppd - self._hoff
                    dim = calendar.monthrange(d.year, d.month)[1]
                    p.drawText(
                        QRectF(x, 2, dim * ppd, _HDR_H - 4),
                        Qt.AlignmentFlag.AlignCenter,
                        d.strftime("%b %Y"),
                    )

    def _paint_rows(self, p: QPainter, w: int, h: int) -> None:
        vrows = self._v._vrows
        tasks = self._v._tasks
        font_lane = QFont()
        font_lane.setPointSize(9)
        font_lane.setBold(True)
        font_task = QFont()
        font_task.setPointSize(9)

        y = float(_HDR_H) - self._voff
        lane_idx = 0
        for vr_i, (rtype, label, ti) in enumerate(vrows):
            rh = _LANE_HDR_H if rtype == _VR_LANE else _ROW_H
            bottom = y + rh
            if bottom < _HDR_H:
                y = bottom
                if rtype == _VR_LANE:
                    lane_idx += 1
                continue
            if y > h:
                break

            if rtype == _VR_LANE:
                bg = _C_LANE_BG if lane_idx % 2 == 0 else _C_LANE_ALT
                p.fillRect(QRectF(0, y, w, rh), bg)
                p.setPen(QPen(_C_LANE_LBL))
                p.setFont(font_lane)
                p.drawText(
                    QRectF(4, y, _LIST_W - 8, rh),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    label,
                )
                lane_idx += 1
            else:
                task = tasks[ti]
                p.setPen(QPen(_C_TEXT))
                p.setFont(font_task)
                p.drawText(
                    QRectF(12, y, _LIST_W - 16, rh),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    task.title,
                )
                self._paint_task_bar(p, task, y, rh)

            # Grid line
            p.setPen(QPen(_C_GRID))
            p.drawLine(QPointF(0, bottom), QPointF(w, bottom))

            y = bottom

    def _paint_task_bar(self, p: QPainter, task: Task, y: float, rh: float) -> None:
        if task.start is None or task.due is None:
            if task.milestone and task.start is not None:
                self._paint_milestone(p, task, y, rh)
            return
        if task.milestone:
            self._paint_milestone(p, task, y, rh)
            return
        x1 = self._date_x(task.start)
        x2 = self._date_x(task.due + timedelta(days=1))
        bar_y = y + (rh - _BAR_H) / 2
        r = QRectF(x1, bar_y, max(x2 - x1, 2.0), _BAR_H)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_C_BAR)
        p.drawRoundedRect(r, 3, 3)

        if task.percent_done > 0:
            pw = r.width() * min(task.percent_done, 1.0)
            p.setBrush(_C_PROG)
            p.drawRoundedRect(QRectF(r.left(), r.top(), pw, r.height()), 3, 3)

    def _paint_milestone(self, p: QPainter, task: Task, y: float, rh: float) -> None:
        if task.start is None:
            return
        cx = self._date_x(task.start)
        cy = y + rh / 2
        s = _BAR_H / 2
        path = QPainterPath()
        path.moveTo(QPointF(cx, cy - s))
        path.lineTo(QPointF(cx + s, cy))
        path.lineTo(QPointF(cx, cy + s))
        path.lineTo(QPointF(cx - s, cy))
        path.closeSubpath()
        p.setPen(QPen(_C_MILE.darker(120), 1))
        p.setBrush(_C_MILE)
        p.drawPath(path)

    # ── mouse interaction ─────────────────────────────────────────────

    def wheelEvent(self, event: Any) -> None:
        dy = event.angleDelta().y()
        dx = event.angleDelta().x()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._hoff = max(0, self._hoff - dy)
        elif dx:
            self._hoff = max(0, self._hoff - dx)
        else:
            self._voff = max(0, self._voff - dy)
        self.update()

    def mousePressEvent(self, event: Any) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        vr = self._vrow_at_y(pos.y())
        if vr is None or vr >= len(self._v._vrows):
            return
        rtype, label, ti = self._v._vrows[vr]
        if rtype != _VR_TASK or ti is None:
            return
        self._drag_idx = ti
        self._drag_orig_lane = label

    def mouseMoveEvent(self, event: Any) -> None:
        pos = event.position().toPoint()
        if self._drag_idx is not None:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        vr = self._vrow_at_y(pos.y())
        if vr is not None and vr < len(self._v._vrows):
            rtype, _label, ti = self._v._vrows[vr]
            if rtype == _VR_TASK and ti is not None:
                task = self._v._tasks[ti]
                parts = [task.title]
                if task.start:
                    parts.append(f"Start: {task.start}")
                if task.due:
                    parts.append(f"Due: {task.due}")
                if task.assignee:
                    parts.append(f"Assignee: {task.assignee}")
                QToolTip.showText(event.globalPosition().toPoint(), "\n".join(parts), self)
                return
        QToolTip.hideText()
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: ARG002
        if self._drag_idx is None:
            return
        pos = event.position().toPoint()
        new_lane = self._lane_at_y(pos.y())
        task = self._v._tasks[self._drag_idx]
        if new_lane is not None and new_lane != self._drag_orig_lane:
            field = self._v._lane_field
            setattr(task, field, new_lane)
            if self._v._sheet is not None and self._v._col_map is not None:
                write_task(
                    self._v._sheet, task, field, new_lane,
                    col_map=self._v._col_map,
                    first_col=self._v._first_col,
                    on_set=self._v._on_set,
                )
            self._v._compute_lanes()
            self._v._build_vrows()
            self.update()
        self._drag_idx = None
        self._drag_orig_lane = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        pos = event.position().toPoint()
        vr = self._vrow_at_y(pos.y())
        if vr is not None and vr < len(self._v._vrows):
            rtype, _label, ti = self._v._vrows[vr]
            if rtype == _VR_TASK and ti is not None:
                self._v.taskSelected.emit(self._v._tasks[ti].row)

    def sizeHint(self) -> QSize:
        return QSize(800, 400)


# ── Public widget ─────────────────────────────────────────────────────


class TimelineView(QWidget):
    """Horizontal swim-lane timeline grouped by a configurable task field.

    Signals
    -------
    taskSelected(int)
        Row number of the double-clicked task.
    """

    taskSelected = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tasks: list[Task] = []
        self._lane_field: str = "assignee"
        self._lanes: dict[str, list[int]] = {}
        self._lane_order: list[str] = []
        self._vrows: list[tuple[str, str, int | None]] = []
        self._zoom: str = "week"
        self._today: date | None = None
        self._date_start: date | None = None
        self._date_end: date | None = None
        self._bday_snap: bool = False

        self._sheet: Any = None
        self._col_map: dict[str, int] | None = None
        self._first_col: int = 0
        self._on_set: Any = None

        self.setAccessibleName("Timeline View")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Zoom:"))
        self._zoom_cb = QComboBox()
        self._zoom_cb.addItems(["day", "week", "month"])
        self._zoom_cb.setCurrentText("week")
        self._zoom_cb.currentTextChanged.connect(self._on_zoom_changed)
        self._zoom_cb.setAccessibleName("Timeline zoom level")
        toolbar.addWidget(self._zoom_cb)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._canvas = _TimelineCanvas(self)
        layout.addWidget(self._canvas, 1)

    # ── internals ─────────────────────────────────────────────────────

    def _compute_date_range(self) -> None:
        dates: list[date] = []
        for t in self._tasks:
            if t.start:
                dates.append(t.start)
            if t.due:
                dates.append(t.due)
        if dates:
            self._date_start = min(dates) - timedelta(days=_PAD_DAYS)
            self._date_end = max(dates) + timedelta(days=_PAD_DAYS)
        else:
            today = date.today()
            self._date_start = today - timedelta(days=14)
            self._date_end = today + timedelta(days=14)

    def _compute_lanes(self) -> None:
        lanes: dict[str, list[int]] = {}
        for i, t in enumerate(self._tasks):
            lbl = getattr(t, self._lane_field, "") or "(none)"
            if lbl not in lanes:
                lanes[lbl] = []
            lanes[lbl].append(i)
        self._lanes = lanes
        self._lane_order = sorted(lanes.keys())

    def _build_vrows(self) -> None:
        """Build the flat visual-row list: ``(type, lane_label, task_idx|None)``."""
        rows: list[tuple[str, str, int | None]] = []
        for label in self._lane_order:
            rows.append((_VR_LANE, label, None))
            for ti in self._lanes[label]:
                rows.append((_VR_TASK, label, ti))
        self._vrows = rows

    # ── public API ────────────────────────────────────────────────────

    def setTasks(self, tasks: list[Task]) -> None:
        self._tasks = list(tasks)
        self._compute_date_range()
        self._compute_lanes()
        self._build_vrows()
        self._canvas.update()

    def setContext(
        self,
        sheet: Any,
        col_map: dict[str, int],
        first_col: int = 0,
        on_set: Any = None,
    ) -> None:
        self._sheet = sheet
        self._col_map = col_map
        self._first_col = first_col
        self._on_set = on_set

    def setLaneField(self, field: str) -> None:
        self._lane_field = field
        self._compute_lanes()
        self._build_vrows()
        self._canvas.update()

    def setToday(self, d: date | None) -> None:
        self._today = d
        self._canvas.update()

    def setZoom(self, level: str) -> None:
        if level in _PPD:
            self._zoom = level
            self._zoom_cb.setCurrentText(level)
            self._canvas.update()

    def refresh(self) -> None:
        self._canvas.update()

    # ── internal slots ────────────────────────────────────────────────

    def _on_zoom_changed(self, text: str) -> None:
        if text in _PPD:
            self._zoom = text
            self._canvas.update()
