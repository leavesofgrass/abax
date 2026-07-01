"""Multi-condition column filter — hide rows that don't match ALL conditions.

Builds up to three predicates (column / operator / value), ANDed, over the
selected region and hands them to the window's ``apply_filter`` (non-destructive
row hiding). Matching logic lives in :mod:`abax.core.sortfilter`.
"""

from __future__ import annotations

from .._qtcompat import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QPushButton,
)
from ...core.reference import index_to_col

_OPS = [
    ("contains", "contains"),
    ("eq", "equals"),
    ("ne", "not equal"),
    ("startswith", "starts with"),
    ("endswith", "ends with"),
    ("gt", "greater than"),
    ("lt", "less than"),
    ("ge", "≥"),
    ("le", "≤"),
    ("between", "between (a|b)"),
    ("nonblank", "is not blank"),
    ("blank", "is blank"),
]
_LEVELS = 3


class FilterDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Filter")
        self._bounds = window._sort_region_bounds()
        self._rows: list[tuple] = []
        self._build()

    def _build(self) -> None:
        from .._qtcompat import QHBoxLayout, QWidget

        form = QFormLayout(self)
        _r1, c1, _r2, c2 = self._bounds
        for level in range(_LEVELS):
            col = QComboBox(self)
            col.addItem("(none)", -1)
            for c in range(c1, c2 + 1):
                col.addItem(f"Col {index_to_col(c)}", c)
            if level == 0 and col.count() > 1:
                col.setCurrentIndex(1)
            op = QComboBox(self)
            for code, label in _OPS:
                op.addItem(label, code)
            val = QLineEdit(self)
            holder = QWidget()
            lay = QHBoxLayout(holder)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(col, 1)
            lay.addWidget(op, 1)
            lay.addWidget(val, 1)
            form.addRow("Where:" if level == 0 else "And:", holder)
            self._rows.append((col, op, val))
        apply_btn = QPushButton("Apply filter", self)
        apply_btn.clicked.connect(self._apply)
        clear_btn = QPushButton("Clear filter", self)
        clear_btn.clicked.connect(self._clear)
        form.addRow(apply_btn)
        form.addRow(clear_btn)

    def _apply(self) -> None:
        preds = []
        for col, op, val in self._rows:
            c = col.currentData()
            if c is not None and c >= 0:
                preds.append((c, op.currentData(), val.text()))
        if not preds:
            self.reject()
            return
        self._win.apply_filter(self._bounds, preds)
        self.accept()

    def _clear(self) -> None:
        self._win.clear_filter()
        self.accept()
