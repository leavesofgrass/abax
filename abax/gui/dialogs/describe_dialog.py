"""Descriptive Statistics tool — summarise a range in one click.

Reads a numeric range (defaulting to the current selection), drops blanks and
non-numeric cells, and computes the full spread of descriptive measures via the
pure-stdlib :func:`abax.core.science.descriptive.describe` (count, sum, mean,
median, mode, min, Q1, Q3, max, range, sample + population variance/stdev,
skewness, kurtosis). Results land in a small read-only table; "Write summary to
new sheet" drops a two-column ``statistic / value`` table into a fresh sheet.
"""

from __future__ import annotations

from .._qtcompat import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from ...core.reference import parse_range, to_a1
from ...core.science import descriptive

# Human-readable labels for the summary rows, in :data:`descriptive.FIELDS` order.
_LABELS = {
    "count": "Count",
    "sum": "Sum",
    "mean": "Mean",
    "median": "Median",
    "mode": "Mode",
    "min": "Minimum",
    "Q1": "Q1 (25%)",
    "Q3": "Q3 (75%)",
    "max": "Maximum",
    "range": "Range",
    "variance": "Variance (sample)",
    "stdev": "Std dev (sample)",
    "variance_pop": "Variance (pop.)",
    "stdev_pop": "Std dev (pop.)",
    "skewness": "Skewness",
    "kurtosis": "Kurtosis",
}


def _fmt(val) -> str:
    if val is None:
        return "—"
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return f"{val:.6g}"
    return str(val)


class DescribeDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self._summary: dict | None = None
        self.setWindowTitle("Descriptive Statistics")
        self.resize(360, 480)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        r1, c1, r2, c2 = self._win._selected_bounds()
        self._in = QLineEdit(f"{to_a1(r1, c1)}:{to_a1(r2, c2)}", self)
        row.addWidget(QLabel("Data (range):", self))
        row.addWidget(self._in, 1)
        compute = QPushButton("Compute", self)
        compute.clicked.connect(self._compute)
        row.addWidget(compute)
        layout.addLayout(row)

        self._table = QTableWidget(len(descriptive.FIELDS), 2, self)
        self._table.setHorizontalHeaderLabels(["Statistic", "Value"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        for i, key in enumerate(descriptive.FIELDS):
            self._table.setItem(i, 0, QTableWidgetItem(_LABELS[key]))
            self._table.setItem(i, 1, QTableWidgetItem(""))
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table, 1)

        btns = QHBoxLayout()
        self._to_sheet = QPushButton("Write summary to new sheet", self)
        self._to_sheet.setEnabled(False)
        self._to_sheet.clicked.connect(self._write_sheet)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        btns.addWidget(self._to_sheet)
        btns.addStretch(1)
        btns.addWidget(close)
        layout.addLayout(btns)

        # Compute immediately for the initial selection, if any.
        self._compute()

    def _read_values(self, rng: str) -> list:
        r1, c1, r2, c2 = parse_range(rng)
        sheet = self._win._doc.workbook.sheet
        return [
            sheet.get_value(r, c)
            for r in range(r1, r2 + 1)
            for c in range(c1, c2 + 1)
        ]

    def _compute(self) -> None:
        try:
            values = self._read_values(self._in.text())
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, "Descriptive Statistics", f"Bad range: {exc}")
            return
        summary = descriptive.describe(values)
        self._summary = summary
        for i, key in enumerate(descriptive.FIELDS):
            self._table.item(i, 1).setText(_fmt(summary[key]))
        self._to_sheet.setEnabled(summary["count"] > 0)
        if summary["count"] == 0:
            self._win._set_status("Descriptive Statistics: no numeric data in range")
        else:
            self._win._set_status(
                f"Descriptive Statistics: n={summary['count']}, "
                f"mean={_fmt(summary['mean'])}")

    def _write_sheet(self) -> None:
        if not self._summary or self._summary["count"] == 0:
            return
        wb = self._win._doc.workbook
        name = self._win._unique_sheet_name("Describe")
        sheet = wb.add_sheet(name)
        sheet.set_cell(0, 0, "Statistic")
        sheet.set_cell(0, 1, "Value")
        for i, key in enumerate(descriptive.FIELDS, start=1):
            sheet.set_cell(i, 0, _LABELS[key])
            val = self._summary[key]
            sheet.set_cell(i, 1, "" if val is None else _fmt(val))
        wb.active = len(wb.sheets) - 1
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(f"Descriptive Statistics -> sheet '{name}'")
        self.accept()
