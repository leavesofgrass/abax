"""Antenna modeler — a method-of-moments (MoM) dialog for real wire antennas.

Unlike the analytic :mod:`antenna_dialog` (closed-form patterns), this dialog
drives :mod:`abax.core.science.wire_mom`, a thin-wire MoM solver, to model an
actual **dipole** or **Yagi-Uda** array from its physical dimensions (in
wavelengths). It reports the modelled **gain (dBi)**, **front-to-back ratio
(dB)**, and **feed-point impedance Zin = R + jX**, and draws the azimuth
radiation pattern with the same QPainter polar widget the analytic dialog uses.

The geometry-building and analysis helpers are UI-free and directly testable.
"""

from __future__ import annotations

import math

from .antenna_dialog import PolarPlot
from .._qtcompat import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

_SEGMENTS = 12


def _element(length: float, x: float, segments: int = _SEGMENTS):
    """A z-directed wire of the given length centred at ``(x, 0, 0)``.

    Returns an even number of segments so an interior node sits at the centre
    (the feed point of the driven element)."""
    n = max(2, segments + (segments & 1))
    half = length / 2.0
    dz = length / n
    return [(x, 0.0, -half + i * dz) for i in range(n + 1)]


def _center_node(segments: int = _SEGMENTS) -> int:
    return max(2, segments + (segments & 1)) // 2


def build_geometry(kind: str, params: dict, segments: int = _SEGMENTS):
    """Return ``(wires, feed_node)`` for ``kind`` in {"dipole", "yagi"}.

    ``params`` for a dipole: ``{"driven": length_wl}``. For a Yagi it adds
    ``reflector``/``director`` lengths and ``refl_spacing``/``dir_spacing``
    (wavelengths); the reflector sits behind the driven element (−x) and the
    director in front (+x). The driven element is always wire 0, fed at its
    centre node."""
    driven = float(params["driven"])
    wires = [_element(driven, 0.0, segments)]
    if kind == "yagi":
        reflector = float(params["reflector"])
        director = float(params["director"])
        refl_spacing = float(params["refl_spacing"])
        dir_spacing = float(params["dir_spacing"])
        wires.append(_element(reflector, -abs(refl_spacing), segments))
        wires.append(_element(director, abs(dir_spacing), segments))
    return wires, _center_node(segments)


def directivity_dbi(wires, result, n_theta: int = 24, n_phi: int = 48) -> float:
    """Lossless gain (directivity) in dBi from a solved wire structure.

    ``D = 4π · U_max / ∮ U dΩ`` where ``U`` is the (relative) radiation
    intensity from :func:`wire_mom.far_field_intensity`; the arbitrary common
    scale cancels. The sphere is integrated with the trapezoidal rule in θ and
    the midpoint rule in φ."""
    from ...core.science import wire_mom

    u_max = 0.0
    total = 0.0
    for i in range(n_theta + 1):
        theta = math.pi * i / n_theta
        wt = 0.5 if i in (0, n_theta) else 1.0
        st = math.sin(theta)
        for j in range(n_phi):
            phi = 2.0 * math.pi * j / n_phi
            u = wire_mom.far_field_intensity(wires, result, theta, phi)
            u_max = max(u_max, u)
            total += wt * u * st
    integ = total * (math.pi / n_theta) * (2.0 * math.pi / n_phi)
    if integ <= 0.0 or u_max <= 0.0:
        return float("-inf")
    return 10.0 * math.log10(4.0 * math.pi * u_max / integ)


def azimuth_pattern(wires, result, count: int = 361):
    """Normalised azimuth-plane pattern as ``[(theta_plot, mag 0..1)]``.

    Sweeps φ in the elevation plane θ = 90° (the array's plane). The PolarPlot
    widget measures its angle from the vertical, so φ maps straight onto that
    angle; magnitudes are field (√intensity) normalised to the peak."""
    from ...core.science import wire_mom

    theta = math.pi / 2.0
    raw = []
    peak = 0.0
    for i in range(count):
        phi = 2.0 * math.pi * i / (count - 1)
        u = wire_mom.far_field_intensity(wires, result, theta, phi)
        mag = math.sqrt(max(0.0, u))
        peak = max(peak, mag)
        raw.append((phi, mag))
    if peak <= 0.0:
        return [(phi, 0.0) for phi, _ in raw]
    return [(phi, mag / peak) for phi, mag in raw]


class AntennaModelerDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Antenna modeler")
        self.resize(620, 460)
        self._build()
        self._run()

    def _build(self) -> None:
        outer = QHBoxLayout(self)
        self._plotw = PolarPlot(self)
        outer.addWidget(self._plotw, 1)

        side = QVBoxLayout()
        form = QFormLayout()
        self._kind = QComboBox(self)
        self._kind.addItems(["Dipole", "Yagi"])
        self._kind.currentIndexChanged.connect(self._on_kind_changed)

        self._driven = QLineEdit("0.47", self)
        self._reflector = QLineEdit("0.5", self)
        self._director = QLineEdit("0.44", self)
        self._refl_spacing = QLineEdit("0.2", self)
        self._dir_spacing = QLineEdit("0.15", self)
        for edit in (self._driven, self._reflector, self._director,
                     self._refl_spacing, self._dir_spacing):
            edit.editingFinished.connect(self._run)
            edit.returnPressed.connect(self._run)

        form.addRow("Antenna:", self._kind)
        form.addRow("Driven length (λ):", self._driven)
        self._refl_row = ("Reflector length (λ):", self._reflector)
        self._dir_row = ("Director length (λ):", self._director)
        self._refl_sp_row = ("Reflector spacing (λ):", self._refl_spacing)
        self._dir_sp_row = ("Director spacing (λ):", self._dir_spacing)
        form.addRow(*self._refl_row)
        form.addRow(*self._dir_row)
        form.addRow(*self._refl_sp_row)
        form.addRow(*self._dir_sp_row)
        side.addLayout(form)

        run_btn = QPushButton("Run model", self)
        run_btn.clicked.connect(self._run)
        side.addWidget(run_btn)

        self._readout = QLabel(self)
        self._readout.setWordWrap(True)
        side.addWidget(self._readout, 1)
        outer.addLayout(side)

        self._on_kind_changed()

    def _is_yagi(self) -> bool:
        return self._kind.currentIndex() == 1

    def _on_kind_changed(self) -> None:
        yagi = self._is_yagi()
        for _, edit in (self._refl_row, self._dir_row,
                        self._refl_sp_row, self._dir_sp_row):
            edit.setEnabled(yagi)
        self._run()

    def _params(self) -> tuple[str, dict]:
        """Read the form into ``(kind, params)`` for :func:`build_geometry`."""
        if self._is_yagi():
            return "yagi", {
                "driven": float(self._driven.text()),
                "reflector": float(self._reflector.text()),
                "director": float(self._director.text()),
                "refl_spacing": float(self._refl_spacing.text()),
                "dir_spacing": float(self._dir_spacing.text()),
            }
        return "dipole", {"driven": float(self._driven.text())}

    def analyze(self) -> dict:
        """Solve the current geometry (UI-free); returns a results dict."""
        from ...core.science import wire_mom

        kind, params = self._params()
        wires, feed = build_geometry(kind, params)
        result = wire_mom.solve(wires, [(0, feed, 1.0)])
        zin = result["feed_impedance"][(0, feed)]
        out = {
            "kind": kind,
            "gain_dbi": directivity_dbi(wires, result),
            "zin": zin,
            "pattern": azimuth_pattern(wires, result),
        }
        # Front-to-back is only meaningful for a directional array.
        out["front_to_back_db"] = (
            wire_mom.front_to_back_db(wires, result) if kind == "yagi" else None)
        return out

    def _run(self) -> None:
        try:
            res = self.analyze()
        except (ValueError, KeyError, ZeroDivisionError):
            self._readout.setText("Dimensions must be positive numbers (in wavelengths).")
            return
        self._plotw.set_samples(res["pattern"])
        zin = res["zin"]
        sign = "+" if zin.imag >= 0 else "-"
        lines = [
            f"Gain: {res['gain_dbi']:.2f} dBi",
            f"Zin: {zin.real:.1f} {sign} j{abs(zin.imag):.1f} Ω",
        ]
        if res["front_to_back_db"] is not None:
            lines.insert(1, f"Front/back: {res['front_to_back_db']:.1f} dB")
        self._readout.setText("\n".join(lines))
