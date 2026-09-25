"""Shared chart panel for the radio / circuit dialogs.

:class:`GraphPanel` lays out a small input form with a *Compute* button, a
read-only results readout, an :class:`~._xyplot.XYPlot`, a written summary
(which is also the chart's accessible description), the same data as a table,
and a *Data → new sheet* button. Nothing on it is available only as a picture.
"""

from __future__ import annotations

from ._xyplot import XYPlot
from .._qtcompat import (
    QAbstractItemView,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def format_rows(rows: list[tuple[str, str]]) -> str:
    """``(label, value)`` rows as aligned plain text."""
    width = max((len(label) for label, _ in rows), default=0)
    return "\n".join(f"{label.ljust(width)}   {text}" for label, text in rows)


def rows_to_new_sheet(win, title: str, headers: list[str], rows: list[tuple]) -> str:
    """Write ``rows`` under ``headers`` into a new worksheet of ``win``'s
    workbook, make it active, and return its name."""
    wb = win._doc.workbook
    existing = {s.name for s in wb.sheets}
    base = title.replace(" chart", "")
    name, n = base, 2
    while name in existing:
        name, n = f"{base} {n}", n + 1
    sheet = wb.add_sheet(name)
    for c, h in enumerate(headers):
        sheet.set_cell(0, c, h)
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            # cells take raw text; repr keeps a float's full precision
            sheet.set_cell(r, c, val if isinstance(val, str) else repr(float(val)))
    wb.active = len(wb.sheets) - 1
    win._doc.mark_dirty()
    win.refresh_table()
    win._set_status(f"{base} data -> sheet '{name}'")
    return name


class GraphPanel(QWidget):
    """Shared layout: form + Compute, a results readout, the graph, the same
    data as a table, and *Data → new sheet*."""

    def __init__(self, parent, window, chart_name: str, table_name: str,
                 headers: list[str]) -> None:
        super().__init__(parent)
        self._win = window
        self._headers = headers
        outer = QHBoxLayout(self)
        side = QVBoxLayout()
        self.form = QFormLayout()
        side.addLayout(self.form)
        self.compute_btn = QPushButton("&Compute", self)
        side.addWidget(self.compute_btn)
        self.results = QPlainTextEdit(self)
        self.results.setReadOnly(True)
        self.results.setAccessibleName(f"{chart_name} results")
        side.addWidget(self.results, 1)
        outer.addLayout(side, 1)

        right = QVBoxLayout()
        self.plot = XYPlot(chart_name, self)
        right.addWidget(self.plot, 3)
        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                             | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.summary.setAccessibleName(f"{chart_name} summary")
        right.addWidget(self.summary)
        self.table = QTableWidget(0, len(headers), self)
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setAccessibleName(table_name)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        right.addWidget(self.table, 2)
        self.to_sheet = QPushButton("&Data → new sheet", self)
        self.to_sheet.setAccessibleDescription("Copy the graph's data table into a new worksheet")
        self.to_sheet.clicked.connect(self._to_sheet)
        right.addWidget(self.to_sheet)
        outer.addLayout(right, 2)
        self._rows: list[tuple] = []

    def field(self, label: str, default: str, accessible: str) -> QLineEdit:
        le = QLineEdit(default, self)
        le.setAccessibleName(accessible)
        le.returnPressed.connect(self.compute_btn.click)
        self.form.addRow(label, le)
        return le

    def show_result(self, rows, description: str, table_rows: list[tuple]) -> None:
        self.results.setPlainText(format_rows(rows))
        self.summary.setText(description)
        self.plot.set_description(description)
        self._rows = table_rows
        self.table.setRowCount(len(table_rows))
        for r, row in enumerate(table_rows):
            for c, val in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(val if isinstance(val, str)
                                                          else f"{val:.6g}"))

    def show_error(self, message: str) -> None:
        self.results.setPlainText(message)
        self.summary.setText(message)

    def _to_sheet(self) -> None:
        if self._rows:
            rows_to_new_sheet(self._win, self.plot.accessibleName(), self._headers, self._rows)
