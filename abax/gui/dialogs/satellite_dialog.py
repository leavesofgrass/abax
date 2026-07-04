"""Satellite pass predictor — TLE in, predicted passes out, optionally to a sheet.

Paste a satellite's TLE (name line optional), set the observer (latitude,
longitude, altitude) and the prediction window (start time in UTC, length in
hours, minimum elevation), and Predict. Passes appear in a table — rise,
culmination and set times with their azimuths and the maximum elevation — and
"Passes -> new sheet" drops them into a fresh sheet.

Orbit propagation is done by the optional ``sgp4`` package via
:mod:`abax.engine.satellite`; when it is not installed the dialog stays usable
but Predict reports the "install sgp4" message instead of computing.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .._qtcompat import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from ...engine import satellite

# A recent-ish ISS element set, used to prefill the input so the dialog is
# immediately runnable (only meaningful when propagated near its own epoch).
_SAMPLE_TLE = (
    "ISS (ZARYA)\n"
    "1 25544U 98067A   24173.54791435  .00016717  00000-0  30074-3 0  9993\n"
    "2 25544  51.6402 210.0827 0004572  61.9772 298.1637 15.50186970    07"
)

_COLUMNS = [
    "Satellite",
    "Rise (UTC)",
    "Rise Az",
    "Culmination (UTC)",
    "Max El",
    "Max Az",
    "Set (UTC)",
    "Set Az",
    "Duration",
]


def _fmt_time(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_deg(val: float) -> str:
    return f"{val:.1f}°"


def _fmt_duration(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 60}m {total % 60:02d}s"


class SatelliteDialog(QDialog):
    """Predict satellite passes over an observer and write them to a sheet."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Satellite pass predictor")
        self.resize(760, 560)
        self._passes: list[dict] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)

        if not satellite.available():
            warn = QLabel(
                "The 'sgp4' package is not installed — prediction is unavailable. "
                "Install it with:  pip install sgp4",
                self,
            )
            warn.setWordWrap(True)
            root.addWidget(warn)

        root.addWidget(QLabel("TLE (name line optional):", self))
        self._tle = QPlainTextEdit(self)
        self._tle.setPlainText(_SAMPLE_TLE)
        self._tle.setMaximumHeight(90)
        root.addWidget(self._tle)

        # --- observer + window controls, side by side ---
        controls = QHBoxLayout()

        obs_box = QGroupBox("Observer", self)
        obs_form = QFormLayout(obs_box)
        self._lat = self._spin(-90.0, 90.0, 4, 40.7128, " °")
        self._lon = self._spin(-180.0, 180.0, 4, -74.0060, " °")
        self._alt = self._spin(-500.0, 100000.0, 1, 10.0, " m")
        obs_form.addRow("Latitude", self._lat)
        obs_form.addRow("Longitude", self._lon)
        obs_form.addRow("Altitude", self._alt)
        controls.addWidget(obs_box)

        win_box = QGroupBox("Window", self)
        win_form = QFormLayout(win_box)
        self._start = QLineEdit(self)
        self._start.setText(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        self._start.setToolTip("Start time in UTC (YYYY-MM-DD HH:MM:SS)")
        self._hours = self._spin(0.1, 336.0, 1, 24.0, " h")
        self._min_el = self._spin(0.0, 89.0, 1, 10.0, " °")
        win_form.addRow("Start (UTC)", self._start)
        win_form.addRow("Duration", self._hours)
        win_form.addRow("Min elevation", self._min_el)
        controls.addWidget(win_box)

        root.addLayout(controls)

        # --- action bar ---
        bar = QHBoxLayout()
        predict = QPushButton("Predict  (F5)", self)
        predict.clicked.connect(self.predict)
        self._to_sheet = QPushButton("Passes -> new sheet", self)
        self._to_sheet.clicked.connect(self._passes_to_sheet)
        self._to_sheet.setEnabled(False)
        bar.addWidget(predict)
        bar.addWidget(self._to_sheet)
        bar.addStretch(1)
        root.addLayout(bar)

        self._table = QTableWidget(0, len(_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        root.addWidget(self._table, 1)

        self._status = QLabel("", self)
        root.addWidget(self._status)

    def _spin(
        self, lo: float, hi: float, decimals: int, value: float, suffix: str
    ) -> QDoubleSpinBox:
        sb = QDoubleSpinBox(self)
        sb.setRange(lo, hi)
        sb.setDecimals(decimals)
        sb.setValue(value)
        if suffix:
            sb.setSuffix(suffix)
        return sb

    # ------------------------------------------------------------------ #
    def _parse_start(self) -> datetime | None:
        text = self._start.text().strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def predict(self) -> None:
        start = self._parse_start()
        if start is None:
            QMessageBox.warning(
                self,
                "Satellite",
                "Could not parse the start time. Use UTC 'YYYY-MM-DD HH:MM:SS'.",
            )
            return
        observer = (self._lat.value(), self._lon.value(), self._alt.value())
        try:
            self._passes = satellite.predict_passes(
                self._tle.toPlainText(),
                observer,
                start,
                self._hours.value(),
                min_elevation_deg=self._min_el.value(),
            )
        except satellite.Sgp4Unavailable as exc:
            QMessageBox.warning(self, "Satellite", str(exc))
            return
        except ValueError as exc:
            QMessageBox.warning(self, "Satellite", str(exc))
            return

        self._populate_table()
        self._to_sheet.setEnabled(bool(self._passes))
        self._status.setText(f"{len(self._passes)} pass(es) predicted")

    def _populate_table(self) -> None:
        self._table.setRowCount(len(self._passes))
        for r, p in enumerate(self._passes):
            cells = [
                p["satellite"],
                _fmt_time(p["rise"]),
                _fmt_deg(p["rise_azimuth"]),
                _fmt_time(p["culmination"]),
                _fmt_deg(p["max_elevation"]),
                _fmt_deg(p["max_azimuth"]),
                _fmt_time(p["set"]),
                _fmt_deg(p["set_azimuth"]),
                _fmt_duration(p["duration_s"]),
            ]
            for c, val in enumerate(cells):
                self._table.setItem(r, c, QTableWidgetItem(val))

    def _passes_to_sheet(self) -> None:
        if not self._passes:
            return
        wb = self._win._doc.workbook
        base = "Passes"
        existing = {s.name for s in wb.sheets}
        name, n = base, 2
        while name in existing:
            name, n = f"{base} {n}", n + 1
        sheet = wb.add_sheet(name)
        for c, col in enumerate(_COLUMNS):
            sheet.set_cell(0, c, col)
        for r, p in enumerate(self._passes, start=1):
            row = [
                p["satellite"],
                _fmt_time(p["rise"]),
                round(p["rise_azimuth"], 1),
                _fmt_time(p["culmination"]),
                round(p["max_elevation"], 1),
                round(p["max_azimuth"], 1),
                _fmt_time(p["set"]),
                round(p["set_azimuth"], 1),
                round(p["duration_s"], 1),
            ]
            for c, val in enumerate(row):
                sheet.set_cell(r, c, str(val))
        wb.active = len(wb.sheets) - 1
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(f"satellite passes -> sheet '{name}'")
        self.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        from .._qtcompat import Qt

        if event.key() == Qt.Key.Key_F5:
            self.predict()
            return
        super().keyPressEvent(event)
