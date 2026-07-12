"""Resource workload heatmap — people x weeks grid with reassignment support."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from abax.gui._qtcompat import (
    QBrush,
    QColor,
    QLabel,
    QMenu,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)

if TYPE_CHECKING:
    from abax.gui.theming import Theme


def _load_ratio_color(ratio: float, theme: Theme | None) -> QColor:
    """Return a QColor for the given load ratio using theme tokens.

    Green (success) for <= 0.8, amber/warning for 0.8-1.0, red (error) for > 1.0.
    Falls back to hardcoded colours when no theme is available.
    """
    if ratio <= 0.8:
        if theme is not None:
            return theme.q_color("success")
        return QColor("#a6e3a1")
    if ratio <= 1.0:
        if theme is not None:
            return theme.q_color("warning")
        return QColor("#f9e2af")
    # overallocated
    if theme is not None:
        return theme.q_color("error")
    return QColor("#f38ba8")


def _week_iso(d: datetime.date) -> str:
    """ISO week string like '2026-W03'."""
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _tasks_in_week(tasks: list[Any], assignee: str, week: str) -> list[Any]:
    """Return tasks assigned to *assignee* that overlap *week*."""
    result: list[Any] = []
    for t in tasks:
        if getattr(t, "assignee", None) != assignee:
            continue
        start = getattr(t, "start", None)
        due = getattr(t, "due", None)
        if start is None or due is None:
            continue
        task_start_week = _week_iso(start)
        task_due_week = _week_iso(due)
        if task_start_week <= week <= task_due_week:
            result.append(t)
    return result


class ResourceView(QWidget):
    """People x weeks workload heatmap with click-to-inspect and reassign."""

    taskReassigned = pyqtSignal(str, str, str)  # task_id, old, new

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._workload: dict[str, dict[str, float]] = {}
        self._people: list[Any] | None = None
        self._default_capacity: float = 40.0
        self._tasks: list[Any] = []
        self._weeks: list[str] = []
        self._assignees: list[str] = []

        # Context for write-back
        self._sheet: Any = None
        self._col_map: Any = None
        self._first_col: int = 0
        self._on_set: Any = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._title_label = QLabel("Resource Workload")
        layout.addWidget(self._title_label)

        self._table = QTableWidget(self)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table)

    # ------------------------------------------------------------------
    # Data API
    # ------------------------------------------------------------------

    def setData(
        self,
        workload: dict[str, dict[str, float]],
        people: list[Any] | None = None,
        default_capacity: float = 40.0,
    ) -> None:
        """Set the workload data and rebuild the grid.

        *workload* maps assignee name -> {week_iso: hours}.
        *people* is an optional list of person objects with ``weekly_capacity``.
        """
        self._workload = workload
        self._people = people
        self._default_capacity = default_capacity
        self._rebuild()

    def setTasks(self, tasks: list[Any]) -> None:
        """Store the task list for click-to-inspect and reassign."""
        self._tasks = list(tasks)

    def setContext(
        self,
        sheet: Any,
        col_map: Any,
        first_col: int = 0,
        on_set: Any = None,
    ) -> None:
        """Set the write-back context for reassignment."""
        self._sheet = sheet
        self._col_map = col_map
        self._first_col = first_col
        self._on_set = on_set

    # ------------------------------------------------------------------
    # Capacity helpers
    # ------------------------------------------------------------------

    def _capacity_for(self, assignee: str) -> float:
        """Weekly capacity for *assignee*."""
        if self._people is not None:
            for p in self._people:
                name = getattr(p, "name", None) or str(p)
                if name == assignee:
                    return float(getattr(p, "weekly_capacity", self._default_capacity))
        return self._default_capacity

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _current_theme(self) -> Theme | None:
        """Walk the parent chain to find the MainWindow's ``_theme``."""
        w: QWidget | None = self.window()
        theme = getattr(w, "_theme", None)
        if theme is not None:
            return theme  # type: ignore[return-value]
        return None

    # ------------------------------------------------------------------
    # Grid rebuild
    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        """Rebuild the QTableWidget from the current workload dict."""
        # Collect sorted assignees and weeks
        week_set: set[str] = set()
        for hours_by_week in self._workload.values():
            week_set.update(hours_by_week.keys())

        self._assignees = sorted(self._workload.keys())
        self._weeks = sorted(week_set)

        self._table.setRowCount(len(self._assignees))
        self._table.setColumnCount(len(self._weeks))

        self._table.setVerticalHeaderLabels(self._assignees)
        self._table.setHorizontalHeaderLabels(self._weeks)

        theme = self._current_theme()

        for row, assignee in enumerate(self._assignees):
            cap = self._capacity_for(assignee)
            hours_by_week = self._workload.get(assignee, {})
            for col, week in enumerate(self._weeks):
                hours = hours_by_week.get(week, 0.0)
                ratio = hours / cap if cap > 0 else 0.0
                item = QTableWidgetItem(f"{hours:.1f}")
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                color = _load_ratio_color(ratio, theme)
                item.setBackground(QBrush(color))
                # Store metadata for inspection
                item.setData(Qt.ItemDataRole.UserRole, {
                    "assignee": assignee,
                    "week": week,
                    "hours": hours,
                    "capacity": cap,
                    "ratio": ratio,
                })
                self._table.setItem(row, col, item)

    # ------------------------------------------------------------------
    # Click-to-inspect
    # ------------------------------------------------------------------

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """Show a tooltip listing contributing tasks."""
        if row < 0 or row >= len(self._assignees):
            return
        if col < 0 or col >= len(self._weeks):
            return
        assignee = self._assignees[row]
        week = self._weeks[col]
        tasks = _tasks_in_week(self._tasks, assignee, week)
        if not tasks:
            QToolTip.showText(
                self._table.viewport().mapToGlobal(
                    self._table.visualItemRect(self._table.item(row, col)).center()
                ),
                f"{assignee} - {week}: no tasks",
            )
            return
        lines = [f"{assignee} - {week}:"]
        for t in tasks:
            tid = getattr(t, "id", "?")
            effort = getattr(t, "effort", 0)
            lines.append(f"  {tid} ({effort}h)")
        QToolTip.showText(
            self._table.viewport().mapToGlobal(
                self._table.visualItemRect(self._table.item(row, col)).center()
            ),
            "\n".join(lines),
        )

    # ------------------------------------------------------------------
    # Right-click reassign
    # ------------------------------------------------------------------

    def _on_context_menu(self, pos) -> None:  # noqa: ANN001
        """Show a 'Reassign to...' context menu for tasks in the clicked cell."""
        item = self._table.itemAt(pos)
        if item is None:
            return
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._assignees):
            return
        if col < 0 or col >= len(self._weeks):
            return

        assignee = self._assignees[row]
        week = self._weeks[col]
        tasks = _tasks_in_week(self._tasks, assignee, week)
        if not tasks:
            return

        menu = QMenu(self)
        for t in tasks:
            tid = getattr(t, "id", "?")
            sub = menu.addMenu(f"Reassign '{tid}'")
            for other in self._assignees:
                if other == assignee:
                    continue
                action = sub.addAction(other)
                action.setData({"task": t, "old": assignee, "new": other})

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        data = chosen.data()
        if data is None:
            return
        self._do_reassign(data["task"], data["old"], data["new"])

    def _do_reassign(self, task: Any, old_assignee: str, new_assignee: str) -> None:
        """Reassign *task* from *old_assignee* to *new_assignee*."""
        task.assignee = new_assignee
        tid = str(getattr(task, "id", ""))

        if self._sheet is not None:
            from abax.gui.pm.pm_io import write_task  # type: ignore[import-not-found]

            write_task(
                self._sheet,
                task,
                "assignee",
                new_assignee,
                col_map=self._col_map,
                first_col=self._first_col,
                on_set=self._on_set,
            )

        self.taskReassigned.emit(tid, old_assignee, new_assignee)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def cell_color(self, row: int, col: int) -> QColor | None:
        """Return the background colour of the cell at (*row*, *col*)."""
        item = self._table.item(row, col)
        if item is None:
            return None
        return item.background().color()

    def cell_data(self, row: int, col: int) -> dict[str, Any] | None:
        """Return the metadata dict stored in UserRole for (*row*, *col*)."""
        item = self._table.item(row, col)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)  # type: ignore[return-value]

    @property
    def row_count(self) -> int:
        return self._table.rowCount()

    @property
    def column_count(self) -> int:
        return self._table.columnCount()
