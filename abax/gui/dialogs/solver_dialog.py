"""Numerical solver — root-find / integrate / differentiate an expression f(x).

Compiles the expression with the sandboxed :func:`abax.core.graphing.compile_expr`
(so ``^`` means power and only a safe math namespace is exposed) and applies
:mod:`abax.core.science.numeric`. The result is written to an output cell and/or the
status line.
"""

from __future__ import annotations

from .._qtcompat import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
)
from ...core.graphing import compile_expr
from ...core.reference import parse_a1
from ...core.science import numeric as N

_MODES = [
    "Root — bisection [a, b]",
    "Root — Newton (x₀)",
    "Integral ∫ over [a, b]",
    "Derivative f′(x₀)",
]


class SolverDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Numerical solver")
        self._build()

    def _build(self) -> None:
        form = QFormLayout(self)
        self._expr = QLineEdit("x^2 - 2", self)
        self._mode = QComboBox(self)
        self._mode.addItems(_MODES)
        self._a = QLineEdit("0", self)
        self._b = QLineEdit("2", self)
        self._x0 = QLineEdit("1", self)
        self._out = QLineEdit(self)
        self._out.setPlaceholderText("optional output cell, e.g. B1")
        form.addRow("f(x) =", self._expr)
        form.addRow("Method:", self._mode)
        form.addRow("a:", self._a)
        form.addRow("b:", self._b)
        form.addRow("x₀:", self._x0)
        form.addRow("Output cell:", self._out)
        btn = QPushButton("Solve", self)
        btn.clicked.connect(self._apply)
        form.addRow(btn)

    def _apply(self) -> None:
        try:
            f = compile_expr(self._expr.text())
        except Exception as exc:  # noqa: BLE001 - surface any compile error
            QMessageBox.warning(self, "Solver", f"Bad expression: {exc}")
            return
        idx = self._mode.currentIndex()
        try:
            a, b, x0 = float(self._a.text()), float(self._b.text()), float(self._x0.text())
            if idx == 0:
                result = N.bisection(f, a, b)
            elif idx == 1:
                result = N.newton(f, x0)
            elif idx == 2:
                result = N.integrate(f, a, b)
            else:
                result = N.derivative(f, x0)
        except (N.NumericError, ValueError) as exc:
            QMessageBox.warning(self, "Solver", str(exc))
            return
        out = self._out.text().strip()
        if out:
            try:
                r0, c0 = parse_a1(out)
                self._win._doc.workbook.sheet.set_cell(r0, c0, f"{result:.12g}")
                self._win._doc.mark_dirty()
                self._win.refresh_table()
            except Exception:  # noqa: BLE001
                pass
        self._win._set_status(f"{_MODES[idx].split('—')[0].strip()}: {result:.10g}")
        self.accept()
