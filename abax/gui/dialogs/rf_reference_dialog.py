"""RF reference panel — the US amateur band plan and the standard CTCSS tones.

A read-only, filterable view over the pure-stdlib reference data in
:mod:`abax.core.science.rf_bands`. Type in the filter box to narrow both tables
(by band name / frequency text); "Bands -> new sheet" drops the band plan into
the workbook for use in formulas.
"""

from __future__ import annotations

from .._qtcompat import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from ...core.science import rf_bands

_C = 299_792_458.0

_BAND_HEADERS = ("Band", "Low (MHz)", "High (MHz)", "Width (MHz)", "λ mid (m)")
_TONE_HEADERS = ("#", "Tone (Hz)")


def _band_rows() -> list[tuple[str, str, str, str, str]]:
    rows = []
    for name, lo, hi in rf_bands.US_AMATEUR_BANDS:
        mid = (lo + hi) / 2.0
        rows.append((name, f"{lo / 1e6:g}", f"{hi / 1e6:g}",
                     f"{(hi - lo) / 1e6:g}", f"{_C / mid:.3f}"))
    return rows


def _tone_rows() -> list[tuple[str, str]]:
    return [(str(i), f"{t:g}") for i, t in enumerate(rf_bands.CTCSS_TONES, start=1)]


class RfReferenceDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("RF reference — bands & CTCSS")
        self.resize(560, 620)
        self._bands = _band_rows()
        self._tones = _tone_rows()
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)

        self._filter = QLineEdit(self)
        self._filter.setPlaceholderText("Filter (band name, frequency, tone)…")
        self._filter.textChanged.connect(self._apply_filter)
        root.addWidget(self._filter)

        root.addWidget(QLabel("US amateur bands (FCC Part 97, ITU Region 2)", self))
        self._band_table = self._make_table(_BAND_HEADERS, self._bands)
        root.addWidget(self._band_table, 3)

        root.addWidget(QLabel("CTCSS (PL) tones — EIA standard", self))
        self._tone_table = self._make_table(_TONE_HEADERS, self._tones)
        root.addWidget(self._tone_table, 2)

        bar = QHBoxLayout()
        to_sheet = QPushButton("Bands -> new sheet", self)
        to_sheet.clicked.connect(self._bands_to_sheet)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        bar.addWidget(to_sheet)
        bar.addStretch(1)
        bar.addWidget(close)
        root.addLayout(bar)

    def _make_table(self, headers, rows) -> QTableWidget:
        table = QTableWidget(len(rows), len(headers), self)
        table.setHorizontalHeaderLabels(list(headers))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(val))
        table.resizeColumnsToContents()
        return table

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for table, rows in ((self._band_table, self._bands),
                            (self._tone_table, self._tones)):
            for r, row in enumerate(rows):
                hit = not needle or any(needle in str(v).lower() for v in row)
                table.setRowHidden(r, not hit)

    def _bands_to_sheet(self) -> None:
        wb = self._win._doc.workbook
        existing = {s.name for s in wb.sheets}
        name, n = "Bands", 2
        while name in existing:
            name, n = f"Bands {n}", n + 1
        sheet = wb.add_sheet(name)
        for c, h in enumerate(_BAND_HEADERS):
            sheet.set_cell(0, c, h)
        for r, row in enumerate(self._bands, start=1):
            for c, val in enumerate(row):
                sheet.set_cell(r, c, val)
        wb.active = len(wb.sheets) - 1
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(f"band plan -> sheet '{name}'")
        self.accept()
