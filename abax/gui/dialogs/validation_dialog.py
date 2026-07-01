"""Data-validation dialog — set a dropdown list or input rule on the selection.

Builds a :class:`abax.core.validation.ValidationRule` and hands it to the
window's ``apply_validation``. List rules give the selected cells a dropdown
editor; number/text rules reject invalid entries on commit.
"""

from __future__ import annotations

from .._qtcompat import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QPushButton,
)
from ...core import validation as V
from ...core.reference import to_a1

_KINDS = [
    ("list", "Dropdown list (comma-separated values)"),
    ("whole", "Whole number"),
    ("decimal", "Decimal number"),
    ("textlen", "Text length"),
]
_OPS = [
    ("between", "between"),
    ("notbetween", "not between"),
    ("eq", "equal to"),
    ("ne", "not equal to"),
    ("gt", "greater than"),
    ("lt", "less than"),
    ("ge", "≥"),
    ("le", "≤"),
]


class ValidationDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Data validation")
        r1, c1, r2, c2 = window._selected_bounds()
        self._bounds = (r1, c1, r2, c2)
        self._build(r1, c1, r2, c2)

    def _build(self, r1, c1, r2, c2) -> None:
        form = QFormLayout(self)
        rng = to_a1(r1, c1) if (r1 == r2 and c1 == c2) else f"{to_a1(r1, c1)}:{to_a1(r2, c2)}"
        self._kind = QComboBox(self)
        for code, label in _KINDS:
            self._kind.addItem(label, code)
        self._op = QComboBox(self)
        for code, label in _OPS:
            self._op.addItem(label, code)
        self._p1 = QLineEdit(self)
        self._p2 = QLineEdit(self)
        self._p1.setPlaceholderText("list values (a, b, c) — or lower bound")
        self._p2.setPlaceholderText("upper bound (for between)")
        from .._qtcompat import QLabel

        form.addRow(QLabel(f"Range: {rng}", self))
        form.addRow("Allow:", self._kind)
        form.addRow("Condition:", self._op)
        form.addRow("Value(s):", self._p1)
        form.addRow("Upper:", self._p2)
        apply_btn = QPushButton("Apply", self)
        apply_btn.clicked.connect(self._apply)
        clear_btn = QPushButton("Clear validation on selection", self)
        clear_btn.clicked.connect(self._clear)
        form.addRow(apply_btn)
        form.addRow(clear_btn)

    def _apply(self) -> None:
        kind = self._kind.currentData()
        try:
            if kind == "list":
                values = [v.strip() for v in self._p1.text().split(",") if v.strip()]
                rule = V.list_rule(tuple(values))
            else:
                rule = V.number_rule(kind, self._op.currentData(),
                                     self._p1.text().strip(), self._p2.text().strip())
        except ValueError:
            return
        self._win.apply_validation(self._bounds, rule)
        self.accept()

    def _clear(self) -> None:
        self._win.clear_validation()
        self.accept()
