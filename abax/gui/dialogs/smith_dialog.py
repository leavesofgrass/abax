"""Smith chart — plot a load impedance, its reflection coefficient, and an
L-network match.

The chart is QPainter-drawn (constant-resistance circles + constant-reactance arcs
clipped to the unit circle). Enter a load Z = R + jX on a system impedance Z0 and a
frequency; the dialog plots Γ, reports VSWR / return loss, and computes the
two L-network solutions that bring the resistive part to Z0.
"""

from __future__ import annotations

from .._qtcompat import (
    QBrush,
    QColor,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPainter,
    QPainterPath,
    QPen,
    QPointF,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
)

_R_CIRCLES = (0.2, 0.5, 1.0, 2.0, 5.0)
_X_ARCS = (0.2, 0.5, 1.0, 2.0, 5.0)


class SmithChart(QWidget):
    """A Smith-chart canvas. ``set_points`` takes ``(re_gamma, im_gamma, color,
    label)`` tuples to plot (each as a dot + a vector from the centre)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(280, 280)
        self._points: list = []

    def set_points(self, points: list) -> None:
        self._points = list(points)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        radius = min(w, h) / 2.0 - 14.0
        cx, cy = w / 2.0, h / 2.0
        grid = self.palette().windowText().color()

        unit = QPainterPath()
        unit.addEllipse(QPointF(cx, cy), radius, radius)
        p.setPen(QPen(grid, 1.4))
        p.drawPath(unit)
        p.drawLine(QPointF(cx - radius, cy), QPointF(cx + radius, cy))

        faint = QColor(grid)
        faint.setAlpha(90)
        p.save()
        p.setClipPath(unit)
        p.setPen(QPen(faint, 1.0))
        for r in _R_CIRCLES:                       # constant-resistance circles
            rad = radius / (r + 1.0)
            p.drawEllipse(QPointF(cx + (r / (r + 1.0)) * radius, cy), rad, rad)
        for x in _X_ARCS:                          # constant-reactance arcs (±)
            rad = radius / x
            p.drawEllipse(QPointF(cx + radius, cy - (1.0 / x) * radius), rad, rad)
            p.drawEllipse(QPointF(cx + radius, cy + (1.0 / x) * radius), rad, rad)
        p.restore()

        for re, im, color, label in self._points:
            px, py = cx + re * radius, cy - im * radius
            col = QColor(color)
            p.setPen(QPen(col, 2.0))
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(px, py), 4.0, 4.0)
            p.drawLine(QPointF(cx, cy), QPointF(px, py))
            if label:
                p.drawText(QPointF(px + 6.0, py - 6.0), label)
        p.end()


class SmithDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Smith chart")
        self.resize(560, 420)
        self._build()
        self._plot()

    def _build(self) -> None:
        outer = QHBoxLayout(self)
        self._chart = SmithChart(self)
        outer.addWidget(self._chart, 1)

        side = QVBoxLayout()
        form = QFormLayout()
        self._r = QLineEdit("75", self)
        self._x = QLineEdit("25", self)
        self._z0 = QLineEdit("50", self)
        self._freq = QLineEdit("14.2", self)
        form.addRow("Load R (Ω):", self._r)
        form.addRow("Load X (Ω):", self._x)
        form.addRow("Z0 (Ω):", self._z0)
        form.addRow("Frequency (MHz):", self._freq)
        side.addLayout(form)
        btn = QPushButton("Plot && match", self)
        btn.clicked.connect(self._plot)
        side.addWidget(btn)
        self._readout = QLabel(self)
        self._readout.setWordWrap(True)
        self._readout.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        side.addWidget(self._readout, 1)
        outer.addLayout(side)

    def gamma(self) -> complex:
        """Reflection coefficient Γ for the current inputs (UI-free; testable)."""
        from ...core.science import rf

        z0 = float(self._z0.text())
        zl = complex(float(self._r.text()), float(self._x.text()))
        return rf.reflection_coefficient(zl, z0)

    def _plot(self) -> None:
        from ...core.science import rf

        try:
            g = self.gamma()
            r, x, z0 = float(self._r.text()), float(self._x.text()), float(self._z0.text())
            freq = float(self._freq.text()) * 1e6
        except (ValueError, ZeroDivisionError):
            self._readout.setText("Enter numeric R, X, Z0, and frequency.")
            return
        mag = abs(g)
        vswr = rf.vswr_from_gamma(mag)
        rl = rf.return_loss_db(mag)
        self._chart.set_points([
            (g.real, g.imag, "#e06c75", f"Z = {r:g}{x:+g}j"),
            (0.0, 0.0, "#98c379", "matched"),
        ])
        lines = [
            f"Γ = {g.real:.3f}{g.imag:+.3f}j   |Γ| = {mag:.3f}",
            f"VSWR = {vswr:.2f} : 1",
            f"Return loss = {rl:.2f} dB",
            "",
            "L-network (resistive part):",
        ]
        try:
            for i, s in enumerate(rf.l_match(complex(z0), complex(r), freq), 1):
                lines.append(f"  {i}: series {self._comp(s['series'])}, "
                             f"shunt {self._comp(s['shunt'])}")
        except (ValueError, ZeroDivisionError) as exc:
            lines.append(f"  (no match: {exc})")
        self._readout.setText("\n".join(lines))

    @staticmethod
    def _comp(c: dict) -> str:
        if c["type"] == "L":
            hy = c["henrys"]
            return f"L={hy * 1e9:.1f}nH" if hy < 1e-6 else f"L={hy * 1e6:.2f}µH"
        if c["type"] == "C":
            fa = c["farads"]
            return f"C={fa * 1e12:.1f}pF" if fa < 1e-9 else f"C={fa * 1e9:.2f}nF"
        return "through"
