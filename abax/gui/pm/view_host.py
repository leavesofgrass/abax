"""PM view host — a dockable tabbed panel that hosts the six PM views.

The host creates view widgets lazily on first switch, wires the ``on_set``
callback to the window's undo/commit path, and refreshes visible views when
the active project or workbook changes.
"""

from __future__ import annotations

from typing import Any

from abax.core.pm.projects import Project
from abax.core.pm.taskmodel import detect_columns, parse_tasks
from abax.gui._qtcompat import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    Qt,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

__all__ = ["PMViewHost"]

_VIEW_DEFS = [
    ("kanban", "Kanban"),
    ("card", "Card"),
    ("calendar", "Calendar"),
    ("gantt", "Gantt"),
    ("timeline", "Timeline"),
    ("dashboard", "Dashboard"),
    ("roadmap", "Roadmap"),
    ("resource", "Resources"),
    ("finance", "Budget"),
    ("okr", "OKRs"),
]


class PMViewHost(QDockWidget):
    """Dockable panel hosting all PM views for the active project."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__("Project views", parent)
        self.setObjectName("PMViewHost")
        self._win = parent
        self._project: Project | None = None

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Project:"))
        self._project_combo = QComboBox()
        self._project_combo.setMinimumWidth(140)
        self._project_combo.currentIndexChanged.connect(self._on_project_changed)
        toolbar.addWidget(self._project_combo)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh_views)
        toolbar.addWidget(self._refresh_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self.setWidget(container)
        self._views: dict[str, QWidget] = {}
        self._critical_ids: set[str] = set()
        self._tabs.currentChanged.connect(self._on_tab_changed)

        for key, label in _VIEW_DEFS:
            placeholder = QLabel(f"({label} view — select a project)")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._tabs.addTab(placeholder, label)

    def reload_projects(self) -> None:
        """Rebuild the project combo from the workbook registry."""
        wb = self._win._doc.workbook
        self._project_combo.blockSignals(True)
        old = self._project_combo.currentText()
        self._project_combo.clear()
        for proj in wb.projects:
            self._project_combo.addItem(proj.name, proj)
        if old:
            idx = self._project_combo.findText(old)
            if idx >= 0:
                self._project_combo.setCurrentIndex(idx)
        self._project_combo.blockSignals(False)
        if self._project_combo.count() > 0:
            self._on_project_changed(self._project_combo.currentIndex())

    def select_project(self, name: str) -> None:
        idx = self._project_combo.findText(name)
        if idx >= 0:
            self._project_combo.setCurrentIndex(idx)

    def set_critical(self, ids: set[str]) -> None:
        """Store critical-path task IDs and push them to the schedule views.

        The IDs are remembered so newly materialized / refreshed Gantt and
        Roadmap views pick up the highlight too (see :meth:`_push_data_to`).
        """
        self._critical_ids = set(ids)
        for key in ("gantt", "roadmap"):
            view = self._views.get(key)
            if view is not None and hasattr(view, "setCritical"):
                view.setCritical(self._critical_ids)

    def _on_project_changed(self, idx: int) -> None:
        if idx < 0:
            self._project = None
            return
        self._project = self._project_combo.itemData(idx)
        self._refresh_views()

    def _on_tab_changed(self, idx: int) -> None:
        if idx < 0 or self._project is None:
            return
        key = _VIEW_DEFS[idx][0]
        if key not in self._views:
            self._materialize_view(key, idx)

    def _materialize_view(self, key: str, tab_idx: int) -> None:
        view = self._create_view(key)
        if view is None:
            return
        self._views[key] = view
        old = self._tabs.widget(tab_idx)
        self._tabs.removeTab(tab_idx)
        self._tabs.insertTab(tab_idx, view, _VIEW_DEFS[tab_idx][1])
        self._tabs.setCurrentIndex(tab_idx)
        if old is not None:
            old.deleteLater()
        self._push_data_to(key, view)

    def _create_view(self, key: str) -> QWidget | None:
        if key == "kanban":
            from .kanban_view import KanbanView
            return KanbanView(parent=self)
        if key == "card":
            from .card_view import CardView
            return CardView(parent=self)
        if key == "calendar":
            from .calendar_view import CalendarView
            return CalendarView(parent=self)
        if key == "gantt":
            from .gantt_view import GanttView
            return GanttView(parent=self)
        if key == "timeline":
            from .timeline_view import TimelineView
            return TimelineView(parent=self)
        if key == "dashboard":
            from .dashboard import DashboardView
            return DashboardView(parent=self)
        if key == "roadmap":
            from .roadmap_view import RoadmapView
            return RoadmapView(parent=self)
        if key == "resource":
            from .resource_view import ResourceView
            return ResourceView(parent=self)
        if key == "finance":
            from .finance_view import FinanceView
            return FinanceView(parent=self)
        if key == "okr":
            from .okr_view import OkrView
            return OkrView(parent=self)
        return None

    def _get_sheet(self) -> Any | None:
        if self._project is None:
            return None
        wb = self._win._doc.workbook
        for s in wb.sheets:
            if s.name == self._project.sheet:
                return s
        return None

    def _make_on_set(self) -> Any:
        win = self._win

        def on_set(sheet: Any, row: int, col: int, value: Any) -> None:
            win._doc.checkpoint("project view edit", coalesce_key="pm_edit")
            sheet.set_cell(row, col, str(value))
            win._doc.mark_dirty()
            win.refresh_table()

        return on_set

    def _parse_project_tasks(self, sheet: Any) -> tuple[dict, list]:
        proj = self._project
        if proj is None:
            return {}, []
        hr = proj.header_row
        fc = proj.first_col
        lc = proj.last_col
        if lc < 0:
            _, nc = sheet.used_bounds()
            lc = nc - 1
        width = lc - fc + 1
        if width <= 0:
            return {}, []
        headers = [
            str(v) if v is not None else ""
            for v in [sheet.get_value(hr, fc + c) for c in range(width)]
        ]
        col_map = detect_columns(headers)
        tasks = parse_tasks(
            sheet,
            header_row=hr,
            first_col=fc,
            last_col=lc,
            first_data_row=proj.first_data_row if proj.first_data_row >= 0 else None,
            last_data_row=proj.last_data_row if proj.last_data_row >= 0 else None,
        )
        return col_map, tasks

    def _push_data_to(self, key: str, view: QWidget) -> None:
        sheet = self._get_sheet()
        if sheet is None:
            return
        col_map, tasks = self._parse_project_tasks(sheet)
        on_set = self._make_on_set()
        proj = self._project

        if key in ("kanban", "card"):
            view.setTasks(tasks)
        elif key == "calendar":
            view.setTasks(tasks)
            view.setContext(
                sheet=sheet,
                col_map=col_map,
                first_col=proj.first_col if proj else 0,
                on_set=on_set,
            )
        elif key in ("gantt", "timeline"):
            if hasattr(view, "setTasks"):
                view.setTasks(tasks)
            if hasattr(view, "setContext"):
                view.setContext(
                    sheet=sheet,
                    col_map=col_map,
                    first_col=proj.first_col if proj else 0,
                    on_set=on_set,
                )
            if hasattr(view, "setCritical"):
                view.setCritical(self._critical_ids)
        elif key == "dashboard":
            from datetime import date as _date

            all_data = self._all_project_data()
            view.setData(all_data, _date.today())
        elif key == "roadmap":
            from datetime import date as _date

            all_data = self._all_project_data()
            view.setProjects(all_data)
            view.setToday(_date.today())
            all_links = []
            for p, _ in all_data:
                all_links.extend(p.cross_links)
            if all_links:
                view.setCrossLinks(all_links)
            if hasattr(view, "setCritical"):
                view.setCritical(self._critical_ids)
        elif key == "resource":
            from abax.core.pm.capacity import aggregate_workload

            workload = aggregate_workload(tasks)
            view.setData(workload)
            view.setTasks(tasks)
            view.setContext(
                sheet=sheet,
                col_map=col_map,
                first_col=proj.first_col if proj else 0,
                on_set=on_set,
            )
        elif key == "finance":
            from abax.core.pm.finance import budget_rollup, evm

            bd = budget_rollup(tasks)
            ev = evm(tasks)
            view.setData(bd, ev)
        elif key == "okr":
            objectives = proj.objectives if proj else []
            view.setObjectives(objectives, tasks)

    def _all_project_data(self) -> list[tuple[Any, list]]:
        """Gather (Project, tasks) for every registered project."""
        wb = self._win._doc.workbook
        result: list[tuple[Any, list]] = []
        for proj in wb.projects:
            for s in wb.sheets:
                if s.name == proj.sheet:
                    old_project = self._project
                    self._project = proj
                    _, tasks = self._parse_project_tasks(s)
                    self._project = old_project
                    result.append((proj, tasks))
                    break
        return result

    def _refresh_views(self) -> None:
        for key, view in self._views.items():
            self._push_data_to(key, view)
            if hasattr(view, "refresh"):
                view.refresh()
