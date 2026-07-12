"""OKR (Objectives & Key Results) panel widget."""

from __future__ import annotations

from dataclasses import dataclass

from abax.gui._qtcompat import (
    QLabel,
    QProgressBar,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


# ---- lightweight contract types (duplicated for import-safety) -----------
@dataclass
class KeyResult:
    name: str
    target: float = 100.0
    current_formula: str = ""


@dataclass
class Objective:
    objective: str
    key_results: list[KeyResult]


# --------------------------------------------------------------------------


def _kr_progress(kr: KeyResult) -> float:
    """Return 0-100 progress for a key result."""
    try:
        current = float(kr.current_formula)
    except (ValueError, TypeError):
        return 0.0
    if kr.target == 0:
        return 0.0
    return min(max(current / kr.target * 100, 0.0), 100.0)


class OkrView(QWidget):
    """Tree-style OKR panel using a QTableWidget for hierarchy display."""

    _COL_NAME = 0
    _COL_TARGET = 1
    _COL_CURRENT = 2
    _COL_PROGRESS = 3
    _COL_TASKS = 4
    _HEADERS = ["Name", "Target", "Current", "Progress", "Tasks"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        header = QLabel("<b>Objectives & Key Results</b>")
        layout.addWidget(header)

        self._table = QTableWidget(0, len(self._HEADERS))
        self._table.setHorizontalHeaderLabels(self._HEADERS)
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers,
        )
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

    # ------------------------------------------------------------------
    def setObjectives(  # noqa: N802
        self,
        objectives: list[Objective],
        tasks: list | None = None,
    ) -> None:
        """Populate the table with objectives and their key results."""
        tasks = tasks or []
        self._table.setRowCount(0)

        for obj in objectives:
            # --- objective header row ---
            obj_row = self._table.rowCount()
            self._table.insertRow(obj_row)

            # Aggregate progress
            if obj.key_results:
                avg_pct = sum(_kr_progress(kr) for kr in obj.key_results) / len(
                    obj.key_results
                )
            else:
                avg_pct = 0.0

            obj_item = QTableWidgetItem(obj.objective)
            font = obj_item.font()
            font.setBold(True)
            obj_item.setFont(font)
            self._table.setItem(obj_row, self._COL_NAME, obj_item)

            # Progress bar for objective aggregate
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(avg_pct))
            self._table.setCellWidget(obj_row, self._COL_PROGRESS, bar)

            # Linked task count (tags matching "okr:<objective_id>")
            obj_id = obj.objective.lower().replace(" ", "_")
            tag_prefix = f"okr:{obj_id}"
            linked = sum(
                1
                for t in tasks
                if any(
                    tg == tag_prefix or tg.startswith(tag_prefix + ":")
                    for tg in getattr(t, "tags", [])
                )
            )
            task_item = QTableWidgetItem(str(linked))
            task_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter,
            )
            self._table.setItem(obj_row, self._COL_TASKS, task_item)

            # --- key result rows ---
            for kr in obj.key_results:
                kr_row = self._table.rowCount()
                self._table.insertRow(kr_row)

                name_item = QTableWidgetItem(f"    {kr.name}")
                self._table.setItem(kr_row, self._COL_NAME, name_item)

                target_item = QTableWidgetItem(f"{kr.target:g}")
                target_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                )
                self._table.setItem(kr_row, self._COL_TARGET, target_item)

                try:
                    cur_val = float(kr.current_formula)
                    cur_text = f"{cur_val:g}"
                except (ValueError, TypeError):
                    cur_val = 0.0
                    cur_text = kr.current_formula or "0"

                cur_item = QTableWidgetItem(cur_text)
                cur_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                )
                self._table.setItem(kr_row, self._COL_CURRENT, cur_item)

                pct = _kr_progress(kr)
                kr_bar = QProgressBar()
                kr_bar.setRange(0, 100)
                kr_bar.setValue(int(pct))
                self._table.setCellWidget(kr_row, self._COL_PROGRESS, kr_bar)
