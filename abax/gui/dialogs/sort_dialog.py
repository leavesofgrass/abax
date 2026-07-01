"""Multi-column sort dialog.

Collects up to three sort levels (column + ascending/descending) over the
selected range, with an optional header row, and hands them to the window's
``apply_sort``. Sort logic lives in :mod:`abax.core.sortfilter`.
"""

from __future__ import annotations

from .._qtcompat import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QPushButton,
)
from ...core.reference import index_to_col

_LEVELS = 3


class SortDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Sort")
        self._bounds = window._sort_region_bounds()
        self._build()

    def _build(self) -> None:
        form = QFormLayout(self)
        r1, c1, r2, c2 = self._bounds
        self._header = QCheckBox("First row is a header", self)
        form.addRow(self._header)
        self._cols: list[QComboBox] = []
        self._dirs: list[QComboBox] = []
        for level in range(_LEVELS):
            col = QComboBox(self)
            col.addItem("(none)", -1)
            for c in range(c1, c2 + 1):
                col.addItem(f"Column {index_to_col(c)}", c)
            if level == 0 and col.count() > 1:
                col.setCurrentIndex(1)
            direction = QComboBox(self)
            direction.addItem("Ascending", False)
            direction.addItem("Descending", True)
            self._cols.append(col)
            self._dirs.append(direction)
            label = "Sort by:" if level == 0 else "Then by:"
            row_w = _pair(col, direction)
            form.addRow(label, row_w)
        btn = QPushButton("Sort", self)
        btn.clicked.connect(self._apply)
        form.addRow(btn)

    def _apply(self) -> None:
        keys = []
        for col, direction in zip(self._cols, self._dirs):
            c = col.currentData()
            if c is not None and c >= 0:
                keys.append((c, bool(direction.currentData())))
        if not keys:
            self.reject()
            return
        self._win.apply_sort(self._bounds, keys, self._header.isChecked())
        self.accept()


def _pair(a, b):
    from .._qtcompat import QHBoxLayout, QWidget

    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(a, 1)
    lay.addWidget(b)
    return w
