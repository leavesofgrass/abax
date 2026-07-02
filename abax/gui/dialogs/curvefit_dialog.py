"""Curve fitting dialog — fit a model to XY data and report coefficients + R².

Reads an X range and a Y range from the grid, fits one of Linear / Polynomial
(degree n) / Exponential (``y = a·e^{bx}``) / Power (``y = a·x^b``) with the
pure-stdlib :mod:`abax.core.science.curvefit`, and shows the coefficients and
R². Optionally writes a fitted-values column next to the data.
"""

from __future__ import annotations

import math

from .._qtcompat import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
)
from ...core.reference import parse_a1, parse_range, to_a1
from ...core.science import curvefit

_LINEAR = "Linear (y = a + b·x)"
_POLY = "Polynomial (degree n)"
_EXP = "Exponential (y = a·e^(b·x))"
_POWER = "Power (y = a·x^b)"
_MODELS = [_LINEAR, _POLY, _EXP, _POWER]


class CurveFitDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Curve fit")
        self._build()

    def _build(self) -> None:
        form = QFormLayout(self)
        r1, c1, r2, c2 = self._win._selected_bounds()
        # Guess X = first selected column, Y = second (or same if one column).
        self._x = QLineEdit(f"{to_a1(r1, c1)}:{to_a1(r2, c1)}", self)
        ycol = c1 + 1 if c2 > c1 else c1
        self._y = QLineEdit(f"{to_a1(r1, ycol)}:{to_a1(r2, ycol)}", self)
        self._model = QComboBox(self)
        self._model.addItems(_MODELS)
        self._degree = QLineEdit("2", self)
        self._degree.setToolTip("Polynomial degree (only used for the Polynomial model)")
        self._write = QCheckBox("Write fitted-values column next to Y", self)
        self._write.setChecked(True)
        self._out = QLineEdit(to_a1(r1, ycol + 1), self)
        self._out.setToolTip("Top cell for the fitted-values column")
        form.addRow("X range:", self._x)
        form.addRow("Y range:", self._y)
        form.addRow("Model:", self._model)
        form.addRow("Degree:", self._degree)
        form.addRow(self._write)
        form.addRow("Fitted column top:", self._out)
        btn = QPushButton("Fit", self)
        btn.clicked.connect(self._apply)
        form.addRow(btn)
        self._readout = QLabel("", self)
        self._readout.setWordWrap(True)
        form.addRow(self._readout)

    def _read_col(self, rng: str) -> list[float]:
        """Read a range as a flat list of floats (row-major); blanks skipped."""
        r1, c1, r2, c2 = parse_range(rng)
        sheet = self._win._doc.workbook.sheet
        vals: list[float] = []
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                v = sheet.get_value(r, c)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    vals.append(float(v))
        return vals

    def _apply(self) -> None:
        try:
            xs = self._read_col(self._x.text())
            ys = self._read_col(self._y.text())
        except Exception as exc:  # noqa: BLE001 - bad range text
            QMessageBox.warning(self, "Curve fit", f"Bad range: {exc}")
            return
        if len(xs) != len(ys):
            QMessageBox.warning(
                self, "Curve fit",
                f"X and Y must have the same number of numeric values "
                f"({len(xs)} vs {len(ys)}).")
            return

        model = self._model.currentText()
        try:
            summary, fitted = self._fit(model, xs, ys)
        except (curvefit.RegressionError, ValueError) as exc:
            QMessageBox.warning(self, "Curve fit", str(exc))
            return

        self._readout.setText(summary)
        if self._write.isChecked() and fitted is not None:
            try:
                r0, c0 = parse_a1(self._out.text())
            except Exception:  # noqa: BLE001
                r0, c0 = parse_range(self._y.text())[0], parse_range(self._y.text())[3] + 1
            sheet = self._win._doc.workbook.sheet
            for i, yv in enumerate(fitted):
                sheet.set_cell(r0 + i, c0, f"{yv:.10g}")
            self._win._doc.mark_dirty()
            self._win.refresh_table()
        self._win._set_status(summary)

    def _fit(self, model: str, xs, ys):
        """Run the chosen fit; return ``(summary_text, fitted_values)``."""
        if model == _EXP:
            a, b, r2 = curvefit.expfit(xs, ys)
            fitted = [a * math.exp(b * x) for x in xs]
            return (f"y = {a:.6g}·e^({b:.6g}·x)    R² = {r2:.6f}", fitted)
        if model == _POWER:
            a, b, r2 = curvefit.powerfit(xs, ys)
            fitted = [a * (x ** b) for x in xs]
            return (f"y = {a:.6g}·x^{b:.6g}    R² = {r2:.6f}", fitted)
        # Linear or polynomial (both via polyfit).
        if model == _LINEAR:
            degree = 1
        else:
            try:
                degree = int(float(self._degree.text()))
            except ValueError:
                raise ValueError("degree must be a whole number")
        coeffs, r2 = curvefit.polyfit(xs, ys, degree)
        fitted = [curvefit.polyval(coeffs, x) for x in xs]
        terms = " + ".join(
            (f"{c:.6g}" if i == 0 else f"{c:.6g}·x^{i}") for i, c in enumerate(coeffs))
        return (f"y = {terms}    R² = {r2:.6f}", fitted)
