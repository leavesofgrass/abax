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
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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


#: The free-space caveat carried into plot titles and the sheet header. The
#: built-in MoM and calc-mode-0 PyNEC results are free space, so the elevation
#: cut is symmetric about the horizon and is NOT an installed-height take-off
#: pattern — the label keeps that from being mistaken for a real ground pattern.
FREE_SPACE = "(free space)"
#: Companion caveat for the image-plane ground model: the elevation cut is a real
#: take-off pattern (asymmetric about the horizon, zero below it).
OVER_GROUND = "(over ground)"

#: The Ground combobox choices, in order. "Free space" leaves the classic
#: behaviour untouched; the others fold in the image-plane reflection.
GROUND_CHOICES = ("Free space", "Perfect ground", "Perfect ground + height")


def raise_to_height(wires, height: float):
    """Offset every wire in +z so the structure stands ``height`` wavelengths above
    the ``z = 0`` ground plane. The dialog's elements are z-directed (vertical), so
    this lifts a vertical radiator's base to the requested height."""
    if height == 0.0:
        return wires
    return [[(x, y, z + height) for (x, y, z) in pts] for pts in wires]


def ground_from_choice(choice: str, height: float = 0.0):
    """Map a Ground-combobox ``choice`` to ``(ground, height)``.

    Returns ``(None, 0.0)`` for free space (the classic path), a perfect
    :class:`~abax.core.science.wire_mom.Ground` with the structure sitting on the
    plane for "Perfect ground", and the same ground raised to ``height`` for
    "Perfect ground + height"."""
    from ...core.science import wire_mom

    if choice == GROUND_CHOICES[0]:
        return None, 0.0
    if choice == GROUND_CHOICES[1]:
        return wire_mom.Ground("perfect"), 0.0
    if choice == GROUND_CHOICES[2]:
        return wire_mom.Ground("perfect"), float(height)
    raise ValueError(f"unknown ground choice {choice!r}")


def pattern_cut_ground(kind: str, params: dict, choice: str, height: float = 0.0,
                       plane: str = "elevation", count: int = 361,
                       decibels: bool = True, segments: int = _SEGMENTS):
    """A radiation cut that honours the ground option, as ``(samples, source)``.

    For "Free space" this defers to :func:`pattern_cut` (unchanged, PyNEC-preferred
    where present). For a ground choice it always uses the built-in MoM image model
    (:func:`abax.core.science.wire_mom.pattern_cut` with a ``Ground``) — PyNEC's
    free-space read-back cannot express the take-off pattern — lifting the geometry
    to ``height`` first. The elevation cut then shows a real take-off angle and is
    zero below the horizon; the azimuth cut over ground is taken at the horizon."""
    from ...core.science import wire_mom

    ground, h = ground_from_choice(choice, height)
    if ground is None:
        return pattern_cut(kind, params, plane=plane, count=count,
                           decibels=decibels, segments=segments)
    wires, feed = build_geometry(kind, params, segments)
    wires = raise_to_height(wires, h)
    result = wire_mom.solve(wires, [(0, feed, 1.0)])
    samples = wire_mom.pattern_cut(wires, result, plane=plane, count=count,
                                   decibels=decibels, ground=ground)
    return samples, "mom-ground"


def pattern_cut(kind: str, params: dict, plane: str = "azimuth",
                count: int = 361, decibels: bool = True,
                segments: int = _SEGMENTS):
    """A free-space radiation cut as ``[(angle_rad, value)]`` samples plus a source.

    Builds the geometry for ``kind``/``params`` (see :func:`build_geometry`) and
    computes an ``azimuth`` or ``elevation`` cut, **preferring PyNEC** when it is
    installed and falling back to the built-in MoM otherwise. Returns
    ``(samples, source)`` where ``source`` is ``"pynec"`` or ``"mom"``. The result
    is free space: the elevation cut is symmetric about the horizon and is not an
    over-ground take-off pattern."""
    from ...core.science import nec, wire_mom

    wires, feed = build_geometry(kind, params, segments)

    # Prefer the reference solver when present; any PyNEC hiccup silently degrades
    # to the always-available built-in MoM so the dialog never dead-ends.
    try:
        from ...engine import necpy

        if necpy.available():
            radii = [1e-3] * len(wires)
            deck = nec.to_nec(wires, [(0, feed, 1.0)], 300.0, radii_wl=radii,
                              comment=f"abax {kind}")
            samples = necpy.pattern_cut(deck, plane=plane, count=count,
                                        decibels=decibels)
            return samples, "pynec"
    except Exception:
        pass

    result = wire_mom.solve(wires, [(0, feed, 1.0)])
    samples = wire_mom.pattern_cut(wires, result, plane=plane,
                                   count=count, decibels=decibels)
    return samples, "mom"


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

        self._plane = QComboBox(self)
        self._plane.addItems(["Azimuth", "Elevation"])
        self._plane.currentIndexChanged.connect(self._plot_pattern)
        form.addRow("Pattern plane:", self._plane)

        self._ground = QComboBox(self)
        self._ground.addItems(list(GROUND_CHOICES))
        self._ground.setToolTip(
            "Free space keeps the classic symmetric pattern; a ground option folds "
            "in an image-plane reflection so the elevation cut shows a real "
            "take-off angle.")
        self._ground.currentIndexChanged.connect(self._on_ground_changed)
        form.addRow("Ground:", self._ground)

        self._height = QLineEdit("0.5", self)
        self._height.setToolTip("Height of the antenna base above ground (λ).")
        self._height.editingFinished.connect(self._plot_pattern)
        self._height.returnPressed.connect(self._plot_pattern)
        self._height_row = ("Height above ground (λ):", self._height)
        form.addRow(*self._height_row)
        side.addLayout(form)

        run_btn = QPushButton("Run model", self)
        run_btn.clicked.connect(self._run)
        side.addWidget(run_btn)

        pat_btn = QPushButton("Radiation pattern", self)
        pat_btn.setToolTip(
            "Compute an azimuth/elevation cut and plot it (free space or over "
            "ground per the Ground option)")
        pat_btn.clicked.connect(self._plot_pattern)
        side.addWidget(pat_btn)

        sheet_btn = QPushButton("Pattern → sheet", self)
        sheet_btn.setToolTip("Write the (angle, gain) samples to a new sheet")
        sheet_btn.clicked.connect(self._pattern_to_sheet)
        side.addWidget(sheet_btn)

        svg_btn = QPushButton("Export pattern SVG...", self)
        svg_btn.clicked.connect(self._export_pattern_svg)
        side.addWidget(svg_btn)

        # Cached from the last pattern compute, for the sheet / SVG writers.
        self._pattern: list = []
        self._pattern_source = ""

        self._readout = QLabel(self)
        self._readout.setWordWrap(True)
        side.addWidget(self._readout, 1)
        outer.addLayout(side)

        self._on_kind_changed()
        self._on_ground_changed()

    def _is_yagi(self) -> bool:
        return self._kind.currentIndex() == 1

    def _on_kind_changed(self) -> None:
        yagi = self._is_yagi()
        for _, edit in (self._refl_row, self._dir_row,
                        self._refl_sp_row, self._dir_sp_row):
            edit.setEnabled(yagi)
        self._run()

    def _ground_choice(self) -> str:
        return self._ground.currentText()

    def _ground_height(self) -> float:
        try:
            return float(self._height.text())
        except ValueError:
            return 0.0

    def _over_ground(self) -> bool:
        return self._ground_choice() != GROUND_CHOICES[0]

    def _on_ground_changed(self) -> None:
        # The height field only applies to the "+ height" choice.
        self._height.setEnabled(self._ground_choice() == GROUND_CHOICES[2])
        self._plot_pattern()

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

    # --- radiation-pattern read-back ---------------------------------------

    def _selected_plane(self) -> str:
        return "elevation" if self._plane.currentIndex() == 1 else "azimuth"

    def compute_pattern(self, count: int = 361):
        """Compute the current model's radiation cut (UI-free; testable).

        Returns ``(samples, source)`` for the selected plane and Ground option, and
        **caches** the samples on the dialog for the sheet / SVG writers. In free
        space this prefers PyNEC when installed and otherwise the built-in MoM (and
        the elevation cut is symmetric about the horizon). Over ground it uses the
        built-in image model (``source`` ``"mom-ground"``), so the elevation cut is
        a real take-off pattern, zero below the horizon."""
        kind, params = self._params()
        plane = self._selected_plane()
        if self._over_ground():
            samples, source = pattern_cut_ground(
                kind, params, self._ground_choice(), self._ground_height(),
                plane=plane, count=count, decibels=True)
        else:
            samples, source = pattern_cut(kind, params, plane=plane,
                                          count=count, decibels=True)
        self._pattern = samples
        self._pattern_source = source
        return samples, source

    def _ground_caveat(self) -> str:
        """The ``(free space)`` / ``(over ground)`` tag for titles and headers."""
        return OVER_GROUND if self._over_ground() else FREE_SPACE

    def _source_label(self) -> str:
        return {
            "pynec": "PyNEC",
            "mom": "MoM",
            "mom-ground": "MoM + ground image",
        }.get(self._pattern_source, "MoM")

    def _pattern_title(self) -> str:
        kind, _ = self._params()
        plane = self._selected_plane().capitalize()
        src = self._source_label()
        tag = self._ground_caveat()
        if self._over_ground() and self._ground_choice() == GROUND_CHOICES[2]:
            tag = f"(over ground, h={self._ground_height():g}λ)"
        return f"{kind.capitalize()} {plane} pattern {tag} — {src}"

    def _plot_pattern(self) -> None:
        try:
            samples, source = self.compute_pattern()
        except (ValueError, KeyError, ZeroDivisionError):
            self._readout.setText("Dimensions must be positive numbers (in wavelengths).")
            return
        self._plotw.set_samples(samples)
        plane = self._selected_plane().capitalize()
        src = self._source_label()
        if self._over_ground():
            note = (
                "Over ground: the elevation cut is a real take-off pattern "
                "(asymmetric about the horizon, zero below it).")
        else:
            note = (
                "Free space: the elevation cut is symmetric about the horizon and "
                "is not a real over-ground take-off pattern.")
        self._readout.setText(
            f"{plane} pattern {self._ground_caveat()}\n"
            f"Source: {src}\n{note}")

    def _pattern_to_sheet(self) -> None:
        from ...core.science import wire_mom

        if not self._pattern:
            try:
                self.compute_pattern()
            except (ValueError, KeyError, ZeroDivisionError):
                QMessageBox.warning(self, "Radiation pattern",
                                    "Fix the dimensions first (wavelengths).")
                return
        headers, rows = wire_mom.pattern_to_rows(self._pattern, decibels=True)
        confirm = QMessageBox.question(
            self, "Radiation pattern",
            f"Write {len(rows)} {self._selected_plane()} samples "
            f"{self._ground_caveat()} to a new sheet?")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        wb = self._win._doc.workbook
        name = self._win._unique_sheet_name("Pattern")
        sheet = wb.add_sheet(name)
        title = self._pattern_title()
        sheet.set_cell(0, 0, title)
        for j, head in enumerate(headers):
            sheet.set_cell(1, j, head)
        for i, row in enumerate(rows, start=2):
            for j, cell in enumerate(row):
                sheet.set_cell(i, j, cell)
        wb.active = len(wb.sheets) - 1
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(
            f"Radiation pattern -> sheet '{name}' {self._ground_caveat()}")

    def _export_pattern_svg(self) -> None:
        from pathlib import Path

        from ...core.science import antenna

        if not self._pattern:
            try:
                self.compute_pattern()
            except (ValueError, KeyError, ZeroDivisionError):
                QMessageBox.warning(self, "Export pattern SVG",
                                    "Fix the dimensions first (wavelengths).")
                return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export pattern as SVG", "pattern.svg", "SVG image (*.svg)")
        if not path:
            return
        svg = antenna.polar_svg(self._pattern, title=self._pattern_title())
        try:
            Path(path).write_text(svg, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Export pattern SVG", str(exc))
            return
        self._win._set_status(f"Saved pattern SVG: {Path(path).name}")
