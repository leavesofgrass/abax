"""Formula dependency viewer — the current cell's precedents or dependents.

Reads the window's current cell and renders its dependency tree, computed by
:mod:`abax.core.deptrace`, as box-drawing ASCII in a monospace pane. Toggle the
**direction** (Precedents = what the cell reads; Dependents = what reads it),
set the **depth**, and Refresh to recompute against wherever the cursor now is.

A blank or non-formula cell in the Precedents direction shows ``(no
precedents)``; a cell nothing references in the Dependents direction shows ``(no
dependents)``. Nothing here mutates the workbook.
"""

from __future__ import annotations

from .._qtcompat import (
    QComboBox,
    QDialog,
    QFont,
    QFontDatabase,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from ...core import deptrace
from ...core.reference import to_a1

_DIRECTIONS = ("Precedents", "Dependents")


class DepTraceDialog(QDialog):
    """Show the current cell's precedent / dependent tree."""

    def __init__(self, window) -> None:
        super().__init__(window if isinstance(window, QWidget) else None)
        self._win = window
        self.setWindowTitle("Dependency trace")
        self.resize(560, 460)
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        root = QVBoxLayout(self)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Direction", self))
        self._direction = QComboBox(self)
        self._direction.addItems(list(_DIRECTIONS))
        self._direction.currentIndexChanged.connect(lambda _=0: self.refresh())
        bar.addWidget(self._direction)

        bar.addWidget(QLabel("Depth", self))
        self._depth = QSpinBox(self)
        self._depth.setRange(1, 16)
        self._depth.setValue(8)
        self._depth.valueChanged.connect(lambda _=0: self.refresh())
        bar.addWidget(self._depth)

        refresh = QPushButton("Refresh", self)
        refresh.clicked.connect(self.refresh)
        bar.addWidget(refresh)
        bar.addStretch(1)
        root.addLayout(bar)

        self._view = QPlainTextEdit(self)
        self._view.setReadOnly(True)
        self._view.setFont(self._mono_font())
        self._view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        root.addWidget(self._view, 1)

        self._status = QLabel("", self)
        root.addWidget(self._status)

    @staticmethod
    def _mono_font() -> QFont:
        try:
            font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        except Exception:  # pragma: no cover - defensive across bindings
            font = QFont("monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        return font

    # ------------------------------------------------------------------ #
    def _current_cell(self) -> tuple[int, int]:
        table = self._win._table
        row = max(0, table.currentRow())
        col = max(0, table.currentColumn())
        return row, col

    def trace_text(self, direction: str, depth: int) -> str:
        """Return the ASCII trace for the current cell — Qt-free logic path.

        ``direction`` is ``"Precedents"`` or ``"Dependents"``. Never raises; a
        blank or non-formula cell yields the ``(no precedents)`` /
        ``(no dependents)`` placeholder.
        """
        row, col = self._current_cell()
        sheet = self._win._doc.workbook.sheet
        try:
            if direction == "Dependents":
                node = deptrace.trace_dependents(sheet, row, col, max_depth=depth)
            else:
                node = deptrace.trace_precedents(sheet, row, col, max_depth=depth)
        except Exception:  # pragma: no cover - never crash on a bad cell
            return f"({to_a1(row, col)}: trace failed)"

        if not node.children:
            noun = "dependents" if direction == "Dependents" else "precedents"
            return f"{deptrace.render_ascii(node)}\n(no {noun})"
        return deptrace.render_ascii(node)

    def refresh(self) -> None:
        direction = self._direction.currentText()
        depth = self._depth.value()
        row, col = self._current_cell()
        self._view.setPlainText(self.trace_text(direction, depth))
        self._status.setText(f"{direction} of {to_a1(row, col)}")
