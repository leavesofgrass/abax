"""Pivot / group-by tool — summarise a table with :mod:`abax.core.pivot`.

Reads the selected range (first row = column names), then either groups by a
column and aggregates a value column, builds a pivot table (index × columns), or
cross-tabulates two columns. The result block is written back into the sheet.
"""

from __future__ import annotations

from .._qtcompat import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from ...core import pivot as P
from ...core.reference import parse_a1, parse_range, to_a1

_MODES = ["Group by", "Pivot table", "Cross-tab"]


class PivotDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Pivot / group-by")
        self.resize(420, 300)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        r1, c1, r2, c2 = self._win._selected_bounds()
        self._range = QLineEdit(f"{to_a1(r1, c1)}:{to_a1(r2, c2)}", self)
        self._range.editingFinished.connect(self._reload_columns)
        self._mode = QComboBox(self)
        self._mode.addItems(_MODES)
        self._mode.currentIndexChanged.connect(self._update_visibility)
        self._index = QComboBox(self)
        self._column = QComboBox(self)
        self._value = QComboBox(self)
        self._agg = QComboBox(self)
        for key, label in P.AGGREGATIONS.items():
            self._agg.addItem(label, key)
        # Pivot-table extras (margins + percent-of-total). Multi-value fields
        # are supported by core.pivot.pivot_table (value_cols=/aggs=); to expose
        # them here, swap self._value for a multi-select list and pass the two
        # parallel lists through in _apply — the wiring below already routes a
        # single field, so that is the only change needed.
        self._totals = QCheckBox("Show grand totals (margins)", self)
        self._pct = QComboBox(self)
        for key, label in (
            (None, "Off"), ("grand", "% of grand total"),
            ("row", "% of row"), ("col", "% of column"),
        ):
            self._pct.addItem(label, key)
        self._out = QLineEdit(to_a1(r1, max(0, c2 + 2)), self)
        form.addRow("Data (range):", self._range)
        form.addRow("Mode:", self._mode)
        self._index_row = ("Group / index col:", self._index)
        self._column_row = ("Columns (across):", self._column)
        self._value_row = ("Value col:", self._value)
        self._agg_row = ("Aggregate:", self._agg)
        for label, widget in (self._index_row, self._column_row,
                              self._value_row, self._agg_row):
            form.addRow(label, widget)
        self._totals_row = ("Totals:", self._totals)
        self._pct_row = ("Display as:", self._pct)
        form.addRow(*self._totals_row)
        form.addRow(*self._pct_row)
        form.addRow("Output top-left:", self._out)
        layout.addLayout(form)
        btn = QPushButton("Build", self)
        btn.clicked.connect(self._apply)
        layout.addWidget(btn)
        self._reload_columns()
        self._update_visibility()

    def _rows(self):
        r1, c1, r2, c2 = parse_range(self._range.text())
        sheet = self._win._doc.workbook.sheet
        return [["" if sheet.get_value(r, c) is None else str(sheet.get_value(r, c))
                 for c in range(c1, c2 + 1)]
                for r in range(r1, r2 + 1)]

    def _reload_columns(self) -> None:
        try:
            header = self._rows()[0]
        except Exception:
            header = []
        for combo in (self._index, self._column, self._value):
            current = combo.currentText()
            combo.clear()
            combo.addItems([str(h) for h in header])
            if current:
                i = combo.findText(current)
                if i >= 0:
                    combo.setCurrentIndex(i)

    def _update_visibility(self) -> None:
        mode = self._mode.currentText()
        # show column-col for pivot/crosstab; value+agg for group/pivot
        self._set_row_visible(self._column, mode in ("Pivot table", "Cross-tab"))
        self._set_row_visible(self._value, mode in ("Group by", "Pivot table"))
        self._set_row_visible(self._agg, mode in ("Group by", "Pivot table"))
        # margins + percent-of-total apply only to the pivot table.
        self._set_row_visible(self._totals, mode == "Pivot table")
        self._set_row_visible(self._pct, mode == "Pivot table")

    def _set_row_visible(self, widget, visible: bool) -> None:
        widget.setVisible(visible)
        lbl = self.layout().itemAt(0).layout().labelForField(widget)
        if lbl is not None:
            lbl.setVisible(visible)

    def _apply(self) -> None:
        mode = self._mode.currentText()
        try:
            rows = self._rows()
            if mode == "Group by":
                out = P.group_by(rows, [self._index.currentText()],
                                 self._value.currentText(), self._agg.currentData())
            elif mode == "Pivot table":
                out = P.pivot_table(rows, self._index.currentText(),
                                    self._column.currentText(),
                                    self._value.currentText(), self._agg.currentData(),
                                    margins=self._totals.isChecked(),
                                    pct_of=self._pct.currentData())
            else:
                out = P.crosstab(rows, self._index.currentText(),
                                 self._column.currentText())
        except (P.PivotError, ValueError) as exc:
            QMessageBox.warning(self, "Pivot", str(exc))
            return
        r0, c0 = parse_a1(self._out.text())
        sheet = self._win._doc.workbook.sheet
        for i, row in enumerate(out):
            for j, val in enumerate(row):
                sheet.set_cell(r0 + i, c0 + j, str(val))
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(
            f"{mode}: {len(out) - 1} rows written at {self._out.text()}")
        self.accept()
