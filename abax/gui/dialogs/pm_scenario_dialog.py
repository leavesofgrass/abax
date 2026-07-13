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
        project: Any = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("PM Scenario Editor")
        self.resize(800, 500)

        self._tasks = tasks
        self._scenarios: list[PmScenario] = list(scenarios or [])
        self._apply = False
        self._project = project

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
            tid = getattr(t, "id", "") or f"T{getattr(t, 'row', '?')}"
            label = getattr(t, "title", "") or tid
            self._task_combo.addItem(f"{tid}: {label}", tid)
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
        if not self._scenarios:
            self._scenarios.append(PmScenario(name="Scenario 1"))
        for sc in self._scenarios:
            self._scenario_list.addItem(sc.name)
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

    def result_scenarios(self) -> list[PmScenario]:
        """Return every scenario in the editor (for persistence)."""
        return list(self._scenarios)

    def setDelta(self, delta: dict) -> None:  # noqa: N802
        """Populate the before/after text area from a delta dict.

        Understands the structure returned by
        :func:`abax.core.pm.finance.scenario_delta`
        (``{"projects": [{name, old_finish, new_finish, finish_delta_days,
        old_cost, new_cost, cost_delta}, ...]}``); falls back to a plain
        ``key: value`` dump for any other mapping.
        """
        projects = delta.get("projects") if isinstance(delta, dict) else None
        if projects is None:
            lines = [f"{key}: {val}" for key, val in delta.items()]
            self._delta_display.setPlainText("\n".join(lines))
            return

        lines = []
        for p in projects:
            lines.append(str(p.get("name", "")))
            of, nf = p.get("old_finish"), p.get("new_finish")
            fd = p.get("finish_delta_days")
            if fd is None:
                lines.append(f"  Finish: {of or 'n/a'} → {nf or 'n/a'}")
            else:
                sign = "+" if fd >= 0 else ""
                lines.append(
                    f"  Finish: {of or 'n/a'} → {nf or 'n/a'}"
                    f"  ({sign}{fd} day{'s' if abs(fd) != 1 else ''})"
                )
            oc = p.get("old_cost", 0.0)
            nc = p.get("new_cost", 0.0)
            cd = p.get("cost_delta", 0.0)
            sign = "+" if cd >= 0 else ""
            lines.append(f"  Cost:   {oc:,.2f} → {nc:,.2f}  ({sign}{cd:,.2f})")
        self._delta_display.setPlainText("\n".join(lines))

    # ------------------------------------------------------------------
    # Live delta
    # ------------------------------------------------------------------
    def _update_delta(self) -> None:
        """Recompute the before/after delta for the current scenario."""
        sc = self._current_scenario()
        if sc is None:
            self._delta_display.clear()
            return
        from datetime import date

        from abax.core.pm.finance import PmScenario as _FinScenario
        from abax.core.pm.finance import scenario_delta
        from abax.core.pm.projects import Project

        overrides: dict[str, dict[str, Any]] = {}
        for tid, fields in sc.overrides.items():
            overrides[tid] = {
                fld: self._coerce_value(fld, val)
                for fld, val in fields.items()
            }
        fin_sc = _FinScenario(name=sc.name, overrides=overrides)
        proj = self._project if self._project is not None else Project(
            name=sc.name or "(scenario)",
        )
        try:
            delta = scenario_delta([(proj, self._tasks)], fin_sc, date.today())
        except Exception as exc:  # keep the dialog usable on bad input
            self._delta_display.setPlainText(f"(delta unavailable: {exc})")
            return
        self.setDelta(delta)

    @staticmethod
    def _coerce_value(field_name: str, value: Any) -> Any:
        """Coerce numeric override strings so delta math stays type-correct."""
        if field_name in ("effort", "cost", "percent_done"):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return value

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
                self._append_override_row(tid, fld, self._get_original(tid, fld), str(val))
        self._update_delta()

    def _on_add_override(self) -> None:
        sc = self._current_scenario()
        if sc is None:
            return
        tid = self._task_combo.currentData() or self._task_combo.currentText()
        fld = self._field_combo.currentText()
        new_val = self._new_value_edit.text()
        sc.overrides.setdefault(tid, {})[fld] = new_val
        orig = self._get_original(tid, fld)
        self._append_override_row(tid, fld, orig, new_val)
        self._new_value_edit.clear()
        self._update_delta()

    def _get_original(self, tid: str, fld: str) -> str:
        for t in self._tasks:
            task_id = getattr(t, "id", "") or f"T{getattr(t, 'row', '')}"
            if task_id == tid:
                val = getattr(t, fld, None)
                return str(val) if val is not None else ""
        return ""

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
        self._update_delta()

    def _on_apply(self) -> None:
        self._apply = True
        self.accept()

    def _on_keep(self) -> None:
        self._apply = False
        self.accept()
