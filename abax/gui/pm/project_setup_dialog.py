"""Project setup dialog — create or edit a PM project definition.

Lets the user pick a sheet (or Table), preview the detected column mapping,
name the project, and choose a default view.  On accept the project is
registered (or updated) in the workbook's :class:`ProjectRegistry`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from abax.core.pm.projects import Project
from abax.core.pm.taskmodel import detect_columns
from abax.gui._qtcompat import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    Qt,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from abax.gui._qtcompat import QWidget

__all__ = ["ProjectSetupDialog"]

_VIEW_LABELS = [
    ("kanban", "Kanban board"),
    ("card", "Card / gallery"),
    ("calendar", "Calendar"),
    ("gantt", "Gantt chart"),
    ("timeline", "Timeline"),
]


class ProjectSetupDialog(QDialog):
    """Modal dialog for creating or editing a project definition."""

    def __init__(
        self,
        parent: QWidget,
        workbook: Any,
        *,
        project: Project | None = None,
    ) -> None:
        super().__init__(parent)
        self._wb = workbook
        self._editing = project
        self.setWindowTitle("Edit project" if project else "New project from sheet")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit(self)
        form.addRow("Project &name:", self._name_edit)

        self._sheet_combo = QComboBox(self)
        for s in workbook.sheets:
            self._sheet_combo.addItem(s.name)
        form.addRow("&Sheet:", self._sheet_combo)

        self._table_combo = QComboBox(self)
        self._table_combo.addItem("(entire sheet)")
        for tbl in workbook.tables:
            self._table_combo.addItem(tbl.name)
        form.addRow("&Table region:", self._table_combo)

        self._header_spin = QSpinBox(self)
        self._header_spin.setMinimum(0)
        self._header_spin.setMaximum(99999)
        form.addRow("&Header row:", self._header_spin)

        self._view_combo = QComboBox(self)
        for key, label in _VIEW_LABELS:
            self._view_combo.addItem(label, key)
        form.addRow("Default &view:", self._view_combo)

        layout.addLayout(form)

        self._preview_label = QLabel(self)
        self._preview_label.setWordWrap(True)
        self._preview_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(QLabel("<b>Detected columns:</b>"))
        layout.addWidget(self._preview_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._sheet_combo.currentIndexChanged.connect(self._update_preview)
        self._table_combo.currentIndexChanged.connect(self._update_preview)
        self._header_spin.valueChanged.connect(self._update_preview)

        if project:
            self._name_edit.setText(project.name)
            idx = self._sheet_combo.findText(project.sheet)
            if idx >= 0:
                self._sheet_combo.setCurrentIndex(idx)
            if project.table_ref:
                tidx = self._table_combo.findText(project.table_ref)
                if tidx >= 0:
                    self._table_combo.setCurrentIndex(tidx)
            self._header_spin.setValue(project.header_row)
            vidx = self._view_combo.findData(project.default_view)
            if vidx >= 0:
                self._view_combo.setCurrentIndex(vidx)

        self._update_preview()

    def _current_sheet(self) -> Any | None:
        name = self._sheet_combo.currentText()
        for s in self._wb.sheets:
            if s.name == name:
                return s
        return None

    def _update_preview(self) -> None:
        sheet = self._current_sheet()
        if sheet is None:
            self._preview_label.setText("(no sheet)")
            return
        tbl_name = self._table_combo.currentText()
        if tbl_name != "(entire sheet)":
            tbl = self._wb.tables.get(tbl_name)
            if tbl is not None:
                hr = tbl.header_row
                fc, lc = tbl.first_col, tbl.last_col
                self._header_spin.setValue(hr)
            else:
                hr = self._header_spin.value()
                fc, lc = 0, None
        else:
            hr = self._header_spin.value()
            fc = 0
            _, nc = sheet.used_bounds()
            lc = nc - 1 if nc > 0 else 0
        width = (lc - fc + 1) if lc is not None else 0
        if width <= 0:
            self._preview_label.setText("(no columns)")
            return
        headers = [
            str(v) if v is not None else ""
            for v in [sheet.get_value(hr, fc + c) for c in range(width)]
        ]
        col_map = detect_columns(headers)
        if col_map:
            lines = [f"  {field} -> column {fc + idx}" for field, idx in sorted(col_map.items())]
            self._preview_label.setText("\n".join(lines))
        else:
            self._preview_label.setText("(no task columns recognised)")

    def _on_accept(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setFocus()
            return
        if not self._editing and self._wb.projects.has(name):
            self._name_edit.selectAll()
            self._name_edit.setFocus()
            return

        sheet = self._current_sheet()
        if sheet is None:
            return

        tbl_name = self._table_combo.currentText()
        table_ref = tbl_name if tbl_name != "(entire sheet)" else ""

        if self._editing:
            proj = self._editing
            proj.name = name
            proj.sheet = sheet.name
            proj.header_row = self._header_spin.value()
            proj.table_ref = table_ref
            proj.default_view = self._view_combo.currentData()
            if not table_ref:
                _, nc = sheet.used_bounds()
                proj.first_col = 0
                proj.last_col = nc - 1 if nc > 0 else 0
            self._wb.projects.touch()
        else:
            _, nc = sheet.used_bounds()
            proj = Project(
                name=name,
                sheet=sheet.name,
                header_row=self._header_spin.value(),
                table_ref=table_ref,
                default_view=self._view_combo.currentData(),
                first_col=0,
                last_col=nc - 1 if nc > 0 else 0,
            )
            self._wb.projects.add(proj)

        self._result_project = proj
        self.accept()

    def result_project(self) -> Project | None:
        return getattr(self, "_result_project", None)
