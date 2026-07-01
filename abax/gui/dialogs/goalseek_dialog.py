"""Goal Seek — find the input-cell value that makes a target cell equal a value.

Solves with :func:`abax.core.goalseek.goal_seek` over a closure that writes the
changing cell, recomputes, and reads the target cell.
"""

from __future__ import annotations

from .._qtcompat import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from ...core import goalseek
from ...core.reference import parse_a1, to_a1


class GoalSeekDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Goal Seek")
        r, c = window._current_cell()
        form = QFormLayout()
        self._target = QLineEdit(to_a1(r, c), self)
        self._value = QLineEdit("0", self)
        self._changing = QLineEdit("", self)
        form.addRow("Set cell:", self._target)
        form.addRow("To value:", self._value)
        form.addRow("By changing cell:", self._changing)
        root = QVBoxLayout(self)
        root.addLayout(form)
        bar = QHBoxLayout()
        bar.addStretch(1)
        cancel = QPushButton("Cancel", self)
        cancel.clicked.connect(self.reject)
        solve = QPushButton("Solve", self)
        solve.setDefault(True)
        solve.clicked.connect(self.solve)
        bar.addWidget(cancel)
        bar.addWidget(solve)
        root.addLayout(bar)
        self._readout = QLabel("", self)
        self._readout.setWordWrap(True)
        root.addWidget(self._readout)

    def solve(self) -> str:
        sheet = self._win._doc.workbook.sheet
        try:
            tr, tc = parse_a1(self._target.text())
            cr, cc = parse_a1(self._changing.text())
            target = float(self._value.text())
        except ValueError:
            QMessageBox.warning(self, "Goal Seek", "Enter valid cell refs and a number.")
            return ""
        original = sheet.get_raw(cr, cc)

        def f(x: float) -> float:
            sheet.set_cell(cr, cc, repr(x))
            v = sheet.get_value(tr, tc)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise ValueError("target cell is not numeric")
            return float(v)

        try:
            x0 = float(sheet.get_value(cr, cc) or 0)
        except (TypeError, ValueError):
            x0 = 0.0
        try:
            result = goalseek.goal_seek(f, target, x0)
        except (goalseek.GoalSeekError, ValueError) as exc:
            sheet.set_cell(cr, cc, original)                 # restore on failure
            QMessageBox.warning(self, "Goal Seek", f"No solution found: {exc}")
            return ""
        sheet.set_cell(cr, cc, repr(result))                 # keep the solution
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(
            f"Goal Seek: {self._changing.text()} = {result:.6g} "
            f"makes {self._target.text()} = {target:g}")
        self.accept()
        return f"{result:.6g}"
