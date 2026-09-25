"""RF exposure estimate — MPE compliance distances and the FCC exemption check.

Enter the station (frequency, power, feed-line loss, antenna gain, duty cycle,
transmit time in the averaging period, ground reflection) and the distance to
the nearest person. The dialog reports average power, EIRP/ERP, the § 1.1310
limits for both tiers, the distance at which each limit is met, how the
chosen distance compares, and the § 1.1307(b)(3)(i)(C) exemption threshold.

The graph plots far-field power density against distance on log-log axes with
both limits and both compliance distances marked; its written summary (also
its accessible description), the data table and *Data → new sheet* carry the
same information in words and numbers.

Backed by :mod:`abax.core.science.rf_exposure`. An estimate, not a substitute
for a station evaluation — the dialog says so where the numbers are.
"""

from __future__ import annotations

import math

from ._graphpanel import GraphPanel
from .._qtcompat import (
    QComboBox,
    QDialog,
    QLabel,
    QVBoxLayout,
)
from ...core.science import rf_exposure as X

_FT = 0.3048

DISCLAIMER = (
    "Estimate only, using the far-field power-density formula. It is not a "
    "substitute for your station's RF exposure evaluation under 47 CFR § 97.13(c) "
    "and § 1.1307(b), and it is not a reliable measure closer to the antenna than "
    "λ/2π. Duty cycle is yours to enter: abax does not preset per-mode values."
)

REFLECTION_CHOICES = (
    ("None — free space (×1)", 1.0),
    ("Full in-phase reflection, worst case (×4)", X.FULL_REFLECTION),
    ("Custom power-density factor", None),
)

TIER_LABELS = {
    "controlled": "Controlled (you and trained household members)",
    "uncontrolled": "Uncontrolled (neighbors and the public)",
}


def _m_ft(m: float) -> str:
    return f"{m:.2f} m ({m / _FT:.1f} ft)"


def compute_exposure(raw: dict) -> dict:
    """Parse the dialog's text fields and evaluate the station (UI-free).

    ``raw`` keys: freq_mhz, power_w, loss_db, gain_dbi, duty_pct, tx_pct,
    reflection (a number) and distance_m. Returns the result rows, the curve,
    the table, the description and the evaluation dict.
    """
    f = float(raw["freq_mhz"])
    ev = X.evaluate_station(
        f_mhz=f, power_w=float(raw["power_w"]), feedline_loss_db=float(raw["loss_db"]),
        gain_dbi=float(raw["gain_dbi"]), duty_cycle=float(raw["duty_pct"]) / 100.0,
        tx_fraction=float(raw["tx_pct"]) / 100.0, reflection=float(raw["reflection"]),
        distance_m=float(raw["distance_m"]))
    d = ev["distance_m"]
    rows = [
        ("Average power at antenna", f"{ev['avg_power_w']:.4g} W"),
        ("EIRP / ERP", f"{ev['eirp_w']:.4g} W / {ev['erp_w']:.4g} W"),
        ("Ground-reflection factor", f"×{ev['reflection']:g}"),
    ]
    verdicts = []
    for t in X.TIERS:
        lim = ev["limits"][t]
        pct = ev["percent"][t]
        state = "below the limit" if pct <= 100.0 else "ABOVE the limit"
        rows += [
            (f"{TIER_LABELS[t]}", ""),
            ("  MPE limit", f"{lim['power_density']:.4g} mW/cm² "
                            f"(averaged over {lim['averaging_minutes']:g} min)"),
            ("  Limit met beyond", _m_ft(ev["compliance_m"][t])),
            (f"  At {_m_ft(d)}", f"{ev['density']:.4g} mW/cm² = {pct:.1f}% of limit, {state}"),
        ]
        verdicts.append(f"{t} limit {lim['power_density']:.3g} mW/cm², met beyond "
                        f"{ev['compliance_m'][t]:.2f} m, {pct:.0f}% of it at your distance")
    thr = ev["exempt_threshold_erp_w"]
    if thr is None:
        exempt_text = (f"Not applicable: the distance is under λ/2π "
                       f"({_m_ft(ev['min_exempt_distance_m'])}) or outside the table")
    else:
        exempt_text = (f"threshold {thr:.4g} W ERP at {d:g} m; your ERP {ev['erp_w']:.4g} W is "
                       + ("at or below it (exempt from routine evaluation)" if ev["exempt"]
                          else "above it (evaluation required)"))
    rows.append(("§ 1.1307 exemption", exempt_text))

    far = max(ev["compliance_m"].values())
    lo = max(0.1, min(d, far) / 10.0)
    hi = max(d, far) * 10.0
    curve = []
    for i in range(0, 121):
        r = lo * (hi / lo) ** (i / 120.0)
        curve.append((r, X.power_density(ev["eirp_w"], r, ev["reflection"])))
    table = []
    for r in sorted({*(lo * (hi / lo) ** (i / 8.0) for i in range(0, 9)),
                     d, *ev["compliance_m"].values()}):
        s = X.power_density(ev["eirp_w"], r, ev["reflection"])
        table.append((r, r / _FT, s, 100 * s / ev["limits"]["uncontrolled"]["power_density"],
                      100 * s / ev["limits"]["controlled"]["power_density"]))
    desc = (f"Log-log line chart of estimated power density in mW/cm² against distance "
            f"in metres from {lo:.2g} to {hi:.3g} m, at {f:g} MHz with EIRP "
            f"{ev['eirp_w']:.3g} W. Density falls with the square of distance. "
            + "; ".join(verdicts) + f". Your distance, {d:g} m, is marked. "
            "Estimate only; not a substitute for a station evaluation.")
    return {"eval": ev, "rows": rows, "curve": curve, "table": table,
            "description": desc, "range": (lo, hi)}


class ExposureDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("RF exposure estimate")
        self.setAccessibleName("RF exposure estimate")
        self.resize(960, 620)
        outer = QVBoxLayout(self)
        note = QLabel(DISCLAIMER, self)
        note.setWordWrap(True)
        note.setAccessibleName("Important: about these estimates")
        outer.addWidget(note)
        self.panel = GraphPanel(self, window, "RF exposure chart", "RF exposure data table",
                                ["Distance (m)", "Distance (ft)", "Power density (mW/cm²)",
                                 "% of uncontrolled limit", "% of controlled limit"])
        outer.addWidget(self.panel, 1)
        p = self.panel
        self.f = p.field("&Frequency (MHz):", "14.2", "Frequency in megahertz")
        self.power = p.field("Transmitter &power (W PEP):", "100",
                             "Transmitter peak envelope power in watts")
        self.loss = p.field("Feed-line &loss (dB):", "1", "Feed-line loss in decibels")
        self.gain = p.field("Antenna &gain (dBi):", "2.15",
                            "Antenna gain in decibels relative to isotropic")
        self.duty = p.field("Mode &duty cycle (%):", "100",
                            "Mode duty cycle in percent; 100 is the worst case")
        self.tx = p.field("&Transmit time in averaging period (%):", "100",
                          "Percent of the averaging period spent transmitting; 100 is "
                          "the worst case")
        self.refl = QComboBox(self.panel)
        self.refl.addItems([label for label, _ in REFLECTION_CHOICES])
        self.refl.setAccessibleName("Ground reflection")
        p.form.addRow("Ground &reflection:", self.refl)
        self.custom = p.field("Custom &factor:", "1", "Custom power-density reflection factor")
        self.custom.setEnabled(False)
        self.dist = p.field("Distance to nearest &person (m):", "10",
                            "Distance in metres from the antenna to the nearest person")
        self.refl.currentIndexChanged.connect(self._reflection_changed)
        p.compute_btn.clicked.connect(self.compute)
        self.compute()

    def _reflection_changed(self) -> None:
        self.custom.setEnabled(REFLECTION_CHOICES[self.refl.currentIndex()][1] is None)
        self.compute()

    def reflection(self) -> float:
        preset = REFLECTION_CHOICES[self.refl.currentIndex()][1]
        return preset if preset is not None else float(self.custom.text())

    def compute(self) -> None:
        p = self.panel
        try:
            res = compute_exposure({
                "freq_mhz": self.f.text(), "power_w": self.power.text(),
                "loss_db": self.loss.text(), "gain_dbi": self.gain.text(),
                "duty_pct": self.duty.text(), "tx_pct": self.tx.text(),
                "reflection": self.reflection(), "distance_m": self.dist.text()})
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            p.show_error(f"Could not compute: {exc}")
            return
        ev = res["eval"]
        lims = ev["limits"]
        p.plot.set_axes("Distance (m)", "mW/cm²", log_x=True, log_y=True,
                        x_range=res["range"],
                        x_fmt=lambda v: f"{v:g}", y_fmt=lambda v: f"{v:g}")
        p.plot.set_data(
            res["curve"],
            vlines=[(ev["distance_m"], "your distance")],
            hlines=[(lims["uncontrolled"]["power_density"], "uncontrolled limit"),
                    (lims["controlled"]["power_density"], "controlled limit")],
            points=[(ev["compliance_m"][t], lims[t]["power_density"],
                     f"{ev['compliance_m'][t]:.2f} m") for t in X.TIERS
                    if math.isfinite(ev["compliance_m"][t]) and ev["compliance_m"][t] > 0])
        p.show_result(res["rows"], res["description"], res["table"])
