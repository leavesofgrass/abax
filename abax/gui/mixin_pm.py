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
        tab_keys = ["kanban", "card", "calendar", "gantt", "timeline"]
        if view_key in tab_keys:
            self._pm_host._tabs.setCurrentIndex(tab_keys.index(view_key))
