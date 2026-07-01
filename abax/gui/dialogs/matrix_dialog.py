"""Matrix tool — apply a matrix operation over grid ranges.

Reads numeric ranges from the sheet, computes (transpose / inverse / determinant
/ multiply / solve) via :mod:`abax.core.science.matrix`, and writes the result back
starting at a target cell (or reports a scalar in the status line).
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
from ...core.reference import parse_a1, parse_range, to_a1
from ...core.science import eigen as E
from ...core.science import matrix as M

_OPS = ["Transpose", "Inverse", "Determinant", "Multiply (A-B)", "Solve (A-x=b)",
        "Eigenvalues", "Cholesky (L)", "QR — Q", "QR — R", "Condition number"]


class MatrixDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Matrix tool")
        self._build()

    def _build(self) -> None:
        form = QFormLayout(self)
        r1, c1, r2, c2 = self._win._selected_bounds()
        self._a = QLineEdit(f"{to_a1(r1, c1)}:{to_a1(r2, c2)}", self)
        self._op = QComboBox(self)
        self._op.addItems(_OPS)
        self._b = QLineEdit(self)
        self._out = QLineEdit(to_a1(r1, max(0, c2 + 2)), self)
        form.addRow("Matrix A (range):", self._a)
        form.addRow("Operation:", self._op)
        form.addRow("B / b (range):", self._b)
        form.addRow("Output top-left:", self._out)
        b = QPushButton("Apply", self)
        b.clicked.connect(self._apply)
        form.addRow(b)

    def _read(self, rng: str):
        r1, c1, r2, c2 = parse_range(rng)
        sheet = self._win._doc.workbook.sheet
        mat = []
        for r in range(r1, r2 + 1):
            row = []
            for c in range(c1, c2 + 1):
                v = sheet.get_value(r, c)
                row.append(float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0)
            mat.append(row)
        return mat

    def _write(self, mat, top_left: str) -> None:
        r0, c0 = parse_a1(top_left)
        sheet = self._win._doc.workbook.sheet
        for i, row in enumerate(mat):
            for j, v in enumerate(row):
                sheet.set_cell(r0 + i, c0 + j, _fmt(v))

    def _apply(self) -> None:
        op = self._op.currentText()
        try:
            a = self._read(self._a.text())
            if op == "Transpose":
                self._write(M.transpose(a), self._out.text())
            elif op == "Inverse":
                self._write(M.inverse(a), self._out.text())
            elif op == "Determinant":
                self._win._set_status(f"det = {_fmt(M.determinant(a))}")
                self.accept()
                return
            elif op.startswith("Multiply"):
                self._write(M.matmul(a, self._read(self._b.text())), self._out.text())
            elif op.startswith("Solve"):
                bvec = [row[0] for row in self._read(self._b.text())]
                x = M.solve(a, bvec)
                self._write([[v] for v in x], self._out.text())
            elif op == "Eigenvalues":
                self._write([[v] for v in E.eigenvalues(a)], self._out.text())
            elif op == "Cholesky (L)":
                self._write(E.cholesky(a), self._out.text())
            elif op == "QR — Q":
                self._write(E.qr(a)[0], self._out.text())
            elif op == "QR — R":
                self._write(E.qr(a)[1], self._out.text())
            elif op == "Condition number":
                self._win._set_status(f"cond = {_fmt(E.condition_number(a))}")
                self.accept()
                return
        except (M.MatrixError, E.EigenError, ValueError) as exc:
            QMessageBox.warning(self, "Matrix", str(exc))
            return
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(f"matrix: {op}")
        self.accept()


def _fmt(v: float) -> str:
    return str(int(v)) if isinstance(v, float) and v.is_integer() else f"{v:.10g}"
