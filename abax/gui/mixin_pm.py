"""PMMixin — Project menu, project-management palette entries, view host wiring."""

from __future__ import annotations


class PMMixin:
    """Mixed into :class:`~abax.gui.main_window.MainWindow`."""

    # -- menu construction (called from _setup_menus) -----------------------

    def _setup_project_menu(self, mb) -> None:
        m_proj = mb.addMenu("&Project")

        self._act(m_proj, "&New project from sheet...", self.pm_new_project)
        self._act(m_proj, "&Open project views...", self.pm_open_views)
        self._act(m_proj, "&Edit project...", self.pm_edit_project)
        self._act(m_proj, "&Remove project...", self.pm_remove_project)
        m_proj.addSeparator()
        self._act(m_proj, "&Milestones...", self.pm_milestones)
        m_proj.addSeparator()
        self._act(m_proj, "&Kanban board", lambda: self._pm_show_view("kanban"))
        self._act(m_proj, "C&ard / gallery", lambda: self._pm_show_view("card"))
        self._act(m_proj, "Ca&lendar", lambda: self._pm_show_view("calendar"))
        self._act(m_proj, "&Gantt chart", lambda: self._pm_show_view("gantt"))
        self._act(m_proj, "&Timeline", lambda: self._pm_show_view("timeline"))
        m_proj.addSeparator()
        self._act(m_proj, "&Dashboard", lambda: self._pm_show_view("dashboard"))
        self._act(m_proj, "&Roadmap", lambda: self._pm_show_view("roadmap"))
        self._act(m_proj, "Re&sources", lambda: self._pm_show_view("resource"))
        self._act(m_proj, "Bud&get / OKRs", lambda: self._pm_show_view("finance"))
        self._act(m_proj, "Sce&narios...", self.pm_scenarios)
        self._act(m_proj, "Schedule (&CPM)...", self.pm_schedule)
        m_proj.addSeparator()
        self._act(m_proj, "&Import tasks...", self.pm_import_tasks)
        self._act(m_proj, "Export &Gantt SVG...", self.pm_export_gantt_svg)
        self._act(m_proj, "Export &report...", self.pm_export_report)

    # -- palette entries (merged by _palette_actions) -----------------------

    def _pm_palette_actions(self) -> dict:
        return {
            "Project: new from sheet...": self.pm_new_project,
            "Project: open views": self.pm_open_views,
            "Project: edit...": self.pm_edit_project,
            "Project: remove...": self.pm_remove_project,
            "Project: milestones...": self.pm_milestones,
            "Project: Kanban board": lambda: self._pm_show_view("kanban"),
            "Project: Card / gallery": lambda: self._pm_show_view("card"),
            "Project: Calendar": lambda: self._pm_show_view("calendar"),
            "Project: Gantt chart": lambda: self._pm_show_view("gantt"),
            "Project: Timeline": lambda: self._pm_show_view("timeline"),
            "Project: Dashboard": lambda: self._pm_show_view("dashboard"),
            "Project: Roadmap": lambda: self._pm_show_view("roadmap"),
            "Project: Resources": lambda: self._pm_show_view("resource"),
            "Project: Budget / OKRs": lambda: self._pm_show_view("finance"),
            "Project: Scenarios...": self.pm_scenarios,
            "Project: Schedule (CPM)...": self.pm_schedule,
            "Project: Import tasks...": self.pm_import_tasks,
            "Project: Export Gantt SVG...": self.pm_export_gantt_svg,
            "Project: export report...": self.pm_export_report,
        }

    # -- actions ------------------------------------------------------------

    def pm_new_project(self) -> None:
        from .pm.project_setup_dialog import ProjectSetupDialog

        dlg = ProjectSetupDialog(self, self._doc.workbook)
        if dlg.exec():
            proj = dlg.result_project()
            if proj is not None:
                self._doc.mark_dirty()
                self._set_status(f"project '{proj.name}' created")
                self._pm_ensure_host()
                self._pm_host.reload_projects()
                self._pm_host.select_project(proj.name)

    def pm_open_views(self) -> None:
        self._pm_ensure_host()
        self._pm_host.reload_projects()
        self._pm_host.show()
        self._pm_host.raise_()

    def pm_edit_project(self) -> None:
        proj = self._pm_pick_project("Edit project")
        if proj is None:
            return
        from .pm.project_setup_dialog import ProjectSetupDialog

        dlg = ProjectSetupDialog(self, self._doc.workbook, project=proj)
        if dlg.exec():
            self._doc.mark_dirty()
            self._set_status(f"project '{proj.name}' updated")
            if hasattr(self, "_pm_host") and self._pm_host is not None:
                self._pm_host.reload_projects()

    def pm_remove_project(self) -> None:
        proj = self._pm_pick_project("Remove project")
        if proj is None:
            return
        from ._qtcompat import QMessageBox

        reply = QMessageBox.question(
            self,
            "Remove project",
            f"Remove project definition '{proj.name}'?\n"
            "(This does not delete sheet data.)",
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._doc.workbook.projects.remove(proj.name)
            self._doc.mark_dirty()
            self._set_status(f"project '{proj.name}' removed")
            if hasattr(self, "_pm_host") and self._pm_host is not None:
                self._pm_host.reload_projects()

    def pm_milestones(self) -> None:
        proj = self._pm_pick_project("Milestones")
        if proj is None:
            return
        from ._qtcompat import QInputDialog

        lines = "\n".join(
            f"{m.name}\t{m.date}\t{'done' if m.done else ''}"
            for m in proj.milestones
        )
        text, ok = QInputDialog.getMultiLineText(
            self,
            "Milestones",
            f"Milestones for '{proj.name}' (name<tab>date<tab>done):",
            lines,
        )
        if not ok:
            return
        from abax.core.pm.projects import Milestone

        milestones = []
        for line in text.strip().splitlines():
            parts = line.split("\t")
            if not parts or not parts[0].strip():
                continue
            name = parts[0].strip()
            dt = parts[1].strip() if len(parts) > 1 else ""
            done = len(parts) > 2 and parts[2].strip().lower() in ("done", "true", "yes", "1")
            milestones.append(Milestone(name=name, date=dt, done=done))
        proj.milestones = milestones
        self._doc.workbook.projects.touch()
        self._doc.mark_dirty()
        self._set_status(f"{len(milestones)} milestone(s) saved for '{proj.name}'")

    def pm_export_report(self) -> None:
        from ._qtcompat import QFileDialog

        path, filt = QFileDialog.getSaveFileName(
            self, "Export PM report", "",
            "HTML files (*.html);;Markdown files (*.md);;All files (*)",
        )
        if not path:
            return
        from datetime import date

        wb = self._doc.workbook
        projects = []
        from abax.core.pm.taskmodel import parse_tasks

        for proj in wb.projects:
            for s in wb.sheets:
                if s.name == proj.sheet:
                    hr = proj.header_row
                    fc = proj.first_col
                    lc = proj.last_col
                    if lc < 0:
                        _, nc = s.used_bounds()
                        lc = nc - 1
                    width = lc - fc + 1
                    if width <= 0:
                        continue
                    tasks = parse_tasks(
                        s, header_row=hr, first_col=fc, last_col=lc,
                        first_data_row=proj.first_data_row if proj.first_data_row >= 0 else None,
                        last_data_row=proj.last_data_row if proj.last_data_row >= 0 else None,
                    )
                    projects.append((proj, tasks))
                    break
        use_md = path.endswith(".md") or "Markdown" in filt
        if use_md:
            from abax.core.pm.report import report_markdown
            content = report_markdown(projects, date.today())
        else:
            from abax.core.pm.report import report_html
            content = report_html(projects, date.today())
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self._set_status(f"PM report exported to {path}")

    def pm_import_tasks(self) -> None:
        from ._qtcompat import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "Import tasks", "",
            "CSV files (*.csv);;MS Project XML (*.xml);;All files (*)",
        )
        if not path:
            return
        from pathlib import Path

        ext = Path(path).suffix.lower()
        from abax.core.pm.importer import import_csv, import_mpp_xml

        try:
            if ext == ".xml":
                tasks = import_mpp_xml(path)
            else:
                tasks = import_csv(path)
        except Exception as exc:
            self._set_status(f"Import failed: {exc}")
            return
        if not tasks:
            self._set_status("No tasks found in file")
            return
        self._set_status(f"Imported {len(tasks)} task(s) from {Path(path).name}")

    def pm_export_gantt_svg(self) -> None:
        proj = self._pm_pick_project("Export Gantt SVG")
        if proj is None:
            return
        from ._qtcompat import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Gantt SVG", "", "SVG files (*.svg);;All files (*)",
        )
        if not path:
            return
        self._pm_ensure_host()
        sheet = self._pm_host._get_sheet()
        if sheet is None:
            return
        _, tasks = self._pm_host._parse_project_tasks(sheet)
        from datetime import date

        from abax.core.pm.exporter import export_gantt_svg

        export_gantt_svg(tasks, path, today=date.today(), title=proj.name)
        self._set_status(f"Gantt SVG exported to {path}")

    def pm_schedule(self) -> None:
        proj = self._pm_pick_project("Schedule (CPM)")
        if proj is None:
            return
        self._pm_ensure_host()
        self._pm_host.select_project(proj.name)
        sheet = self._pm_host._get_sheet()
        if sheet is None:
            self._set_status("project sheet not found")
            return
        _, tasks = self._pm_host._parse_project_tasks(sheet)
        if not tasks:
            self._set_status("no tasks to schedule")
            return
        from abax.core.pm.schedule import compute_cpm, critical_path

        try:
            cpm = compute_cpm(tasks)
        except ValueError as exc:
            self._set_status(f"Schedule failed: {exc}")
            return
        crit = set(critical_path(cpm))
        self._pm_host.set_critical(crit)
        self._pm_show_view("gantt")
        self._set_status(
            f"CPM scheduled '{proj.name}': "
            f"{len(crit)} critical task(s) of {len(tasks)}"
        )

    def pm_scenarios(self) -> None:
        proj = self._pm_pick_project("Scenarios")
        if proj is None:
            return
        self._pm_ensure_host()
        self._pm_host.select_project(proj.name)
        sheet = self._pm_host._get_sheet()
        if sheet is None:
            return
        col_map, tasks = self._pm_host._parse_project_tasks(sheet)
        from .dialogs.pm_scenario_dialog import PmScenario, PmScenarioDialog

        # Reload any scenarios persisted on the project.
        existing = [
            PmScenario(
                name=s.name,
                overrides={tid: dict(f) for tid, f in s.overrides.items()},
            )
            for s in proj.scenarios
        ]
        dlg = PmScenarioDialog(
            self, tasks, scenarios=existing or None, project=proj,
        )
        if not dlg.exec():
            return

        # Persist the edited scenario set on the project (Apply and Keep both
        # accept the dialog; only Cancel — a rejected exec — skips this).
        from abax.core.pm.projects import Scenario as _Scenario

        proj.scenarios = [
            _Scenario(
                name=s.name,
                overrides={tid: dict(f) for tid, f in s.overrides.items()},
            )
            for s in dlg.result_scenarios()
        ]
        self._doc.workbook.projects.touch()
        self._doc.mark_dirty()

        scenario = dlg.result_scenario()
        if scenario is None or not dlg.result_apply():
            self._set_status(
                f"{len(proj.scenarios)} scenario(s) saved for '{proj.name}'"
            )
            return
        from abax.core.pm.finance import apply_scenario_to_sheet

        fc = proj.first_col if proj else 0
        self._doc.checkpoint("apply scenario", coalesce_key="pm_scenario")
        changes = apply_scenario_to_sheet(
            tasks, scenario,
            col_map=col_map, first_col=fc, sheet=sheet,
            on_set=lambda s, r, c, v: s.set_cell(r, c, str(v)),
        )
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status(
            f"Scenario '{scenario.name}' applied ({len(changes)} change(s))"
        )

    # -- helpers ------------------------------------------------------------

    def _pm_pick_project(self, title: str):
        wb = self._doc.workbook
        projects = list(wb.projects)
        if not projects:
            self._set_status("no projects defined — create one first")
            return None
        if len(projects) == 1:
            return projects[0]
        from ._qtcompat import QInputDialog

        names = [p.name for p in projects]
        chosen, ok = QInputDialog.getItem(self, title, "Project:", names, 0, False)
        if not ok:
            return None
        return wb.projects.get(chosen)

    def _pm_ensure_host(self) -> None:
        from ._qtcompat import Qt
        from .pm.view_host import PMViewHost

        host = getattr(self, "_pm_host", None)
        if host is None:
            host = PMViewHost(self)
            self._pm_host = host
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, host)
        host.reload_projects()

    def _pm_show_view(self, view_key: str) -> None:
        self._pm_ensure_host()
        self._pm_host.show()
        self._pm_host.raise_()
        from .pm.view_host import _VIEW_DEFS

        tab_keys = [k for k, _ in _VIEW_DEFS]
        if view_key in tab_keys:
            self._pm_host._tabs.setCurrentIndex(tab_keys.index(view_key))
