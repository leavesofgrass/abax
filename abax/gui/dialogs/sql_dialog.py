"""SQL over sheets — run a query against the workbook's sheets and view results.

Each sheet becomes an in-memory SQLite table (first row = headers). Type your
query, Run it, and optionally drop the result into a new sheet. Backed by the
pure-stdlib :mod:`abax.core.sqlsheets`.
"""

from __future__ import annotations

from .._qtcompat import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from ...core import sqlsheets


class SqlDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("SQL over sheets")
        self.resize(680, 500)
        self._columns: list[str] = []
        self._rows: list[tuple] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        names = ", ".join(s.name for s in self._win._doc.workbook.sheets)
        root.addWidget(QLabel(f"Tables (one per sheet): {names}", self))
        self._sql = QPlainTextEdit(self)
        self._sql.setPlaceholderText("SELECT * FROM Sheet1 WHERE ...")
        self._sql.setMaximumHeight(120)
        root.addWidget(self._sql)

        bar = QHBoxLayout()
        run = QPushButton("Run  (F5)", self)
        run.clicked.connect(self.run_query)
        self._to_sheet = QPushButton("Results -> new sheet", self)
        self._to_sheet.clicked.connect(self._results_to_sheet)
        self._to_sheet.setEnabled(False)
        bar.addWidget(run)
        bar.addWidget(self._to_sheet)
        bar.addStretch(1)
        root.addLayout(bar)

        self._table = QTableWidget(0, 0, self)
        root.addWidget(self._table, 1)
        self._status = QLabel("", self)
        root.addWidget(self._status)

    def run_query(self) -> None:
        query = self._sql.toPlainText().strip()
        if not query:
            return
        sheets = {s.name: s for s in self._win._doc.workbook.sheets}
        try:
            self._columns, self._rows = sqlsheets.run_sql(sheets, query)
        except sqlsheets.SqlError as exc:
            QMessageBox.warning(self, "SQL", str(exc))
            return
        self._table.setColumnCount(len(self._columns))
        self._table.setHorizontalHeaderLabels(self._columns)
        self._table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            for c, val in enumerate(row):
                self._table.setItem(r, c, QTableWidgetItem("" if val is None else str(val)))
        self._to_sheet.setEnabled(bool(self._columns))
        self._status.setText(f"{len(self._rows)} row(s)")

    def _results_to_sheet(self) -> None:
        if not self._columns:
            return
        wb = self._win._doc.workbook
        base = "Query"
        existing = {s.name for s in wb.sheets}
        name, n = base, 2
        while name in existing:
            name, n = f"{base} {n}", n + 1
        sheet = wb.add_sheet(name)
        for c, col in enumerate(self._columns):
            sheet.set_cell(0, c, str(col))
        for r, row in enumerate(self._rows, start=1):
            for c, val in enumerate(row):
                sheet.set_cell(r, c, "" if val is None else str(val))
        wb.active = len(wb.sheets) - 1
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(f"query results -> sheet '{name}'")
        self.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        from .._qtcompat import Qt

        if event.key() == Qt.Key.Key_F5:
            self.run_query()
            return
        super().keyPressEvent(event)
