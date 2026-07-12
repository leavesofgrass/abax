"""Dialog for creating / editing PM what-if scenarios (task-field overrides)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from abax.gui._qtcompat import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


# ---- local copy of PmScenario (Agent J builds the canonical one) ---------
@dataclass
class PmScenario:
    name: str
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


_OVERRIDE_FIELDS = [
    "start",
    "due",
    "effort",
    "cost",
    "assignee",
    "status",
    "percent_done",
]


class PmScenarioDialog(QDialog):
    """Create / edit PM scenarios with task-field overrides."""

    def __init__(
        self,
        parent: QWidget | None,
        tasks: list,
        scenarios: list[PmScenario] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("PM Scenario Editor")
        self.resize(800, 500)

        self._tasks = tasks
        self._scenarios: list[PmScenario] = list(scenarios or [])
        self._apply = False

        root = QVBoxLayout(self)

        # ---- splitter: left (scenario list) | right (override table) ----
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, stretch=1)

        # -- left panel --
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        self._scenario_list = QListWidget()
        left_lay.addWidget(self._scenario_list)
        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("Add")
        self._remove_btn = QPushButton("Remove")
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        left_lay.addLayout(btn_row)
        splitter.addWidget(left)

        # -- right panel --
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)

        self._override_table = QTableWidget(0, 4)
        self._override_table.setHorizontalHeaderLabels(
            ["Task ID", "Field", "Original", "New Value"],
        )
        right_lay.addWidget(self._override_table)

        # Add-override row
        add_row = QHBoxLayout()
        self._task_combo = QComboBox()
        for t in self._tasks:
            tid = getattr(t, "task_id", None) or getattr(t, "name", str(t))
            self._task_combo.addItem(str(tid))
        self._field_combo = QComboBox()
        self._field_combo.addItems(_OVERRIDE_FIELDS)
        self._new_value_edit = QLineEdit()
        self._new_value_edit.setPlaceholderText("New value")
        self._add_override_btn = QPushButton("Add Override")
        self._remove_override_btn = QPushButton("Remove Override")
        add_row.addWidget(self._task_combo)
        add_row.addWidget(self._field_combo)
        add_row.addWidget(self._new_value_edit)
        add_row.addWidget(self._add_override_btn)
        add_row.addWidget(self._remove_override_btn)
        right_lay.addLayout(add_row)
        splitter.addWidget(right)

        # ---- delta display ----
        delta_label = QLabel("<b>Before / After Delta</b>")
        root.addWidget(delta_label)
        self._delta_display = QPlainTextEdit()
        self._delta_display.setReadOnly(True)
        self._delta_display.setMaximumHeight(120)
        root.addWidget(self._delta_display)

        # ---- buttons ----
        btn_box = QHBoxLayout()
        self._apply_btn = QPushButton("Apply to Sheet")
        self._keep_btn = QPushButton("Keep as Scenario")
        self._cancel_btn = QPushButton("Cancel")
        btn_box.addStretch()
        btn_box.addWidget(self._apply_btn)
        btn_box.addWidget(self._keep_btn)
        btn_box.addWidget(self._cancel_btn)
        root.addLayout(btn_box)

        # ---- populate scenario list ----
        for sc in self._scenarios:
            self._scenario_list.addItem(sc.name)
        if self._scenarios:
            self._scenario_list.setCurrentRow(0)

        # ---- connections ----
        self._add_btn.clicked.connect(self._on_add_scenario)
        self._remove_btn.clicked.connect(self._on_remove_scenario)
        self._add_override_btn.clicked.connect(self._on_add_override)
        self._remove_override_btn.clicked.connect(self._on_remove_override)
        self._scenario_list.currentRowChanged.connect(self._on_scenario_changed)
        self._apply_btn.clicked.connect(self._on_apply)
        self._keep_btn.clicked.connect(self._on_keep)
        self._cancel_btn.clicked.connect(self.reject)

        self._on_scenario_changed(self._scenario_list.currentRow())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def result_scenario(self) -> PmScenario | None:
        """Return the selected / edited scenario, or *None*."""
        idx = self._scenario_list.currentRow()
        if 0 <= idx < len(self._scenarios):
            return self._scenarios[idx]
        return None

    def result_apply(self) -> bool:
        """True when the user chose *Apply to Sheet*."""
        return self._apply

    def setDelta(self, delta: dict) -> None:  # noqa: N802
        """Populate the before/after text area from an external delta dict."""
        lines: list[str] = []
        for key, val in delta.items():
            lines.append(f"{key}: {val}")
        self._delta_display.setPlainText("\n".join(lines))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _current_scenario(self) -> PmScenario | None:
        idx = self._scenario_list.currentRow()
        if 0 <= idx < len(self._scenarios):
            return self._scenarios[idx]
        return None

    def _on_add_scenario(self) -> None:
        name = f"Scenario {len(self._scenarios) + 1}"
        sc = PmScenario(name=name)
        self._scenarios.append(sc)
        self._scenario_list.addItem(name)
        self._scenario_list.setCurrentRow(len(self._scenarios) - 1)

    def _on_remove_scenario(self) -> None:
        idx = self._scenario_list.currentRow()
        if idx < 0:
            return
        self._scenarios.pop(idx)
        self._scenario_list.takeItem(idx)

    def _on_scenario_changed(self, idx: int) -> None:
        self._override_table.setRowCount(0)
        sc = self._current_scenario()
        if sc is None:
            return
        for tid, fields in sc.overrides.items():
            for fld, val in fields.items():
                self._append_override_row(tid, fld, "", str(val))

    def _on_add_override(self) -> None:
        sc = self._current_scenario()
        if sc is None:
            return
        tid = self._task_combo.currentText()
        fld = self._field_combo.currentText()
        new_val = self._new_value_edit.text()
        sc.overrides.setdefault(tid, {})[fld] = new_val
        self._append_override_row(tid, fld, "", new_val)
        self._new_value_edit.clear()

    def _append_override_row(
        self,
        tid: str,
        fld: str,
        orig: str,
        new: str,
    ) -> None:
        row = self._override_table.rowCount()
        self._override_table.insertRow(row)
        self._override_table.setItem(row, 0, QTableWidgetItem(tid))
        self._override_table.setItem(row, 1, QTableWidgetItem(fld))
        self._override_table.setItem(row, 2, QTableWidgetItem(orig))
        self._override_table.setItem(row, 3, QTableWidgetItem(new))

    def _on_remove_override(self) -> None:
        row = self._override_table.currentRow()
        if row < 0:
            return
        sc = self._current_scenario()
        if sc is not None:
            tid_item = self._override_table.item(row, 0)
            fld_item = self._override_table.item(row, 1)
            if tid_item and fld_item:
                tid = tid_item.text()
                fld = fld_item.text()
                if tid in sc.overrides:
                    sc.overrides[tid].pop(fld, None)
                    if not sc.overrides[tid]:
                        del sc.overrides[tid]
        self._override_table.removeRow(row)

    def _on_apply(self) -> None:
        self._apply = True
        self.accept()

    def _on_keep(self) -> None:
        self._apply = False
        self.accept()
