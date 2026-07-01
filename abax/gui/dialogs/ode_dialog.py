"""ODE solver dialog — integrate dy/dt = f(t, y) and write t, y columns.

Compiles the scalar derivative expression in ``t`` and ``y`` against the same
sandboxed math namespace used by the grapher (so ``^`` is power and only safe
names are exposed), solves with :mod:`abax.core.science.ode`, and writes the time and
solution columns back to the grid. (Coupled systems are available in the Python
console via ``ode.solve`` with a vector field.)
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
from ...core.graphing import _SAFE_NAMES
from ...core.reference import parse_a1
from ...core.science import ode, ode_implicit

_EXPLICIT = ("rk4", "rk45", "euler")
_STIFF = ("backward_euler", "implicit_trapezoid", "bdf2")
_METHODS = list(_EXPLICIT) + list(_STIFF)


def _compile2(expr: str):
    """Compile ``expr`` into ``f(t, y) -> float`` over the safe math namespace."""
    code = compile(expr.replace("^", "**"), "<ode-expr>", "eval")
    glb = {"__builtins__": {}}

    def f(t: float, y: float) -> float:
        ns = dict(_SAFE_NAMES)
        ns["t"], ns["y"] = t, y
        return eval(code, glb, ns)  # noqa: S307 - sandboxed namespace

    f(0.0, 0.0)  # probe so name/syntax errors surface now
    return f


class ODEDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("ODE solver")
        self._build()

    def _build(self) -> None:
        form = QFormLayout(self)
        self._expr = QLineEdit("-2*y", self)
        self._expr.setToolTip("dy/dt as a function of t and y, e.g.  -2*y  or  t - y")
        self._y0 = QLineEdit("1", self)
        self._t0 = QLineEdit("0", self)
        self._t1 = QLineEdit("5", self)
        self._n = QLineEdit("100", self)
        self._method = QComboBox(self)
        self._method.addItems(_METHODS)
        self._out = QLineEdit("D1", self)
        form.addRow("dy/dt =", self._expr)
        form.addRow("y(t₀):", self._y0)
        form.addRow("t₀:", self._t0)
        form.addRow("t₁:", self._t1)
        form.addRow("steps (n):", self._n)
        form.addRow("Method:", self._method)
        form.addRow("Output top-left:", self._out)
        btn = QPushButton("Solve", self)
        btn.clicked.connect(self._apply)
        form.addRow(btn)

    def _apply(self) -> None:
        try:
            f = _compile2(self._expr.text())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "ODE", f"Bad expression: {exc}")
            return
        method = self._method.currentText()
        try:
            t0, t1 = float(self._t0.text()), float(self._t1.text())
            y0 = float(self._y0.text())
            n = int(float(self._n.text()))
            field = lambda t, y: [f(t, y[0])]  # noqa: E731
            if method in _STIFF:
                ts, ys = ode_implicit.solve_stiff(field, (t0, t1), [y0], method=method, n=n)
            else:
                ts, ys = ode.solve(field, (t0, t1), [y0], method=method, n=n)
        except (ode.ODEError, ode_implicit.StiffODEError, ValueError) as exc:
            QMessageBox.warning(self, "ODE", str(exc))
            return
        try:
            r0, c0 = parse_a1(self._out.text())
        except Exception:  # noqa: BLE001
            r0, c0 = 0, 3
        sheet = self._win._doc.workbook.sheet
        for i, (t, yv) in enumerate(zip(ts, ys)):
            sheet.set_cell(r0 + i, c0, f"{t:.10g}")
            sheet.set_cell(r0 + i, c0 + 1, f"{yv[0]:.10g}")
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(
            f"ODE {self._method.currentText()}: {len(ts)} points "
            f"(t,y -> {self._out.text()})")
        self.accept()
