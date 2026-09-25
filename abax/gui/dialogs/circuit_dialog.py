"""Circuit calculator — Ohm's law, RC/RL time constants, RLC resonance, and
impedance, with accessible graphs.

Four tabs, each a small form. Values accept engineering notation ("50u",
"40 pF", "3.5 MHz"). Every graph is paired with the same data as a table, a
written summary (also the chart's accessible description), and a *Data → new
sheet* button, so nothing is available only as a picture.

The computations are plain functions (``compute_*``) returning the result rows,
the plotted series and the description, so they are testable without a UI.
Backed by :mod:`abax.core.science.circuits`.
"""

from __future__ import annotations

import math

from ._graphpanel import GraphPanel, format_rows, rows_to_new_sheet
from .._qtcompat import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from ...core.science import circuits
from ...core.science.engnum import fmt_eng, parse_eng

# --- pure computations (UI-free) ----------------------------------------------


def compute_ohms(raw: dict) -> list[tuple[str, str]]:
    """``raw`` maps voltage/current/resistance/power to text; blanks are unknown."""
    vals = {k: (parse_eng(v, u) if v.strip() else None)
            for (k, u), v in zip((("voltage", "V"), ("current", "A"),
                                  ("resistance", "Ω"), ("power", "W")),
                                 (raw["voltage"], raw["current"],
                                  raw["resistance"], raw["power"]))}
    out = circuits.solve_ohms_law(vals["voltage"], vals["current"],
                                  vals["resistance"], vals["power"])
    return [
        ("Voltage (E)", fmt_eng(out["voltage"], "V")),
        ("Current (I)", fmt_eng(out["current"], "A")),
        ("Resistance (R)", fmt_eng(out["resistance"], "Ω")),
        ("Power (P)", fmt_eng(out["power"], "W")),
    ]


def compute_time_constant(raw: dict) -> dict:
    """RC or RL time constant plus the 0–5τ charge/discharge curve."""
    r = parse_eng(raw["r"], "Ω")
    kind = raw["kind"]
    if kind == "RC":
        tau = circuits.tau_rc(r, parse_eng(raw["part"], "F"))
    else:
        tau = circuits.tau_rl(r, parse_eng(raw["part"], "H"))
    charging = raw["direction"] == "charge"
    frac = circuits.charge_fraction if charging else circuits.decay_fraction
    curve = [(i / 20.0, 100.0 * frac(i / 20.0, 1.0)) for i in range(0, 101)]
    table = [(n, n * tau, 100.0 * frac(n, 1.0)) for n in range(0, 6)]
    quantity = ("capacitor voltage" if kind == "RC" else "inductor current")
    verb = "charging" if charging else "discharging"
    steps = ", ".join(f"{p:.1f}% at {n}τ" for n, _, p in table[1:])
    desc = (f"Line chart of {quantity} while {verb}, in percent of the "
            f"{'final' if charging else 'starting'} value, against time from 0 to "
            f"5 time constants. τ = {fmt_eng(tau, 's')}. {steps}.")
    rows = [("Time constant τ", fmt_eng(tau, "s"))]
    rows += [(f"{n}τ = {fmt_eng(t, 's')}", f"{p:.1f} %") for n, t, p in table[1:]]
    return {"tau": tau, "rows": rows, "curve": curve, "table": table,
            "description": desc, "y_label": f"% of {'final' if charging else 'start'}"}


def compute_resonance(raw: dict) -> dict:
    """Series/parallel RLC resonance, Q, −3 dB bandwidth, and the response curve."""
    r = parse_eng(raw["r"], "Ω")
    ind = parse_eng(raw["l"], "H")
    cap = parse_eng(raw["c"], "F")
    topo = raw["topology"]
    info = circuits.rlc_resonance(r, ind, cap, topo)
    f0, bw = info["f0"], info["bandwidth"]
    span = max(3.0 * bw, 1e-6 * f0)
    lo = max(f0 - span, f0 * 1e-3)
    hi = f0 + span
    curve = []
    for i in range(0, 241):
        f = lo + (hi - lo) * i / 240.0
        curve.append((f, 100.0 * circuits.rlc_relative_response(f, r, ind, cap, topo)))
    what = "current" if topo == "series" else "impedance"
    desc = (f"Line chart of {topo} RLC {what} relative to its peak, in percent, "
            f"against frequency from {fmt_eng(lo, 'Hz')} to {fmt_eng(hi, 'Hz')}. "
            f"Peak 100% at the resonant frequency {fmt_eng(f0, 'Hz')}. "
            f"Half-power (70.7%, minus 3 dB) points at {fmt_eng(info['f_low'], 'Hz')} "
            f"and {fmt_eng(info['f_high'], 'Hz')}: bandwidth {fmt_eng(bw, 'Hz')}, "
            f"Q {info['q']:.4g}.")
    rows = [
        ("Resonant frequency f0", fmt_eng(f0, "Hz")),
        ("Reactance of L (= C) at f0", fmt_eng(info["x0"], "Ω")),
        ("Q", f"{info['q']:.4g}"),
        ("Bandwidth (−3 dB)", fmt_eng(bw, "Hz")),
        ("Lower half-power frequency", fmt_eng(info["f_low"], "Hz")),
        ("Upper half-power frequency", fmt_eng(info["f_high"], "Hz")),
    ]
    table = [(f, pct) for f, pct in curve[::12]]
    return {"info": info, "rows": rows, "curve": curve, "table": table,
            "description": desc, "range": (lo, hi)}


def compute_impedance(raw: dict) -> list[tuple[str, str]]:
    """Impedance, admittance and phase of R, L, C in series or parallel at f."""
    f = parse_eng(raw["freq"], "Hz")
    r = parse_eng(raw["r"] or "0", "Ω")
    ind = parse_eng(raw["l"] or "0", "H")
    cap = parse_eng(raw["c"] or "0", "F")
    fn = (circuits.series_rlc_impedance if raw["topology"] == "series"
          else circuits.parallel_rlc_impedance)
    z = fn(f, r, ind, cap)
    rows = [("Impedance Z (rectangular)", f"{z.real:.4g} {'+' if z.imag >= 0 else '−'} "
                                          f"j{abs(z.imag):.4g} Ω")]
    if z != 0:
        theta = circuits.phase_angle_deg(z)
        y = circuits.admittance(z)
        if abs(theta) < 1e-9:
            lead = "resistive: voltage and current in phase"
        elif theta > 0:
            lead = "inductive: voltage leads current"
        else:
            lead = "capacitive: voltage lags current"
        rows += [
            ("Impedance Z (polar)", f"{abs(z):.4g} Ω ∠ {theta:.2f}°"),
            ("Phase angle", f"{theta:.2f}° ({lead})"),
            ("Power factor", f"{circuits.power_factor(z):.4f}"),
            ("Admittance Y", f"{y.real:.4g} {'+' if y.imag >= 0 else '−'} "
                             f"j{abs(y.imag):.4g} S"),
            ("Admittance Y (polar)", f"{abs(y):.4g} S ∠ {-theta:.2f}°"),
        ]
    return rows


# --- UI -------------------------------------------------------------------------


class CircuitDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Circuit calculator")
        self.setAccessibleName("Circuit calculator")
        self.resize(900, 560)
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.tabs.setAccessibleName("Circuit calculator sections")
        outer.addWidget(self.tabs)
        self._build_ohms()
        self._build_tau()
        self._build_resonance()
        self._build_impedance()
        self.compute_tau()
        self.compute_resonance()

    # --- Ohm's law ---------------------------------------------------------------

    def _build_ohms(self) -> None:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        hint = QLabel("Enter any two values; leave the other two blank.", page)
        hint.setWordWrap(True)
        lay.addWidget(hint)
        form = QFormLayout()
        self._ohm = {}
        for key, label, unit in (("voltage", "&Voltage E (V):", "volts"),
                                 ("current", "C&urrent I (A):", "amperes"),
                                 ("resistance", "&Resistance R (Ω):", "ohms"),
                                 ("power", "&Power P (W):", "watts")):
            le = QLineEdit(page)
            le.setAccessibleName(f"{key.capitalize()} in {unit}")
            le.returnPressed.connect(self.compute_ohms)
            form.addRow(label, le)
            self._ohm[key] = le
        self._ohm["voltage"].setText("100")
        self._ohm["resistance"].setText("50")
        lay.addLayout(form)
        btn = QPushButton("&Solve", page)
        btn.clicked.connect(self.compute_ohms)
        lay.addWidget(btn)
        self._ohm_out = QPlainTextEdit(page)
        self._ohm_out.setReadOnly(True)
        self._ohm_out.setAccessibleName("Ohm's law results")
        lay.addWidget(self._ohm_out, 1)
        self.tabs.addTab(page, "&Ohm's law")

    def compute_ohms(self) -> None:
        try:
            rows = compute_ohms({k: le.text() for k, le in self._ohm.items()})
        except ValueError as exc:
            self._ohm_out.setPlainText(f"Could not solve: {exc}")
            return
        self._ohm_out.setPlainText(format_rows(rows))

    # --- time constant ----------------------------------------------------------

    def _build_tau(self) -> None:
        tab = GraphPanel(self, self._win, "Time-constant chart", "Time-constant data table",
                        ["Time constants", "Time (s)", "Percent"])
        self._tau_tab = tab
        self._tau_kind = QComboBox(tab)
        self._tau_kind.addItems(["RC", "RL"])
        self._tau_kind.setAccessibleName("Circuit type, RC or RL")
        tab.form.addRow("Circuit &type:", self._tau_kind)
        self._tau_dir = QComboBox(tab)
        self._tau_dir.addItems(["charge", "discharge"])
        self._tau_dir.setAccessibleName("Charging or discharging")
        tab.form.addRow("&Direction:", self._tau_dir)
        self._tau_r = tab.field("&R (Ω):", "1M", "Resistance in ohms")
        self._tau_part = tab.field("C (F) or &L (H):", "220u",
                                   "Capacitance in farads or inductance in henries")
        tab.plot.set_axes("Time (time constants, τ)", "% of final", x_range=(0.0, 5.0),
                          y_range=(0.0, 100.0), x_fmt=lambda v: f"{v:g}τ",
                          y_fmt=lambda v: f"{v:g}%")
        tab.compute_btn.clicked.connect(self.compute_tau)
        self._tau_kind.currentIndexChanged.connect(self.compute_tau)
        self._tau_dir.currentIndexChanged.connect(self.compute_tau)
        self.tabs.addTab(tab, "&Time constant")

    def compute_tau(self) -> None:
        tab = self._tau_tab
        try:
            res = compute_time_constant({
                "kind": self._tau_kind.currentText(), "r": self._tau_r.text(),
                "part": self._tau_part.text(), "direction": self._tau_dir.currentText()})
        except ValueError as exc:
            tab.show_error(f"Could not compute: {exc}")
            return
        charging = self._tau_dir.currentText() == "charge"
        marks = [(n, f"{n}τ") for n in (1, 2, 3, 4, 5)]
        p1 = 100.0 * (1 - math.exp(-1)) if charging else 100.0 * math.exp(-1)
        tab.plot.set_axes("Time (time constants, τ)", res["y_label"], x_range=(0.0, 5.0),
                          y_range=(0.0, 100.0))
        tab.plot.set_data(res["curve"], vlines=marks[:1],
                          points=[(1.0, p1, f"{p1:.1f}% at 1τ")])
        tab.show_result(res["rows"], res["description"], res["table"])

    # --- resonance ----------------------------------------------------------------

    def _build_resonance(self) -> None:
        tab = GraphPanel(self, self._win, "Resonance chart", "Resonance data table",
                        ["Frequency (Hz)", "Response (% of peak)"])
        self._res_tab = tab
        self._res_topo = QComboBox(tab)
        self._res_topo.addItems(["series", "parallel"])
        self._res_topo.setAccessibleName("Series or parallel circuit")
        tab.form.addRow("&Circuit:", self._res_topo)
        self._res_r = tab.field("&R (Ω):", "10", "Resistance in ohms")
        self._res_l = tab.field("&L (H):", "50u", "Inductance in henries")
        self._res_c = tab.field("C (&F):", "40p", "Capacitance in farads")
        tab.compute_btn.clicked.connect(self.compute_resonance)
        self._res_topo.currentIndexChanged.connect(self._res_topology_changed)
        self.tabs.addTab(tab, "&Resonance")

    def _res_topology_changed(self) -> None:
        # a sensible R for each topology (small series R, large parallel R)
        self._res_r.setText("10" if self._res_topo.currentText() == "series" else "10k")
        self.compute_resonance()

    def compute_resonance(self) -> None:
        tab = self._res_tab
        try:
            res = compute_resonance({
                "topology": self._res_topo.currentText(), "r": self._res_r.text(),
                "l": self._res_l.text(), "c": self._res_c.text()})
        except ValueError as exc:
            tab.show_error(f"Could not compute: {exc}")
            return
        info = res["info"]
        tab.plot.set_axes("Frequency", "% of peak", x_range=res["range"], y_range=(0.0, 100.0),
                          x_fmt=lambda v: fmt_eng(v, "Hz", 5), y_fmt=lambda v: f"{v:g}%")
        tab.plot.set_data(res["curve"], vlines=[(info["f0"], "f0")],
                          hlines=[(100.0 / math.sqrt(2), "−3 dB (70.7%)")],
                          points=[(info["f_low"], 100.0 / math.sqrt(2), ""),
                                  (info["f_high"], 100.0 / math.sqrt(2),
                                   f"BW {fmt_eng(info['bandwidth'], 'Hz')}")])
        tab.show_result(res["rows"], res["description"], res["table"])

    # --- impedance ------------------------------------------------------------------

    def _build_impedance(self) -> None:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        hint = QLabel("Leave L or C blank (or 0) to omit it.", page)
        lay.addWidget(hint)
        form = QFormLayout()
        self._imp_topo = QComboBox(page)
        self._imp_topo.addItems(["series", "parallel"])
        self._imp_topo.setAccessibleName("Series or parallel circuit")
        form.addRow("&Circuit:", self._imp_topo)
        self._imp = {}
        for key, label, default, name in (
                ("freq", "&Frequency (Hz):", "14M", "Frequency in hertz"),
                ("r", "&R (Ω):", "400", "Resistance in ohms"),
                ("l", "&L (H):", "", "Inductance in henries"),
                ("c", "C (&F):", "38p", "Capacitance in farads")):
            le = QLineEdit(default, page)
            le.setAccessibleName(name)
            le.returnPressed.connect(self.compute_impedance)
            form.addRow(label, le)
            self._imp[key] = le
        lay.addLayout(form)
        btn = QPushButton("&Compute", page)
        btn.clicked.connect(self.compute_impedance)
        lay.addWidget(btn)
        self._imp_out = QPlainTextEdit(page)
        self._imp_out.setReadOnly(True)
        self._imp_out.setAccessibleName("Impedance results")
        lay.addWidget(self._imp_out, 1)
        self.tabs.addTab(page, "&Impedance")

    def compute_impedance(self) -> None:
        raw = {k: le.text() for k, le in self._imp.items()}
        raw["topology"] = self._imp_topo.currentText()
        try:
            rows = compute_impedance(raw)
        except (ValueError, ZeroDivisionError) as exc:
            self._imp_out.setPlainText(f"Could not compute: {exc}")
            return
        self._imp_out.setPlainText(format_rows(rows))

    # --- shared -----------------------------------------------------------------------

    def rows_to_sheet(self, title: str, headers: list[str], rows: list[tuple]) -> str:
        """Write ``rows`` under ``headers`` into a new worksheet; returns its name."""
        return rows_to_new_sheet(self._win, title, headers, rows)
