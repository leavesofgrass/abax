"""Dashboard view — read-only KPI tiles, project health table, milestones.

Displays an at-a-glance roll-up of all projects in the workbook. Receives
data via :meth:`setData` and recalculates on demand via the Refresh button.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from abax.gui._qtcompat import (
    QColor,
    QFont,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)

if TYPE_CHECKING:
    from abax.core.pm.projects import Project
    from abax.core.pm.taskmodel import Task

__all__ = ["DashboardView"]


# ---------------------------------------------------------------------------
# Private analytics helpers (same lightweight versions as report.py)
# ---------------------------------------------------------------------------

_DONE_STATUSES = frozenset({"done", "complete", "completed", "closed"})


def _is_done(task: Task) -> bool:
    return task.status.lower() in _DONE_STATUSES or task.percent_done >= 100.0


def _progress(tasks: list[Task]) -> float:
    weighted = [(t.effort or 1.0, t.percent_done) for t in tasks]
    total_effort = sum(w for w, _ in weighted)
    if total_effort <= 0:
        return 0.0
    return sum(w * p for w, p in weighted) / total_effort


def _overdue_count(tasks: list[Task], today: date) -> int:
    return sum(
        1 for t in tasks
        if t.due is not None and t.due < today and not _is_done(t)
    )


def _health(tasks: list[Task], today: date) -> str:
    if not tasks:
        return "Green"
    ratio = _overdue_count(tasks, today) / len(tasks)
    if ratio > 0.25:
        return "Red"
    if ratio > 0.10:
        return "Amber"
    return "Green"


# ---------------------------------------------------------------------------
# Health dot colours
# ---------------------------------------------------------------------------

_HEALTH_COLORS = {
    "Green": QColor("#2e7d32"),
    "Amber": QColor("#ef6c00"),
    "Red":   QColor("#c62828"),
}


# ---------------------------------------------------------------------------
# KPI tile helper
# ---------------------------------------------------------------------------

class _KpiTile(QWidget):
    """Small labelled stat tile."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self._value_label = QLabel("--")
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self._value_label.setFont(font)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._title_label = QLabel(label)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self._value_label)
        layout.addWidget(self._title_label)

    def setValue(self, text: str) -> None:  # noqa: N802 — Qt naming
        self._value_label.setText(text)


# ---------------------------------------------------------------------------
# DashboardView
# ---------------------------------------------------------------------------

class DashboardView(QWidget):
    """Read-only dashboard showing KPIs, project health, and milestones."""

    refreshRequested = pyqtSignal()  # noqa: N815 — Qt naming

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._projects: list[tuple[Project, list[Task]]] = []
        self._today = date.today()

        root = QVBoxLayout(self)

        # -- KPI row --------------------------------------------------------
        kpi_row = QHBoxLayout()
        self._kpi_tasks = _KpiTile("Total Tasks")
        self._kpi_done = _KpiTile("Done")
        self._kpi_progress = _KpiTile("Progress")
        self._kpi_overdue = _KpiTile("Overdue")
        for tile in (
            self._kpi_tasks,
            self._kpi_done,
            self._kpi_progress,
            self._kpi_overdue,
        ):
            kpi_row.addWidget(tile)
        root.addLayout(kpi_row)

        # -- Project health table -------------------------------------------
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            "Project", "Progress", "Health", "Overdue", "Tasks",
        ])
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers,
        )
        root.addWidget(self._table)

        # -- Milestone list -------------------------------------------------
        self._ms_label = QLabel("<b>Upcoming Milestones</b>")
        root.addWidget(self._ms_label)
        self._ms_list = QLabel("")
        self._ms_list.setWordWrap(True)
        root.addWidget(self._ms_list)

        # -- Refresh button -------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._on_refresh)
        btn_row.addWidget(self._refresh_btn)
        root.addLayout(btn_row)

    # -- public API ---------------------------------------------------------

    def setData(  # noqa: N802 — Qt naming
        self,
        projects: list[tuple[Project, list[Task]]],
        today: date,
    ) -> None:
        """Populate the dashboard with project data."""
        self._projects = projects
        self._today = today
        self._refresh()

    # -- internals ----------------------------------------------------------

    def _on_refresh(self) -> None:
        self.refreshRequested.emit()
        self._refresh()

    def _refresh(self) -> None:
        all_tasks: list[Task] = []
        for _, tasks in self._projects:
            all_tasks.extend(tasks)

        total = len(all_tasks)
        done = sum(1 for t in all_tasks if _is_done(t))
        pct = _progress(all_tasks) if all_tasks else 0.0
        overdue = _overdue_count(all_tasks, self._today)

        self._kpi_tasks.setValue(str(total))
        self._kpi_done.setValue(str(done))
        self._kpi_progress.setValue(f"{pct:.0f}%")
        self._kpi_overdue.setValue(str(overdue))

        # -- health table ---------------------------------------------------
        self._table.setRowCount(len(self._projects))
        for row_idx, (proj, tasks) in enumerate(self._projects):
            # Project name
            self._table.setItem(
                row_idx, 0, QTableWidgetItem(proj.name),
            )

            # Progress bar cell
            pbar = QProgressBar()
            pbar.setRange(0, 100)
            proj_pct = _progress(tasks) if tasks else 0.0
            pbar.setValue(int(proj_pct))
            self._table.setCellWidget(row_idx, 1, pbar)

            # Health
            h = _health(tasks, self._today)
            item = QTableWidgetItem(h)
            color = _HEALTH_COLORS.get(h)
            if color is not None:
                item.setForeground(color)
            self._table.setItem(row_idx, 2, item)

            # Overdue
            self._table.setItem(
                row_idx, 3,
                QTableWidgetItem(str(_overdue_count(tasks, self._today))),
            )

            # Tasks
            self._table.setItem(
                row_idx, 4, QTableWidgetItem(str(len(tasks))),
            )

        self._table.resizeColumnsToContents()

        # -- milestones -----------------------------------------------------
        upcoming: list[tuple[str, str, str]] = []  # (date, name, project)
        for proj, _ in self._projects:
            for ms in proj.milestones:
                if not ms.done:
                    upcoming.append((ms.date or "", ms.name, proj.name))
        upcoming.sort(key=lambda x: x[0])

        if upcoming:
            lines = []
            for ms_date, ms_name, proj_name in upcoming:
                date_str = f" ({ms_date})" if ms_date else ""
                lines.append(f"- {ms_name}{date_str}  [{proj_name}]")
            self._ms_list.setText("\n".join(lines))
        else:
            self._ms_list.setText("No upcoming milestones.")
