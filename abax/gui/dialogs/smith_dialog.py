"""Smith chart — plot a load impedance, its constant-VSWR circle, and the path
of each L-network that matches it.

Enter a load Z = R + jX on a system impedance Z0 and a frequency. The dialog
plots the load's reflection coefficient Γ with its constant-VSWR circle, reports
Γ (rectangular and polar), VSWR, return loss and mismatch loss, and lists every
lossless L-network that brings the *complex* load to Z0 — including the load's
reactance, which the previous version ignored. Choose a solution to draw its
path: a series element moves along a constant-resistance circle, a shunt
element along a constant-conductance circle, ending at the chart centre.

Accessibility: the chart is keyboard-focusable, labelled, and carries a written
description of everything drawn (updated on every change, and announced to
assistive technology); the readout is a read-only text area a screen reader
can move through line by line. Colours come from the theme palette, and every
mark on the chart is also labelled in text.
"""

from __future__ import annotations

import math

from .._qtcompat import (
    QAccessible,
    QAccessibleEvent,
    QBrush,
    QColor,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPainter,
    QPainterPath,
    QPen,
    QPlainTextEdit,
    QPointF,
    QPushButton,
    QRectF,
    Qt,
    QVBoxLayout,
    QWidget,
)
from ...core.science import rf

_R_CIRCLES = (0.2, 0.5, 1.0, 2.0, 5.0)
_X_ARCS = (0.2, 0.5, 1.0, 2.0, 5.0)


def fmt_component(c: dict) -> str:
    """An L-network element as text (``L = 38.98 nH`` / ``C = 0.923 pF``)."""
    if c["type"] == "L":
        hy = c["henrys"]
        return f"L = {hy * 1e9:.4g} nH" if hy < 1e-6 else f"L = {hy * 1e6:.4g} µH"
    if c["type"] == "C":
        fa = c["farads"]
        return f"C = {fa * 1e12:.4g} pF" if fa < 1e-9 else f"C = {fa * 1e9:.4g} nF"
    return "none"


def describe_solution(i: int, sol: dict) -> str:
    """One matching network in words, source-side element last."""
    if sol["topology"] == "none":
        return "Already matched: no network needed"
    if sol["topology"] == "shunt-at-load":
        return (f"{i}: shunt {fmt_component(sol['shunt'])} across the load, then series "
                f"{fmt_component(sol['series'])} toward the source")
    return (f"{i}: series {fmt_component(sol['series'])} at the load, then shunt "
            f"{fmt_component(sol['shunt'])} toward the source")


def analyse(r: float, x: float, z0: float, freq_hz: float) -> dict:
    """Everything the dialog shows, UI-free: Γ, VSWR, losses, match solutions,
    their paths, and the chart description."""
    zl = complex(r, x)
    g = rf.reflection_coefficient(zl, z0)
    mag = abs(g)
    ang = math.degrees(math.atan2(g.imag, g.real))
    vswr = rf.vswr_from_gamma(mag)
    rl = rf.return_loss_db(mag)
    ml = rf.mismatch_loss_db(mag)
    try:
        sols = rf.l_match_complex(zl, z0, freq_hz)
        match_error = ""
    except ValueError as exc:
        sols, match_error = [], str(exc)
    paths = [rf.match_path(zl, s, z0) for s in sols]
    vswr_txt = "infinite" if math.isinf(vswr) else f"{vswr:.2f}:1"
    rl_txt = "infinite (matched)" if math.isinf(rl) else f"{rl:.2f} dB"
    lines = [
        f"Load Z = {r:g} {'+' if x >= 0 else '−'} j{abs(x):g} Ω on Z0 = {z0:g} Ω "
        f"(normalized {r / z0:.3g} {'+' if x >= 0 else '−'} j{abs(x) / z0:.3g})",
        f"Γ = {g.real:.4f} {'+' if g.imag >= 0 else '−'} j{abs(g.imag):.4f}",
        f"|Γ| = {mag:.4f} at {ang:.1f}°",
        f"VSWR = {vswr_txt}",
        f"Return loss = {rl_txt}",
        f"Mismatch loss = {ml:.3f} dB",
        "",
        f"L-network matches at {freq_hz / 1e6:g} MHz:",
    ]
    lines += ([f"  {describe_solution(i, s)}" for i, s in enumerate(sols, 1)]
              or [f"  (none: {match_error or 'no lossless L-network exists'})"])
    where = ("the centre (matched)" if mag < 1e-9 else
             f"{mag:.2f} of the way from the centre to the edge, at {ang:.0f}°, in the "
             f"{'upper (inductive)' if g.imag > 0 else 'lower (capacitive)' if g.imag < 0 else 'resistive'} "
             "half")
    desc = (f"Smith chart for a load of {r:g} {'plus' if x >= 0 else 'minus'} j{abs(x):g} "
            f"ohms on {z0:g} ohms. The load point is {where}. "
            f"The dashed constant-VSWR circle through it marks VSWR {vswr_txt}; "
            f"return loss {rl_txt}.")
    return {"gamma": g, "vswr": vswr, "solutions": sols, "paths": paths,
            "lines": lines, "description": desc}


class SmithChart(QWidget):
    """A focusable Smith-chart canvas: grid, load point, constant-VSWR circle,
    and an optional match path, all labelled in text."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Smith chart")
        self._load: complex | None = None
        self._vswr_label = ""
        self._path: list[complex] = []
        self._path_label = ""

    def set_state(self, gamma: complex | None, vswr_label: str = "",
                  path: list[complex] | None = None, path_label: str = "") -> None:
        self._load = gamma
        self._vswr_label = vswr_label
        self._path = list(path or [])
        self._path_label = path_label
        self.update()

    def set_description(self, text: str) -> None:
        if text == self.accessibleDescription():
            return
        self.setAccessibleDescription(text)
        self.setToolTip(text)
        if QAccessible is not None and QAccessibleEvent is not None:
            try:
                QAccessible.updateAccessibility(
                    QAccessibleEvent(self, QAccessible.Event.DescriptionChanged))
            except Exception:  # noqa: BLE001
                pass

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        ink = pal.windowText().color()
        accent = pal.highlight().color()
        w, h = self.width(), self.height()
        radius = min(w, h) / 2.0 - 16.0
        cx, cy = w / 2.0, h / 2.0

        def xy(g: complex) -> QPointF:
            return QPointF(cx + g.real * radius, cy - g.imag * radius)

        unit = QPainterPath()
        unit.addEllipse(QPointF(cx, cy), radius, radius)
        faint = QColor(ink)
        faint.setAlpha(70)
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
        p.setPen(QPen(ink, 1.4))
        p.drawPath(unit)
        p.drawLine(QPointF(cx - radius, cy), QPointF(cx + radius, cy))

        # centre = matched to Z0
        p.setBrush(QBrush(ink))
        p.drawEllipse(QPointF(cx, cy), 2.5, 2.5)
        p.drawText(QPointF(cx + 5, cy + 14), "Z0")

        if self._load is not None:
            mag = abs(self._load)
            if 0.0 < mag < 1.0:                     # constant-VSWR circle (dashed = threshold-like)
                pen = QPen(ink, 1.0)
                pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, cy), mag * radius, mag * radius)
                p.drawText(QPointF(cx - 30, cy - mag * radius - 4), self._vswr_label)
            if len(self._path) > 1:                 # the chosen match path
                path = QPainterPath()
                path.moveTo(xy(self._path[0]))
                for g in self._path[1:]:
                    path.lineTo(xy(g))
                p.setPen(QPen(accent, 2.0))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
                mid = self._path[len(self._path) // 2]
                p.setBrush(QBrush(accent))
                p.setPen(QPen(pal.window().color(), 2.0))
                p.drawEllipse(xy(mid), 3.5, 3.5)
                p.setPen(QPen(ink, 1.0))
                p.drawText(xy(mid) + QPointF(6, -6), self._path_label)
            pt = xy(self._load)                      # load point: marker + surface ring + label
            p.setPen(QPen(pal.window().color(), 2.0))
            p.setBrush(QBrush(accent))
            p.drawEllipse(pt, 5.0, 5.0)
            p.setPen(QPen(ink, 1.0))
            p.drawText(pt + QPointF(8, -8), "Load")

        if self.hasFocus():
            p.setPen(QPen(accent, 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(1, 1, w - 2, h - 2))
        p.end()


class SmithDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Smith chart")
        self.setAccessibleName("Smith chart")
        self.resize(760, 480)
        self._result: dict | None = None
        self._build()
        self._plot()

    def _build(self) -> None:
        outer = QHBoxLayout(self)
        left = QVBoxLayout()
        self._chart = SmithChart(self)
        left.addWidget(self._chart, 1)
        self._summary = QLabel(self)
        self._summary.setWordWrap(True)
        self._summary.setAccessibleName("Smith chart summary")
        self._summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                              | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        left.addWidget(self._summary)
        outer.addLayout(left, 3)

        side = QVBoxLayout()
        form = QFormLayout()
        self._r = QLineEdit("75", self)
        self._x = QLineEdit("25", self)
        self._z0 = QLineEdit("50", self)
        self._freq = QLineEdit("14.2", self)
        for le, label, name in ((self._r, "Load &R (Ω):", "Load resistance in ohms"),
                                (self._x, "Load &X (Ω):",
                                 "Load reactance in ohms, positive inductive"),
                                (self._z0, "&Z0 (Ω):", "System impedance in ohms"),
                                (self._freq, "&Frequency (MHz):", "Frequency in megahertz")):
            le.setAccessibleName(name)
            le.returnPressed.connect(self._plot)
            form.addRow(label, le)
        side.addLayout(form)
        btn = QPushButton("&Plot && match", self)
        btn.clicked.connect(self._plot)
        side.addWidget(btn)
        self._solution = QComboBox(self)
        self._solution.setAccessibleName("Matching network to draw")
        self._solution.currentIndexChanged.connect(self._draw_solution)
        pick = QLabel("&Draw match:", self)
        pick.setBuddy(self._solution)
        side.addWidget(pick)
        side.addWidget(self._solution)
        self._readout = QPlainTextEdit(self)
        self._readout.setReadOnly(True)
        self._readout.setAccessibleName("Smith chart results")
        side.addWidget(self._readout, 1)
        outer.addLayout(side, 2)

    def gamma(self) -> complex:
        """Reflection coefficient Γ for the current inputs (UI-free; testable)."""
        z0 = float(self._z0.text())
        zl = complex(float(self._r.text()), float(self._x.text()))
        return rf.reflection_coefficient(zl, z0)

    def _plot(self) -> None:
        try:
            r, x, z0 = float(self._r.text()), float(self._x.text()), float(self._z0.text())
            freq = float(self._freq.text()) * 1e6
            res = analyse(r, x, z0, freq)
        except (ValueError, ZeroDivisionError) as exc:
            msg = f"Enter numeric R, X, Z0 and frequency ({exc})."
            self._readout.setPlainText(msg)
            self._summary.setText(msg)
            return
        self._result = res
        self._readout.setPlainText("\n".join(res["lines"]))
        self._solution.blockSignals(True)
        self._solution.clear()
        self._solution.addItem("None")
        for i, s in enumerate(res["solutions"], 1):
            if s["topology"] != "none":
                self._solution.addItem(describe_solution(i, s))
        self._solution.setCurrentIndex(1 if self._solution.count() > 1 else 0)
        self._solution.blockSignals(False)
        self._draw_solution()

    def _draw_solution(self) -> None:
        res = self._result
        if res is None:
            return
        idx = self._solution.currentIndex() - 1
        vswr = res["vswr"]
        vswr_label = "" if math.isinf(vswr) else f"VSWR {vswr:.2f}:1"
        desc = res["description"]
        if 0 <= idx < len(res["paths"]):
            sol_text = self._solution.currentText()
            self._chart.set_state(res["gamma"], vswr_label, res["paths"][idx], f"match {idx + 1}")
            detail = sol_text.split(": ", 1)[-1]
            desc += (f" Drawn in the accent colour: the path of match {idx + 1} "
                     f"({detail}), from the load to the centre, where the load "
                     "is matched to Z0.")
        else:
            self._chart.set_state(res["gamma"], vswr_label)
        self._summary.setText(desc)
        self._chart.set_description(desc)
