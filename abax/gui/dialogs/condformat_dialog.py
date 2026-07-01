"""Add-a-conditional-format dialog — appends a CondRule to the active sheet.

Colors are picked with the native color dialog; the rule is applied immediately
and persists with the workbook. Visualizes value relationships at a glance.
"""

from __future__ import annotations

from .._qtcompat import (
    QColor,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
)
from ...core.format.condformat import CondRule
from ...core.reference import to_a1

_KINDS = [">", "<", ">=", "<=", "==", "!=", "between", "contains", "blank", "notblank", "colorscale"]


class CondFormatDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self._color = "#a6e3a1"
        self._color2 = "#f38ba8"
        self.setWindowTitle("Conditional format")
        self._build()

    def _build(self) -> None:
        form = QFormLayout(self)
        self._range = QLineEdit(self._default_range(), self)
        self._kind = QComboBox(self)
        self._kind.addItems(_KINDS)
        self._value = QLineEdit(self)
        self._value2 = QLineEdit(self)
        self._color_btn = QPushButton("Fill / scale-min...", self)
        self._color2_btn = QPushButton("Scale-max...", self)
        self._color_btn.clicked.connect(lambda: self._pick("_color", self._color_btn))
        self._color2_btn.clicked.connect(lambda: self._pick("_color2", self._color2_btn))
        self._paint(self._color_btn, self._color)
        self._paint(self._color2_btn, self._color2)

        form.addRow("Range:", self._range)
        form.addRow("Condition:", self._kind)
        form.addRow("Value:", self._value)
        form.addRow("Value 2 (between):", self._value2)
        form.addRow("Color:", self._color_btn)
        form.addRow("Color 2 (scale):", self._color2_btn)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _default_range(self) -> str:
        r1, c1, r2, c2 = self._win._selected_bounds()
        return f"{to_a1(r1, c1)}:{to_a1(r2, c2)}"

    def _pick(self, attr: str, btn) -> None:
        col = QColorDialog.getColor(QColor(getattr(self, attr)), self)
        if col.isValid():
            setattr(self, attr, col.name())
            self._paint(btn, col.name())

    @staticmethod
    def _paint(btn, hexc: str) -> None:
        btn.setStyleSheet(f"background-color: {hexc}; color: #111;")

    def _accept(self) -> None:
        kind = self._kind.currentText()
        value = self._value.text().strip()
        if kind == "colorscale":
            value, value2 = self._color, self._color2
        else:
            value2 = self._value2.text().strip() or None
            value = value or None
        rule = CondRule(
            range=self._range.text().strip() or self._default_range(),
            kind=kind,
            value=value,
            value2=value2,
            color=self._color,
        )
        self._win._doc.workbook.sheet.cond_rules.append(rule)
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(f"added conditional format ({kind})")
        self.accept()
