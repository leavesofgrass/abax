"""Multi-project roadmap view with milestone diamonds and cross-project arrows.

Paints a horizontal timeline with one lane per registered project, task bars
spanning start-to-due dates, milestone diamonds, a today line, and
cross-project dependency arrows.  Read-only for Wave 2 (no drag editing).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from abax.core.pm.projects import CrossProjectLink, Milestone, Project
from abax.core.pm.taskmodel import Task
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

__all__ = ["RoadmapView"]

# -- Layout constants --------------------------------------------------------
_PPD: dict[str, int] = {"day": 40, "week": 10, "month": 3, "quarter": 1}
_LANE_H = 28          # height per task row inside a lane
_LANE_HDR_H = 24      # height of the project-name header inside each lane
_HDR_H = 40           # top date-axis height
_NAME_W = 160         # left column for project names
_BAR_H = 16           # task bar height
_PAD_DAYS = 7         # padding beyond the date range
_MILESTONE_SZ = 8     # half-size of the milestone diamond

# -- Palette -----------------------------------------------------------------
_BAR_COLOR = QColor(70, 130, 180)       # steel blue
_CRIT_COLOR = QColor(220, 60, 60)       # red for critical
_MILESTONE_COLOR = QColor(255, 165, 0)  # orange
_TODAY_COLOR = QColor(0, 180, 0)        # green
_LINK_COLOR = QColor(128, 128, 128)     # gray
_LANE_BG_ALT = QColor(245, 245, 245)   # alternating lane background
_C_GRID = QColor(230, 230, 230)
_C_HDR = QColor(245, 245, 245)
_C_TEXT = QColor(50, 50, 50)
_C_BG = QColor(255, 255, 255)
_C_DIV = QColor(180, 180, 180)
_C_PROG = QColor(40, 80, 120)


# -- Internal data -----------------------------------------------------------

class _LaneInfo:
    """Cached layout info for a single project lane."""

    __slots__ = ("project", "tasks", "milestones", "y", "height")

    def __init__(
        self,
        project: Project,
        tasks: list[Task],
        milestones: list[Milestone],
    ) -> None:
        self.project = project
        self.tasks = tasks
        self.milestones = milestones
        self.y: int = 0
        self.height: int = 0


# -- Canvas (internal) -------------------------------------------------------


class _RoadmapCanvas(QWidget):
    """Custom-painted roadmap body."""

    def __init__(self, view: RoadmapView) -> None:
        super().__init__(view)
        self._v = view
        self._hoff = 0
        self._voff = 0
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Roadmap canvas")

    # -- coordinate helpers ---------------------------------------------------

    def _ppd(self) -> int:
        return _PPD.get(self._v._zoom, 3)

    def _date_x(self, d: date) -> float:
        if self._v._date_start is None:
            return 0.0
        return (
            _NAME_W
            + (d - self._v._date_start).days * self._ppd()
            - self._hoff
        )

    # -- hit testing ----------------------------------------------------------

    def _hit_task(
        self, px: float, py: float,
    ) -> tuple[int | None, int | None]:
        """Return (lane_index, task_index_within_lane) or (None, None)."""
        for li, lane in enumerate(self._v._lanes):
            if lane.y - self._voff <= py < lane.y + lane.height - self._voff:
                local_y = py - (lane.y - self._voff) - _LANE_HDR_H
                if local_y < 0:
                    continue
                row_idx = int(local_y / _LANE_H)
                if 0 <= row_idx < len(lane.tasks):
                    t = lane.tasks[row_idx]
                    if t.start and t.due:
                        x1 = self._date_x(t.start)
                        x2 = self._date_x(t.due + timedelta(days=1))
                        if x1 <= px <= x2:
                            return li, row_idx
        return None, None

    def _hit_milestone(
        self, px: float, py: float,
    ) -> tuple[int | None, int | None]:
        """Return (lane_index, milestone_index) or (None, None)."""
        for li, lane in enumerate(self._v._lanes):
            lane_top = lane.y - self._voff
            # milestones are drawn at the bottom of the lane header
            ms_cy = lane_top + _LANE_HDR_H / 2
            for mi, ms in enumerate(lane.milestones):
                if not ms.date:
                    continue
                try:
                    ms_date = date.fromisoformat(ms.date)
                except (ValueError, TypeError):
                    continue
                cx = self._date_x(ms_date)
                if (
                    abs(px - cx) <= _MILESTONE_SZ + 2
                    and abs(py - ms_cy) <= _MILESTONE_SZ + 2
                ):
                    return li, mi
        return None, None

    # -- painting -------------------------------------------------------------

    def paintEvent(self, event: Any) -> None:  # noqa: ARG002
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(QRectF(0, 0, w, h), _C_BG)

        lanes = self._v._lanes
        if not lanes:
            p.end()
            return

        # Header background
        p.fillRect(QRectF(0, 0, w, _HDR_H), _C_HDR)
        self._paint_header(p, w)

        # Body clip
        p.save()
        p.setClipRect(QRectF(0, _HDR_H, w, h - _HDR_H))

        # Determine visible lanes
        for li, lane in enumerate(lanes):
            lane_top = lane.y - self._voff + _HDR_H
            lane_bot = lane_top + lane.height
            if lane_bot < _HDR_H or lane_top > h:
                continue
            self._paint_lane(p, li, lane, lane_top, w)

        # Cross-project dependency arrows
        self._paint_cross_links(p)

        # Today line
        if self._v._today is not None:
            tx = self._date_x(self._v._today)
            if _NAME_W <= tx <= w:
                p.setPen(QPen(_TODAY_COLOR, 2, Qt.PenStyle.DashLine))
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
        view_w = w - _NAME_W
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
                x = _NAME_W + i * ppd - self._hoff
                p.drawText(
                    QRectF(x, 2, ppd, _HDR_H - 4),
                    Qt.AlignmentFlag.AlignCenter,
                    d.strftime("%d"),
                )
                p.setPen(QPen(_C_GRID))
                p.drawLine(QPointF(x, _HDR_H - 1), QPointF(x, _HDR_H))
                p.setPen(QPen(_C_TEXT))
        elif zoom == "week":
            seen: set[tuple[int, int]] = set()
            for i in range(first_d, last_d):
                d = ds + timedelta(days=i)
                wk = d.isocalendar()[:2]
                if wk not in seen and d.weekday() == 0:
                    seen.add(wk)
                    x = _NAME_W + i * ppd - self._hoff
                    p.drawText(
                        QRectF(x, 2, 7 * ppd, _HDR_H - 4),
                        Qt.AlignmentFlag.AlignCenter,
                        d.strftime("%b %d"),
                    )
                    p.setPen(QPen(_C_GRID))
                    p.drawLine(QPointF(x, 0), QPointF(x, _HDR_H))
                    p.setPen(QPen(_C_TEXT))
        elif zoom == "month":
            seen_m: set[tuple[int, int]] = set()
            for i in range(first_d, last_d):
                d = ds + timedelta(days=i)
                mk = (d.year, d.month)
                if mk not in seen_m and d.day == 1:
                    seen_m.add(mk)
                    x = _NAME_W + i * ppd - self._hoff
                    dim = calendar.monthrange(d.year, d.month)[1]
                    p.drawText(
                        QRectF(x, 2, dim * ppd, _HDR_H - 4),
                        Qt.AlignmentFlag.AlignCenter,
                        d.strftime("%b %Y"),
                    )
                    p.setPen(QPen(_C_GRID))
                    p.drawLine(QPointF(x, 0), QPointF(x, _HDR_H))
                    p.setPen(QPen(_C_TEXT))
        else:  # quarter
            seen_q: set[tuple[int, int]] = set()
            for i in range(first_d, last_d):
                d = ds + timedelta(days=i)
                qk = (d.year, (d.month - 1) // 3)
                if qk not in seen_q and d.day == 1 and d.month in (1, 4, 7, 10):
                    seen_q.add(qk)
                    x = _NAME_W + i * ppd - self._hoff
                    q_num = (d.month - 1) // 3 + 1
                    p.drawText(
                        QRectF(x, 2, 90 * ppd, _HDR_H - 4),
                        Qt.AlignmentFlag.AlignCenter,
                        f"Q{q_num} {d.year}",
                    )
                    p.setPen(QPen(_C_GRID))
                    p.drawLine(QPointF(x, 0), QPointF(x, _HDR_H))
                    p.setPen(QPen(_C_TEXT))

    def _paint_lane(
        self, p: QPainter, idx: int, lane: _LaneInfo,
        lane_top: float, w: float,
    ) -> None:
        # Alternating background
        if idx % 2 == 1:
            p.fillRect(
                QRectF(0, lane_top, w, lane.height),
                _LANE_BG_ALT,
            )

        # Lane divider
        p.setPen(QPen(_C_DIV))
        p.drawLine(
            QPointF(0, lane_top + lane.height),
            QPointF(w, lane_top + lane.height),
        )

        # Project name
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QPen(_C_TEXT))
        p.drawText(
            QRectF(4, lane_top, _NAME_W - 8, _LANE_HDR_H),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            lane.project.name,
        )

        # Divider between name column and chart area
        p.setPen(QPen(_C_DIV))
        p.drawLine(
            QPointF(_NAME_W, lane_top),
            QPointF(_NAME_W, lane_top + lane.height),
        )

        # Task bars
        font.setBold(False)
        font.setPointSize(8)
        p.setFont(font)
        for ti, task in enumerate(lane.tasks):
            self._paint_task_bar(p, task, lane_top + _LANE_HDR_H + ti * _LANE_H)

        # Milestones (diamonds in the header area)
        for ms in lane.milestones:
            self._paint_milestone(p, ms, lane_top)

    def _paint_task_bar(
        self, p: QPainter, task: Task, row_top: float,
    ) -> None:
        if task.start is None or task.due is None:
            return
        x1 = self._date_x(task.start)
        x2 = self._date_x(task.due + timedelta(days=1))
        bar_w = max(x2 - x1, 2.0)
        y = row_top + (_LANE_H - _BAR_H) / 2
        rect = QRectF(x1, y, bar_w, _BAR_H)

        is_crit = task.id in self._v._critical_ids
        color = _CRIT_COLOR if is_crit else _BAR_COLOR

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(rect, 3, 3)

        # Progress overlay
        if task.percent_done > 0:
            pw = rect.width() * min(task.percent_done / 100.0, 1.0)
            p.setBrush(_C_PROG)
            p.drawRoundedRect(
                QRectF(rect.left(), rect.top(), pw, rect.height()), 3, 3,
            )

    def _paint_milestone(
        self, p: QPainter, ms: Milestone, lane_top: float,
    ) -> None:
        if not ms.date:
            return
        try:
            ms_date = date.fromisoformat(ms.date)
        except (ValueError, TypeError):
            return
        cx = self._date_x(ms_date)
        cy = lane_top + _LANE_HDR_H / 2
        s = _MILESTONE_SZ

        path = QPainterPath()
        path.moveTo(QPointF(cx, cy - s))
        path.lineTo(QPointF(cx + s, cy))
        path.lineTo(QPointF(cx, cy + s))
        path.lineTo(QPointF(cx - s, cy))
        path.closeSubpath()

        p.setPen(QPen(_MILESTONE_COLOR.darker(120), 1))
        p.setBrush(_MILESTONE_COLOR)
        p.drawPath(path)

    def _paint_cross_links(self, p: QPainter) -> None:
        links = self._v._cross_links
        if not links:
            return

        # Build lookup: (project_name, task_id) -> (lane_idx, task_idx_in_lane)
        lookup: dict[tuple[str, str], tuple[int, int]] = {}
        for li, lane in enumerate(self._v._lanes):
            for ti, task in enumerate(lane.tasks):
                lookup[(lane.project.name, task.id)] = (li, ti)

        p.setPen(QPen(_LINK_COLOR, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)

        for link in links:
            src_key = (link.from_project, link.from_id)
            dst_key = (link.to_project, link.to_id)
            src_loc = lookup.get(src_key)
            dst_loc = lookup.get(dst_key)
            if src_loc is None or dst_loc is None:
                continue

            src_li, src_ti = src_loc
            dst_li, dst_ti = dst_loc
            src_lane = self._v._lanes[src_li]
            dst_lane = self._v._lanes[dst_li]
            src_task = src_lane.tasks[src_ti]
            dst_task = dst_lane.tasks[dst_ti]

            if src_task.due is None or dst_task.start is None:
                continue

            sx = self._date_x(src_task.due + timedelta(days=1))
            sy = (
                src_lane.y - self._voff + _HDR_H
                + _LANE_HDR_H + src_ti * _LANE_H + _LANE_H / 2
            )
            dx = self._date_x(dst_task.start)
            dy = (
                dst_lane.y - self._voff + _HDR_H
                + _LANE_HDR_H + dst_ti * _LANE_H + _LANE_H / 2
            )

            mx = (sx + dx) / 2
            path = QPainterPath()
            path.moveTo(QPointF(sx, sy))
            path.lineTo(QPointF(mx, sy))
            path.lineTo(QPointF(mx, dy))
            path.lineTo(QPointF(dx, dy))
            p.drawPath(path)

            # Arrowhead
            ah = 5.0
            p.setBrush(_LINK_COLOR)
            arrow = QPainterPath()
            arrow.moveTo(QPointF(dx, dy))
            arrow.lineTo(QPointF(dx - ah, dy - ah))
            arrow.lineTo(QPointF(dx - ah, dy + ah))
            arrow.closeSubpath()
            p.drawPath(arrow)
            p.setBrush(Qt.BrushStyle.NoBrush)

    # -- mouse interaction ----------------------------------------------------

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
        px, py = pos.x(), pos.y() - _HDR_H

        # Check milestone hit first
        li_ms, mi_ms = self._hit_milestone(px, py + _HDR_H)
        if li_ms is not None and mi_ms is not None:
            lane = self._v._lanes[li_ms]
            self._v.milestoneClicked.emit(
                lane.project.name, lane.milestones[mi_ms].name,
            )
            return

        # Check task hit
        li_t, ti_t = self._hit_task(px, py + _HDR_H)
        if li_t is not None and ti_t is not None:
            lane = self._v._lanes[li_t]
            self._v.taskSelected.emit(
                lane.project.name, lane.tasks[ti_t].row,
            )

    def mouseMoveEvent(self, event: Any) -> None:
        pos = event.position().toPoint()
        px, py = pos.x(), pos.y()

        # Check milestone hover
        li_ms, mi_ms = self._hit_milestone(px, py)
        if li_ms is not None and mi_ms is not None:
            lane = self._v._lanes[li_ms]
            ms = lane.milestones[mi_ms]
            tip = f"{ms.name}"
            if ms.date:
                tip += f"\nDate: {ms.date}"
            QToolTip.showText(
                event.globalPosition().toPoint(), tip, self,
            )
            return

        # Check task hover
        li_t, ti_t = self._hit_task(px, py)
        if li_t is not None and ti_t is not None:
            task = self._v._lanes[li_t].tasks[ti_t]
            parts = [task.title]
            if task.start:
                parts.append(f"Start: {task.start}")
            if task.due:
                parts.append(f"Due: {task.due}")
            if task.assignee:
                parts.append(f"Assignee: {task.assignee}")
            parts.append(f"Progress: {task.percent_done:.0f}%")
            QToolTip.showText(
                event.globalPosition().toPoint(), "\n".join(parts), self,
            )
            return

        QToolTip.hideText()

    def keyPressEvent(self, event: Any) -> None:
        key = event.key()
        step = self._ppd() * 7  # scroll by a week's worth of pixels
        if key == Qt.Key.Key_Left:
            self._hoff = max(0, self._hoff - step)
            self.update()
        elif key == Qt.Key.Key_Right:
            self._hoff += step
            self.update()
        elif key == Qt.Key.Key_Up:
            self._voff = max(0, self._voff - _LANE_H * 3)
            self.update()
        elif key == Qt.Key.Key_Down:
            self._voff += _LANE_H * 3
            self.update()
        else:
            super().keyPressEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(900, 500)


# -- Public widget ------------------------------------------------------------


class RoadmapView(QWidget):
    """Multi-project roadmap with milestone diamonds and dependency arrows.

    Signals
    -------
    taskSelected(str, int)
        ``(project_name, task_row)`` when a task bar is clicked.
    milestoneClicked(str, str)
        ``(project_name, milestone_name)`` when a milestone diamond is clicked.
    """

    taskSelected = pyqtSignal(str, int)
    milestoneClicked = pyqtSignal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lanes: list[_LaneInfo] = []
        self._cross_links: list[CrossProjectLink] = []
        self._critical_ids: set[str] = set()
        self._today: date | None = None
        self._zoom: str = "month"
        self._date_start: date | None = None
        self._date_end: date | None = None

        self.setAccessibleName("Roadmap View")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Zoom:"))
        self._zoom_cb = QComboBox()
        self._zoom_cb.addItems(["day", "week", "month", "quarter"])
        self._zoom_cb.setCurrentText("month")
        self._zoom_cb.currentTextChanged.connect(self._on_zoom_changed)
        self._zoom_cb.setAccessibleName("Roadmap zoom level")
        toolbar.addWidget(self._zoom_cb)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._canvas = _RoadmapCanvas(self)
        layout.addWidget(self._canvas, 1)

    # -- date range -----------------------------------------------------------

    def _compute_date_range(self) -> None:
        dates: list[date] = []
        for lane in self._lanes:
            for t in lane.tasks:
                if t.start:
                    dates.append(t.start)
                if t.due:
                    dates.append(t.due)
            for ms in lane.milestones:
                if ms.date:
                    try:
                        dates.append(date.fromisoformat(ms.date))
                    except (ValueError, TypeError):
                        pass
        if dates:
            self._date_start = min(dates) - timedelta(days=_PAD_DAYS)
            self._date_end = max(dates) + timedelta(days=_PAD_DAYS)
        else:
            today = date.today()
            self._date_start = today - timedelta(days=30)
            self._date_end = today + timedelta(days=30)

    def _compute_lane_layout(self) -> None:
        """Assign y positions and heights to each lane."""
        y = 0
        for lane in self._lanes:
            lane.y = y
            task_rows = max(len(lane.tasks), 1)
            lane.height = _LANE_HDR_H + task_rows * _LANE_H
            y += lane.height

    # -- public API -----------------------------------------------------------

    def setProjects(
        self, projects: list[tuple[Project, list[Task]]],
    ) -> None:
        """Set the project data.  Each tuple is (Project, its parsed tasks)."""
        self._lanes = [
            _LaneInfo(proj, list(tasks), list(proj.milestones))
            for proj, tasks in projects
        ]
        self._compute_lane_layout()
        self._compute_date_range()
        self._canvas.update()

    def setToday(self, today: date) -> None:
        """Set the today-line date."""
        self._today = today
        self._canvas.update()

    def setCrossLinks(self, links: list[CrossProjectLink]) -> None:
        """Set cross-project dependency arrows."""
        self._cross_links = list(links)
        self._canvas.update()

    def setCritical(self, ids: set[str]) -> None:
        """Mark task IDs as critical (different bar color)."""
        self._critical_ids = set(ids)
        self._canvas.update()

    def setZoom(self, level: str) -> None:
        """Set zoom: 'day' | 'week' | 'month' | 'quarter'."""
        if level in _PPD:
            self._zoom = level
            self._zoom_cb.setCurrentText(level)
            self._canvas.update()

    def refresh(self) -> None:
        """Force a repaint."""
        self._canvas.update()

    # -- internal slots -------------------------------------------------------

    def _on_zoom_changed(self, text: str) -> None:
        if text in _PPD:
            self._zoom = text
            self._canvas.update()
