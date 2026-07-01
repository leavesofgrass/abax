"""RF toolkit — link budget, coax line, antenna dimensions, and L-network matching.

A mode picker swaps the input form; results (with both metric and imperial where
it helps) are computed via :mod:`abax.core.science.rf` and shown read-only.
Frequencies are entered in MHz / distances in km for convenience; the rf module
itself stays in SI base units.
"""

from __future__ import annotations

from .._qtcompat import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_FT = 0.3048  # metres per foot


def _fmt_component(c: dict) -> str:
    if c["type"] == "L":
        h = c["henrys"]
        return f"L = {h * 1e9:.1f} nH" if h < 1e-6 else f"L = {h * 1e6:.3f} µH"
    if c["type"] == "C":
        f = c["farads"]
        return f"C = {f * 1e12:.1f} pF" if f < 1e-9 else f"C = {f * 1e9:.3f} nF"
    return "(through)"


def _link_budget(v: dict) -> list[tuple[str, str]]:
    from ...core.science import rf

    d_m, f_hz = v["dist"] * 1000.0, v["freq"] * 1e6
    fspl = rf.fspl_db(d_m, f_hz)
    rx = rf.friis_rx_dbm(v["ptx"], v["gtx"], v["grx"], d_m, f_hz)
    margin = rx - v["sens"]
    return [
        ("Free-space path loss", f"{fspl:.2f} dB"),
        ("Received power", f"{rx:.2f} dBm"),
        ("Link margin", f"{margin:+.2f} dB  ({'OK' if margin >= 0 else 'SHORT'})"),
    ]


def _coax(v: dict) -> list[tuple[str, str]]:
    from ...core.science import rf

    z0 = rf.z0_coax(v["od"], v["idd"], v["eps"])   # ratio D/d — unit-independent
    vf = rf.velocity_factor(v["eps"])
    return [
        ("Characteristic impedance Z0", f"{z0:.2f} Ω"),
        ("Velocity factor", f"{vf:.4f}  ({vf * 100:.1f} %)"),
    ]


def _antenna(v: dict) -> list[tuple[str, str]]:
    from ...core.science import rf

    f_hz, k = v["freq"] * 1e6, v["k"]
    dip, mon, lam = rf.dipole_length(f_hz, k), rf.monopole_length(f_hz, k), rf.wavelength(f_hz)
    return [
        ("½-wave dipole", f"{dip:.3f} m   ({dip / _FT:.2f} ft)"),
        ("¼-wave monopole", f"{mon:.3f} m   ({mon / _FT:.2f} ft)"),
        ("Full wavelength λ", f"{lam:.3f} m   ({lam / _FT:.2f} ft)"),
    ]


def _matching(v: dict) -> list[tuple[str, str]]:
    from ...core.science import rf

    sols = rf.l_match(complex(v["rs"]), complex(v["rl"]), v["freq"] * 1e6)
    rows = [("Loaded Q", f"{sols[0]['q']:.3f}")]
    for i, s in enumerate(sols, 1):
        rows.append((f"Solution {i} — series", _fmt_component(s["series"])))
        rows.append((f"Solution {i} — shunt", _fmt_component(s["shunt"])))
    return rows


# (title, [(key, label, default)], compute)
_MODES = [
    ("Link budget",
     [("ptx", "TX power (dBm)", "30"), ("gtx", "TX gain (dBi)", "0"),
      ("grx", "RX gain (dBi)", "0"), ("dist", "Distance (km)", "10"),
      ("freq", "Frequency (MHz)", "146"), ("sens", "RX sensitivity (dBm)", "-110")],
     _link_budget),
    ("Coax line",
     [("od", "Outer dia (shield ID)", "7.25"), ("idd", "Inner dia (centre)", "2.26"),
      ("eps", "Dielectric εr", "2.25")],
     _coax),
    ("Antenna dimensions",
     [("freq", "Frequency (MHz)", "14.2"), ("k", "Velocity / end factor", "0.95")],
     _antenna),
    ("Matching (L-network)",
     [("rs", "Source R (Ω)", "50"), ("rl", "Load R (Ω)", "200"),
      ("freq", "Frequency (MHz)", "7.0")],
     _matching),
]


class RFDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("RF toolkit")
        self.resize(440, 380)
        self._fields: dict = {}
        self._build()
        self._rebuild_inputs()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        self._mode = QComboBox(self)
        self._mode.addItems([m[0] for m in _MODES])
        self._mode.currentIndexChanged.connect(self._rebuild_inputs)
        outer.addWidget(self._mode)
        self._form_host = QWidget(self)
        self._form = QFormLayout(self._form_host)
        outer.addWidget(self._form_host)
        btn = QPushButton("Compute", self)
        btn.clicked.connect(self._compute)
        outer.addWidget(btn)
        self._results = QPlainTextEdit(self)
        self._results.setReadOnly(True)
        outer.addWidget(self._results, 1)

    def _spec(self):
        return _MODES[self._mode.currentIndex()]

    def _rebuild_inputs(self) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        self._fields = {}
        for key, label, default in self._spec()[1]:
            le = QLineEdit(default, self)
            self._form.addRow(label + ":", le)
            self._fields[key] = le
        self._results.clear()

    def compute_rows(self) -> "list[tuple[str, str]]":
        """Run the active mode and return its result rows (testable; no UI)."""
        vals = {k: float(le.text()) for k, le in self._fields.items()}
        return self._spec()[2](vals)

    def _compute(self) -> None:
        try:
            rows = self.compute_rows()
        except ValueError:
            QMessageBox.warning(self, "RF toolkit", "All inputs must be numbers.")
            return
        except (ZeroDivisionError, OverflowError) as exc:
            QMessageBox.warning(self, "RF toolkit", f"Could not compute: {exc}")
            return
        width = max((len(label) for label, _ in rows), default=0)
        self._results.setPlainText(
            "\n".join(f"{label.ljust(width)}   {text}" for label, text in rows))
