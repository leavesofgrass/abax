"""Interactive Gantt chart view with drag editing.

Paints a task list on the left and date-scaled bars on the right.  Bars are
draggable (move or resize) with snap-to-day; every mutation flows through
``write_task`` so the undo system captures it.
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

__all__ = ["GanttView"]

# ── Layout constants ──────────────────────────────────────────────────
_PPD: dict[str, int] = {"day": 40, "week": 10, "month": 3}
_ROW_H = 28
_HDR_H = 40
_LIST_W = 200
_BAR_H = 18
_EDGE_PX = 6
_PAD_DAYS = 7

# ── Palette ───────────────────────────────────────────────────────────
_C_BAR = QColor(70, 130, 180)
_C_CRIT = QColor(220, 60, 60)
_C_PROG = QColor(40, 80, 120)
_C_PROG_CRIT = QColor(150, 30, 30)
_C_MILE = QColor(180, 150, 40)
_C_TODAY = QColor(255, 80, 80)
_C_ARROW = QColor(120, 120, 120)
_C_GRID = QColor(230, 230, 230)
_C_HDR = QColor(245, 245, 245)
_C_TEXT = QColor(50, 50, 50)
_C_BG = QColor(255, 255, 255)
_C_DIV = QColor(180, 180, 180)


def _snap_bday(d: date) -> date:
    wd = d.weekday()
    if wd == 5:
        return d + timedelta(days=2)
    if wd == 6:
        return d + timedelta(days=1)
    return d


# ── Canvas (internal) ─────────────────────────────────────────────────


class _GanttCanvas(QWidget):
    """Virtualized, custom-painted Gantt body."""

    def __init__(self, view: GanttView) -> None:
        super().__init__(view)
        self._v = view
        self._hoff = 0
        self._voff = 0
        self._drag_idx: int | None = None
        self._drag_mode: str | None = None
        self._drag_ax = 0
        self._drag_os: date | None = None
        self._drag_od: date | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Gantt chart canvas")

    # ── coordinate helpers ────────────────────────────────────────────

    def _ppd(self) -> int:
        return _PPD[self._v._zoom]

    def _date_x(self, d: date) -> float:
        if self._v._date_start is None:
            return 0.0
        return _LIST_W + (d - self._v._date_start).days * self._ppd() - self._hoff

    def _x_date(self, x: float) -> date:
        ds = self._v._date_start or date.today()
        days = (x - _LIST_W + self._hoff) / self._ppd()
        return ds + timedelta(days=round(days))

    def _row_y(self, idx: int) -> float:
        return _HDR_H + idx * _ROW_H - self._voff

    def _bar_rect(self, idx: int) -> QRectF | None:
        t = self._v._tasks[idx]
        if t.start is None or t.due is None:
            return None
        x1 = self._date_x(t.start)
        x2 = self._date_x(t.due + timedelta(days=1))
        y = self._row_y(idx) + (_ROW_H - _BAR_H) / 2
        return QRectF(x1, y, max(x2 - x1, 2.0), _BAR_H)

    def _hit(self, px: float, py: float) -> tuple[int | None, str | None]:
        if py < _HDR_H:
            return None, None
        idx = int((py - _HDR_H + self._voff) / _ROW_H)
        tasks = self._v._tasks
        if idx < 0 or idx >= len(tasks):
            return None, None
        r = self._bar_rect(idx)
        if r is None:
            return idx, None
        if abs(px - r.left()) <= _EDGE_PX and r.top() <= py <= r.bottom():
            return idx, "left"
        if abs(px - r.right()) <= _EDGE_PX and r.top() <= py <= r.bottom():
            return idx, "right"
        if r.contains(QPointF(px, py)):
            return idx, "body"
        return idx, None

    # ── painting ──────────────────────────────────────────────────────

    def paintEvent(self, event: Any) -> None:  # noqa: ARG002
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(QRectF(0, 0, w, h), _C_BG)

        tasks = self._v._tasks
        if not tasks:
            p.end()
            return

        # Header background
        p.fillRect(QRectF(0, 0, w, _HDR_H), _C_HDR)
        self._paint_header(p, w)

        # Body clip
        p.save()
        p.setClipRect(QRectF(0, _HDR_H, w, h - _HDR_H))

        first = max(0, int(self._voff / _ROW_H))
        last = min(len(tasks), int((self._voff + h - _HDR_H) / _ROW_H) + 1)

        # Grid lines
        p.setPen(QPen(_C_GRID))
        for i in range(first, last + 1):
            gy = self._row_y(i)
            p.drawLine(QPointF(0, gy), QPointF(w, gy))

        # Divider
        p.setPen(QPen(_C_DIV))
        p.drawLine(QPointF(_LIST_W, _HDR_H), QPointF(_LIST_W, h))

        # Task labels
        font = QFont()
        font.setPointSize(9)
        p.setFont(font)
        p.setPen(QPen(_C_TEXT))
        for i in range(first, last):
            t = tasks[i]
            y = self._row_y(i)
            lbl = t.title
            if t.assignee:
                lbl += f"  [{t.assignee}]"
            p.drawText(
                QRectF(4, y + 2, _LIST_W - 8, _ROW_H - 4),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                lbl,
            )

        # Bars / milestones
        for i in range(first, last):
            t = tasks[i]
            if t.milestone and t.start is not None:
                self._paint_milestone(p, i)
            else:
                self._paint_bar(p, i)

        # Dependency arrows
        self._paint_arrows(p)

        # Today line
        if self._v._today is not None:
            tx = self._date_x(self._v._today)
            if _LIST_W <= tx <= w:
                p.setPen(QPen(_C_TODAY, 2, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(tx, _HDR_H), QPointF(tx, h))

        p.restore()
        p.end()

    # -- sub-painters --

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
                    x = _LIST_W + i * ppd - self._hoff
                    p.drawText(
                        QRectF(x, 2, 7 * ppd, _HDR_H - 4),
                        Qt.AlignmentFlag.AlignCenter,
                        d.strftime("%b %d"),
                    )
                    p.setPen(QPen(_C_GRID))
                    p.drawLine(QPointF(x, 0), QPointF(x, _HDR_H))
                    p.setPen(QPen(_C_TEXT))
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
                    p.setPen(QPen(_C_GRID))
                    p.drawLine(QPointF(x, 0), QPointF(x, _HDR_H))
                    p.setPen(QPen(_C_TEXT))

    def _paint_bar(self, p: QPainter, idx: int) -> None:
        r = self._bar_rect(idx)
        if r is None:
            return
        task = self._v._tasks[idx]
        crit = task.id in self._v._critical_ids
        color = _C_CRIT if crit else _C_BAR

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(r, 3, 3)

        if task.percent_done > 0:
            pw = r.width() * min(task.percent_done, 1.0)
            p.setBrush(_C_PROG_CRIT if crit else _C_PROG)
            p.drawRoundedRect(QRectF(r.left(), r.top(), pw, r.height()), 3, 3)

    def _paint_milestone(self, p: QPainter, idx: int) -> None:
        task = self._v._tasks[idx]
        if task.start is None:
            return
        cx = self._date_x(task.start)
        cy = self._row_y(idx) + _ROW_H / 2
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

    def _paint_arrows(self, p: QPainter) -> None:
        dag = self._v._dag
        if not dag:
            return
        id_idx: dict[str, int] = {}
        for i, t in enumerate(self._v._tasks):
            if t.id:
                id_idx[t.id] = i

        p.setPen(QPen(_C_ARROW, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)

        for tid, preds in dag.items():
            dst_i = id_idx.get(tid)
            if dst_i is None:
                continue
            dst = self._v._tasks[dst_i]
            if dst.start is None:
                continue
            dx = self._date_x(dst.start)
            dy = self._row_y(dst_i) + _ROW_H / 2

            for pid in preds:
                si = id_idx.get(pid)
                if si is None:
                    continue
                src = self._v._tasks[si]
                if src.due is None:
                    continue
                sx = self._date_x(src.due + timedelta(days=1))
                sy = self._row_y(si) + _ROW_H / 2

                mx = (sx + dx) / 2
                path = QPainterPath()
                path.moveTo(QPointF(sx, sy))
                path.lineTo(QPointF(mx, sy))
                path.lineTo(QPointF(mx, dy))
                path.lineTo(QPointF(dx, dy))
                p.drawPath(path)

                ah = 5.0
                p.setBrush(_C_ARROW)
                arrow = QPainterPath()
                arrow.moveTo(QPointF(dx, dy))
                arrow.lineTo(QPointF(dx - ah, dy - ah))
                arrow.lineTo(QPointF(dx - ah, dy + ah))
                arrow.closeSubpath()
                p.drawPath(arrow)
                p.setBrush(Qt.BrushStyle.NoBrush)

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
        idx, hit = self._hit(pos.x(), pos.y())
        if idx is None or hit is None:
            return
        task = self._v._tasks[idx]
        if task.start is None or task.due is None:
            return
        self._drag_idx = idx
        self._drag_mode = "left" if hit == "left" else ("right" if hit == "right" else "move")
        self._drag_ax = pos.x()
        self._drag_os = task.start
        self._drag_od = task.due

    def mouseMoveEvent(self, event: Any) -> None:
        pos = event.position().toPoint()
        px, py = pos.x(), pos.y()

        if self._drag_idx is not None and self._drag_mode:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            delta = round((px - self._drag_ax) / self._ppd())
            td = timedelta(days=delta)
            task = self._v._tasks[self._drag_idx]
            snap = self._v._bday_snap

            if self._drag_mode == "move":
                ns = self._drag_os + td
                nd = self._drag_od + td
                task.start = _snap_bday(ns) if snap else ns
                task.due = _snap_bday(nd) if snap else nd
            elif self._drag_mode == "left":
                ns = self._drag_os + td
                if snap:
                    ns = _snap_bday(ns)
                if ns <= (task.due or ns):
                    task.start = ns
            else:
                nd = self._drag_od + td
                if snap:
                    nd = _snap_bday(nd)
                if nd >= (task.start or nd):
                    task.due = nd
            self.update()
            return

        idx, hit = self._hit(px, py)
        if hit in ("left", "right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif hit == "body":
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        if idx is not None and hit is not None:
            task = self._v._tasks[idx]
            parts = [task.title]
            if task.start:
                parts.append(f"Start: {task.start}")
            if task.due:
                parts.append(f"Due: {task.due}")
            if task.assignee:
                parts.append(f"Assignee: {task.assignee}")
            if task.status:
                parts.append(f"Status: {task.status}")
            parts.append(f"Progress: {task.percent_done:.0%}")
            QToolTip.showText(event.globalPosition().toPoint(), "\n".join(parts), self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: ARG002
        if self._drag_idx is None:
            return
        task = self._v._tasks[self._drag_idx]
        changed = task.start != self._drag_os or task.due != self._drag_od
        if changed:
            if self._v._sheet is not None and self._v._col_map is not None:
                if task.start != self._drag_os:
                    write_task(
                        self._v._sheet, task, "start", task.start,
                        col_map=self._v._col_map,
                        first_col=self._v._first_col,
                        on_set=self._v._on_set,
                    )
                if task.due != self._drag_od:
                    write_task(
                        self._v._sheet, task, "due", task.due,
                        col_map=self._v._col_map,
                        first_col=self._v._first_col,
                        on_set=self._v._on_set,
                    )
            self._v.taskMoved.emit(task.id, task.start, task.due)
        self._drag_idx = None
        self._drag_mode = None
        self._drag_os = None
        self._drag_od = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def mouseDoubleClickEvent(self, event: Any) -> None:
        pos = event.position().toPoint()
        idx, _ = self._hit(pos.x(), pos.y())
        if idx is not None:
            self._v.taskSelected.emit(self._v._tasks[idx].row)

    def sizeHint(self) -> QSize:
        return QSize(800, 400)


# ── Public widget ─────────────────────────────────────────────────────


class GanttView(QWidget):
    """Interactive Gantt chart with drag-to-edit bars.

    Signals
    -------
    taskSelected(int)
        Row number of the double-clicked task.
    taskMoved(str, object, object)
        ``(task_id, new_start, new_due)`` after a drag completes.
    """

    taskSelected = pyqtSignal(int)
    taskMoved = pyqtSignal(str, object, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tasks: list[Task] = []
        self._critical_ids: set[str] = set()
        self._dag: dict[str, list[str]] = {}
        self._today: date | None = None
        self._zoom: str = "week"
        self._bday_snap: bool = False
        self._date_start: date | None = None
        self._date_end: date | None = None

        self._sheet: Any = None
        self._col_map: dict[str, int] | None = None
        self._first_col: int = 0
        self._on_set: Any = None

        self.setAccessibleName("Gantt View")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Zoom:"))
        self._zoom_cb = QComboBox()
        self._zoom_cb.addItems(["day", "week", "month"])
        self._zoom_cb.setCurrentText("week")
        self._zoom_cb.currentTextChanged.connect(self._on_zoom_changed)
        self._zoom_cb.setAccessibleName("Gantt zoom level")
        toolbar.addWidget(self._zoom_cb)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._canvas = _GanttCanvas(self)
        layout.addWidget(self._canvas, 1)

    # ── date range ────────────────────────────────────────────────────

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

    # ── public API ────────────────────────────────────────────────────

    def setTasks(self, tasks: list[Task]) -> None:
        self._tasks = list(tasks)
        self._compute_date_range()
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

    def setCritical(self, ids: set[str]) -> None:
        self._critical_ids = set(ids)
        self._canvas.update()

    def setDependencies(self, dag: dict[str, list[str]]) -> None:
        self._dag = dict(dag)
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
