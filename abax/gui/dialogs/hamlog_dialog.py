"""POTA / SOTA / contest activation log — enter contacts, catch dupes live.

A small keyboard-first logger. Type a callsign, pick band/mode (time defaults to
now, UTC), and *Log QSO*: the contact is added to an in-memory activation log,
scored against the selected ruleset (POTA/SOTA = 1 pt each, Field Day = CW/data
2 / phone 1), and checked for duplicates. Dupe rows are highlighted and a
running tally (valid QSOs / dupes / points / score) updates on every entry.
*Write to sheet* drops the whole log into a new worksheet so it becomes a live
spreadsheet (and can be exported to ADIF via the logbook tools).

All scoring is the pure-stdlib :mod:`abax.core.science.hamlog`; this file is just
the form and the sheet hand-off.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .._qtcompat import (
    QAbstractItemView,
    QBrush,
    QColor,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from ...core.science import hamlog

# Bands/modes offered in the pickers (editable — the combos are editable so an
# unlisted band/mode can still be typed).
_BANDS = ["160M", "80M", "60M", "40M", "30M", "20M", "17M", "15M", "12M",
          "10M", "6M", "2M", "1.25M", "70CM"]
_MODES = ["SSB", "CW", "FM", "AM", "FT8", "FT4", "RTTY", "PSK31", "DATA"]

_DUPE_BRUSH = QColor(255, 210, 210)   # light red for dupe rows
_HEADERS = ["#", "Call", "Band", "Mode", "Time", "Pts", "Status"]


def _bold(text: str) -> QLabel:
    lab = QLabel(text)
    f = lab.font()
    f.setBold(True)
    lab.setFont(f)
    return lab


class HamLogDialog(QDialog):
    """Run an activation log with live dupe detection and a running score."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Activation log (POTA / SOTA / contest)")
        self.resize(560, 480)
        self._log: list[dict] = []
        self._build()
        self._refresh_time()

    # --- construction ------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Ruleset:", self))
        self._ruleset = QComboBox(self)
        self._ruleset.addItems(hamlog.available_rulesets())
        self._ruleset.setCurrentText("pota")
        self._ruleset.currentIndexChanged.connect(self._rescore)
        top.addWidget(self._ruleset)
        top.addStretch(1)
        root.addLayout(top)

        root.addWidget(_bold("Log a contact"))
        entry = QHBoxLayout()
        self._call = QLineEdit(self)
        self._call.setPlaceholderText("Callsign")
        self._call.returnPressed.connect(self._log_qso)
        entry.addWidget(self._call, 2)
        self._band = QComboBox(self)
        self._band.setEditable(True)
        self._band.addItems(_BANDS)
        self._band.setCurrentText("20M")
        entry.addWidget(self._band, 1)
        self._mode = QComboBox(self)
        self._mode.setEditable(True)
        self._mode.addItems(_MODES)
        self._mode.setCurrentText("SSB")
        entry.addWidget(self._mode, 1)
        self._time = QLineEdit(self)
        self._time.setPlaceholderText("HHMM UTC")
        entry.addWidget(self._time, 1)
        root.addLayout(entry)

        btns = QHBoxLayout()
        log_btn = QPushButton("Log QSO", self)
        log_btn.clicked.connect(self._log_qso)
        btns.addWidget(log_btn)
        now_btn = QPushButton("Now", self)
        now_btn.clicked.connect(self._refresh_time)
        btns.addWidget(now_btn)
        undo_btn = QPushButton("Remove last", self)
        undo_btn.clicked.connect(self._remove_last)
        btns.addWidget(undo_btn)
        btns.addStretch(1)
        root.addLayout(btns)

        self._table = QTableWidget(0, len(_HEADERS), self)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        root.addWidget(self._table, 1)

        self._tally = QLabel(self)
        self._tally.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self._tally)

        foot = QHBoxLayout()
        foot.addStretch(1)
        write_btn = QPushButton("Write to sheet", self)
        write_btn.clicked.connect(self._write_sheet)
        foot.addWidget(write_btn)
        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        root.addLayout(foot)

        self._rescore()

    # --- helpers -----------------------------------------------------------

    def _refresh_time(self) -> None:
        self._time.setText(datetime.now(timezone.utc).strftime("%H%M"))

    def _current_rules(self):
        return hamlog.ruleset(self._ruleset.currentText())

    def _read_entry(self) -> dict | None:
        call = self._call.text().strip()
        if not hamlog.normalize_call(call):
            QMessageBox.warning(self, "Activation log", "Enter a callsign first.")
            return None
        return {
            "call": call,
            "band": self._band.currentText().strip(),
            "mode": self._mode.currentText().strip(),
            "time": self._time.text().strip(),
        }

    # --- log operations (testable without the widgets driving them) --------

    def add_qso(self, call: str, band: str, mode: str, time: str = "") -> bool:
        """Append a contact to the log; return True if it is a *dupe*.

        Pure model mutation used by :meth:`_log_qso` and by tests. Dupe status is
        judged against the contacts already in the log under the active ruleset."""
        rules = self._current_rules()
        qso = {"call": call, "band": band, "mode": mode, "time": time}
        dup = hamlog.is_dupe(
            qso, self._log,
            by_band=rules.dupe_by_band, by_mode=rules.dupe_by_mode)
        self._log.append(qso)
        return dup

    def _log_qso(self) -> None:
        entry = self._read_entry()
        if entry is None:
            return
        dup = self.add_qso(entry["call"], entry["band"], entry["mode"], entry["time"])
        self._rescore()
        if dup and hasattr(self._win, "_set_status"):
            self._win._set_status(
                f"DUPE: {hamlog.normalize_call(entry['call'])} already worked "
                f"on {entry['band']} {entry['mode']}")
        # Ready for the next contact.
        self._call.clear()
        self._call.setFocus()
        self._refresh_time()

    def _remove_last(self) -> None:
        if self._log:
            self._log.pop()
            self._rescore()

    # --- scoring / view ----------------------------------------------------

    def score(self):
        """Score the current log under the active ruleset (:class:`ScoreResult`)."""
        return hamlog.score_log(self._log, self._current_rules())

    def _rescore(self) -> None:
        result = self.score()
        self._table.setRowCount(len(result.rows))
        for r, row in enumerate(result.rows):
            src = self._log[row.index]
            cells = [
                str(r + 1), row.call, row.band, row.mode,
                str(src.get("time", "")), str(row.points),
                "DUPE" if row.is_dupe else "OK",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if row.is_dupe:
                    item.setBackground(QBrush(_DUPE_BRUSH))
                self._table.setItem(r, c, item)
        self._table.resizeColumnsToContents()
        mult = f"  x{result.multipliers} mult" if result.multipliers else ""
        self._tally.setText(
            f"Valid QSOs: {result.qso_count}    Dupes: {result.dupe_count}    "
            f"Points: {result.point_total}{mult}    Score: {result.score}")

    # --- sheet hand-off ----------------------------------------------------

    def log_rows(self) -> tuple[list[str], list[list]]:
        """Return ``(headers, rows)`` for the scored log (header + one row/QSO).

        Column layout mirrors the on-screen table and is friendly to the ADIF
        logbook tools (Call / Band / Mode columns line up)."""
        result = self.score()
        headers = ["Call", "Band", "Mode", "Time", "Points", "Dupe"]
        rows: list[list[str]] = []
        for row in result.rows:
            src = self._log[row.index]
            rows.append([
                row.call, row.band, row.mode, str(src.get("time", "")),
                str(row.points), "Y" if row.is_dupe else "",
            ])
        return headers, rows

    def _write_sheet(self) -> None:
        if not self._log:
            QMessageBox.information(self, "Activation log", "Nothing logged yet.")
            return
        headers, rows = self.log_rows()
        result = self.score()
        wb = self._win._doc.workbook
        name = self._win._unique_sheet_name("Log")
        sheet = wb.add_sheet(name)
        rules_name = self._ruleset.currentText()
        sheet.set_cell(0, 0, f"Activation log ({rules_name})")
        for j, head in enumerate(headers):
            sheet.set_cell(1, j, head)
        for i, row in enumerate(rows, start=2):
            for j, cell in enumerate(row):
                if cell not in ("", None):
                    sheet.set_cell(i, j, cell)
        summary = i + 2
        sheet.set_cell(summary, 0, "Valid QSOs")
        sheet.set_cell(summary, 1, str(result.qso_count))
        sheet.set_cell(summary + 1, 0, "Dupes")
        sheet.set_cell(summary + 1, 1, str(result.dupe_count))
        sheet.set_cell(summary + 2, 0, "Points")
        sheet.set_cell(summary + 2, 1, str(result.point_total))
        if result.multipliers:
            sheet.set_cell(summary + 3, 0, "Multipliers")
            sheet.set_cell(summary + 3, 1, str(result.multipliers))
        sheet.set_cell(summary + 4, 0, "Score")
        sheet.set_cell(summary + 4, 1, str(result.score))
        wb.active = len(wb.sheets) - 1
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        if hasattr(self._win, "_set_status"):
            self._win._set_status(
                f"Activation log -> sheet '{name}': {result.qso_count} QSOs, "
                f"score {result.score}")
