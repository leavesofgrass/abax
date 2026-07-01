"""Budget setup wizard — collect income + categories, drop in a live budget sheet.

A small guided dialog: enter monthly income, optionally seed categories from the
50/30/20 rule, tweak the amounts, then *Create budget sheet*. It builds a new
worksheet via :func:`abax.core.budget.budget_cells`, so the budget is a live
spreadsheet (Spent is a ``SUMIF`` over an expenses log, Remaining updates as you
type). The model and layout are the tested core; this is just the form.
"""

from __future__ import annotations

from .._qtcompat import (
    QAbstractItemView,
    QComboBox,
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
from ...core import budget as BUD


def _bold(text: str) -> QLabel:
    lab = QLabel(text)
    f = lab.font()
    f.setBold(True)
    lab.setFont(f)
    return lab


class BudgetWizard(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Budget setup wizard")
        self.resize(460, 460)
        root = QVBoxLayout(self)

        root.addWidget(_bold("1. Monthly income"))
        row = QHBoxLayout()
        self._income = QLineEdit("3000", self)
        row.addWidget(QLabel("Income:", self))
        row.addWidget(self._income, 1)
        self._template = QComboBox(self)
        self._template.addItems(["50/30/20 rule", "Blank"])
        row.addWidget(self._template)
        apply_btn = QPushButton("Seed categories", self)
        apply_btn.clicked.connect(self._seed)
        row.addWidget(apply_btn)
        root.addLayout(row)

        root.addWidget(_bold("2. Categories and monthly amounts"))
        self._table = QTableWidget(0, 2, self)
        self._table.setHorizontalHeaderLabels(["Category", "Monthly amount"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        root.addWidget(self._table, 1)

        edit = QHBoxLayout()
        add = QPushButton("Add row", self)
        add.clicked.connect(lambda: self._add_row("", ""))
        rem = QPushButton("Remove row", self)
        rem.clicked.connect(self._remove_row)
        edit.addWidget(add)
        edit.addWidget(rem)
        edit.addStretch(1)
        self._summary = QLabel("", self)
        edit.addWidget(self._summary)
        root.addLayout(edit)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel", self)
        cancel.clicked.connect(self.reject)
        create = QPushButton("Create budget sheet", self)
        create.clicked.connect(self.create_budget)
        actions.addWidget(cancel)
        actions.addWidget(create)
        root.addLayout(actions)

        self._table.itemChanged.connect(lambda _i: self._update_summary())
        self._seed()

    # --- data -----------------------------------------------------------
    def income(self) -> float:
        try:
            return float(self._income.text() or 0)
        except ValueError:
            return 0.0

    def _add_row(self, name: str, amount: str) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        self._table.setItem(r, 0, QTableWidgetItem(name))
        self._table.setItem(r, 1, QTableWidgetItem(amount))

    def _remove_row(self) -> None:
        r = self._table.currentRow()
        if r >= 0:
            self._table.removeRow(r)
        self._update_summary()

    def _seed(self) -> None:
        self._table.setRowCount(0)
        if self._template.currentText().startswith("50/30/20"):
            cats = BUD.fifty_thirty_twenty(self.income())
            for c in cats:
                self._add_row(c.name, BUD._fmt(c.budgeted))
        else:
            for name in BUD.suggested_categories():
                self._add_row(name, "0")
        self._update_summary()

    def categories(self) -> list[BUD.Category]:
        out = []
        for r in range(self._table.rowCount()):
            name_item = self._table.item(r, 0)
            amt_item = self._table.item(r, 1)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            try:
                amount = float(amt_item.text()) if amt_item and amt_item.text() else 0.0
            except ValueError:
                amount = 0.0
            out.append(BUD.Category(name, amount))
        return out

    def _update_summary(self) -> None:
        total = sum(c.budgeted for c in self.categories())
        left = self.income() - total
        self._summary.setText(f"Allocated {total:.0f} / {self.income():.0f}  "
                              f"(unallocated {left:.0f})")

    # --- create ---------------------------------------------------------
    def _unique_name(self, base: str) -> str:
        wb = self._win._doc.workbook
        existing = {s.name for s in wb.sheets}
        if base not in existing:
            return base
        n = 2
        while f"{base} {n}" in existing:
            n += 1
        return f"{base} {n}"

    def create_budget(self) -> str:
        cats = self.categories()
        if not cats:
            QMessageBox.warning(self, "Budget", "Add at least one category.")
            return ""
        wb = self._win._doc.workbook
        name = self._unique_name("Budget")
        sheet = wb.add_sheet(name)
        budget = BUD.Budget(income=self.income(), categories=cats)
        for r, c, raw in BUD.budget_cells(budget):
            sheet.set_cell(r, c, raw)
        wb.active = len(wb.sheets) - 1
        sheet.recalculate()
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(f"created budget sheet '{name}'")
        self.accept()
        return name
