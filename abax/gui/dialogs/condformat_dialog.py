"""Add-a-conditional-format dialog — appends a CondRule to the active sheet.

Colors are picked with the native color dialog; the rule is applied immediately
and persists with the workbook. The form reshapes itself to the chosen rule —
only the fields a rule actually uses are shown, with a one-line description — so
the many rule kinds stay approachable.
"""

from __future__ import annotations

from .._qtcompat import (
    QColor,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)
from ...core.format.condformat import CondRule
from ...core.reference import to_a1

# (internal kind, human label) — grouped: comparisons, text, presence, ranking,
# then colour scales. currentData() carries the internal kind.
_KINDS: list[tuple[str, str]] = [
    (">", "Greater than"),
    ("<", "Less than"),
    (">=", "Greater than or equal to"),
    ("<=", "Less than or equal to"),
    ("==", "Equal to"),
    ("!=", "Not equal to"),
    ("between", "Between"),
    ("contains", "Text contains"),
    ("beginswith", "Text begins with"),
    ("endswith", "Text ends with"),
    ("regex", "Matches regex"),
    ("blank", "Is blank"),
    ("notblank", "Is not blank"),
    ("duplicate", "Duplicate values"),
    ("unique", "Unique values"),
    ("above_avg", "Above average"),
    ("below_avg", "Below average"),
    ("top_n", "Top N items"),
    ("bottom_n", "Bottom N items"),
    ("top_pct", "Top N%"),
    ("bottom_pct", "Bottom N%"),
    ("colorscale", "2-colour scale"),
    ("colorscale3", "3-colour scale"),
]

# The label + placeholder for the first value field, per kind (kinds absent here
# take no value: blank/notblank, duplicate/unique, above/below average, scales).
_VALUE: dict[str, tuple[str, str]] = {
    ">": ("Value", "e.g. 100"),
    "<": ("Value", "e.g. 100"),
    ">=": ("Value", "e.g. 100"),
    "<=": ("Value", "e.g. 100"),
    "==": ("Value", "number or text"),
    "!=": ("Value", "number or text"),
    "between": ("Low value", "e.g. 10"),
    "contains": ("Text", "substring to find"),
    "beginswith": ("Text", "prefix"),
    "endswith": ("Text", "suffix"),
    "regex": ("Pattern", r"regex, e.g. ^\d{3}-\d{4}$  ((?i) for case-insensitive)"),
    "top_n": ("How many", "e.g. 10"),
    "bottom_n": ("How many", "e.g. 10"),
    "top_pct": ("Percent", "e.g. 25"),
    "bottom_pct": ("Percent", "e.g. 25"),
}
_VALUE2_KINDS = {"between"}          # also needs a second value ("High value")
_SCALE_KINDS = {"colorscale", "colorscale3"}

_HELP: dict[str, str] = {
    "between": "Highlights cells whose number is between the low and high values (inclusive).",
    "contains": "Highlights cells whose text contains this substring (case-insensitive).",
    "beginswith": "Highlights cells whose text starts with this prefix (case-insensitive).",
    "endswith": "Highlights cells whose text ends with this suffix (case-insensitive).",
    "regex": "Highlights cells whose text matches this regular expression "
             "(case-sensitive; prefix with (?i) for case-insensitive).",
    "blank": "Highlights empty cells.",
    "notblank": "Highlights cells that have any value.",
    "duplicate": "Highlights values that appear more than once in the range.",
    "unique": "Highlights values that appear exactly once in the range.",
    "above_avg": "Highlights numbers above the range's average.",
    "below_avg": "Highlights numbers below the range's average.",
    "top_n": "Highlights the N largest numbers (ties at the cut-off are included).",
    "bottom_n": "Highlights the N smallest numbers (ties at the cut-off are included).",
    "top_pct": "Highlights the top N% of numbers by value.",
    "bottom_pct": "Highlights the bottom N% of numbers by value.",
    "colorscale": "Shades cells on a gradient from the min colour (lowest) to the max colour (highest).",
    "colorscale3": "Shades cells min → midpoint → max across the range.",
}


class CondFormatDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self._color = "#a6e3a1"   # solid fill / scale min
        self._color2 = "#f38ba8"  # scale max
        self._color3 = "#f9e2af"  # 3-colour-scale midpoint
        self.setWindowTitle("Conditional format")
        self._build()
        self._on_kind()

    def _build(self) -> None:
        form = QFormLayout(self)
        self._range = QLineEdit(self._default_range(), self)

        self._kind = QComboBox(self)
        for key, label in _KINDS:
            self._kind.addItem(label, key)
        self._kind.currentIndexChanged.connect(self._on_kind)

        self._value = QLineEdit(self)
        self._value2 = QLineEdit(self)
        self._value_label = QLabel("Value:", self)
        self._value2_label = QLabel("High value:", self)

        self._color_btn = QPushButton(self)
        self._color2_btn = QPushButton(self)
        self._color3_btn = QPushButton(self)
        self._color_label = QLabel("Fill colour:", self)
        self._color2_label = QLabel("Max colour:", self)
        self._color3_label = QLabel("Midpoint colour:", self)
        self._color_btn.clicked.connect(lambda: self._pick("_color", self._color_btn))
        self._color2_btn.clicked.connect(lambda: self._pick("_color2", self._color2_btn))
        self._color3_btn.clicked.connect(lambda: self._pick("_color3", self._color3_btn))
        self._paint(self._color_btn, self._color)
        self._paint(self._color2_btn, self._color2)
        self._paint(self._color3_btn, self._color3)

        # Optional CSS: overrides the plain fill with a full style (text colour,
        # bold/italic/underline, background) when the rule matches.
        self._css = QLineEdit(self)
        self._css.setPlaceholderText("optional, e.g. color: white; background: #c00; font-weight: bold")
        self._css_label = QLabel("Style (CSS):", self)

        self._help = QLabel(self)
        self._help.setWordWrap(True)
        self._help.setStyleSheet("color: palette(mid); font-size: 11px;")

        form.addRow("Range:", self._range)
        form.addRow("Condition:", self._kind)
        form.addRow(self._value_label, self._value)
        form.addRow(self._value2_label, self._value2)
        form.addRow(self._color_label, self._color_btn)
        form.addRow(self._color2_label, self._color2_btn)
        form.addRow(self._color3_label, self._color3_btn)
        form.addRow(self._css_label, self._css)
        form.addRow("", self._help)
        self._form = form

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    # --- reshape the form for the chosen kind -----------------------------

    def _on_kind(self) -> None:
        kind = self._kind.currentData()
        # First value field
        if kind in _VALUE:
            label, placeholder = _VALUE[kind]
            self._value_label.setText(f"{label}:")
            self._value.setPlaceholderText(placeholder)
            self._row_visible(self._value_label, self._value, True)
        else:
            self._row_visible(self._value_label, self._value, False)
        # Second value field (between only)
        self._row_visible(self._value2_label, self._value2, kind in _VALUE2_KINDS)
        # Colours
        if kind in _SCALE_KINDS:
            self._color_label.setText("Min colour:")
            self._row_visible(self._color2_label, self._color2_btn, True)
            self._row_visible(self._color3_label, self._color3_btn, kind == "colorscale3")
        else:
            self._color_label.setText("Fill colour:")
            self._row_visible(self._color2_label, self._color2_btn, False)
            self._row_visible(self._color3_label, self._color3_btn, False)
        # CSS styling applies to any match-based rule, not to the colour scales.
        self._row_visible(self._css_label, self._css, kind not in _SCALE_KINDS)
        self._help.setText(_HELP.get(kind, ""))

    @staticmethod
    def _row_visible(label, field, visible: bool) -> None:
        label.setVisible(visible)
        field.setVisible(visible)

    # --- helpers ----------------------------------------------------------

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
        btn.setText(hexc)
        btn.setStyleSheet(f"background-color: {hexc}; color: #111;")

    def _accept(self) -> None:
        kind = self._kind.currentData()
        css = ""
        if kind in _SCALE_KINDS:
            value = self._color            # scale min colour
            value2 = self._color2          # scale max colour
            color = self._color3 if kind == "colorscale3" else self._color
        else:
            value = self._value.text().strip() or None if kind in _VALUE else None
            value2 = self._value2.text().strip() or None if kind in _VALUE2_KINDS else None
            color = self._color
            css = self._css.text().strip()
        rule = CondRule(
            range=self._range.text().strip() or self._default_range(),
            kind=kind,
            value=value,
            value2=value2,
            color=color,
            css=css,
        )
        self._win._doc.workbook.sheet.cond_rules.append(rule)
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        label = dict(_KINDS).get(kind, kind)
        self._win._set_status(f"added conditional format: {label}")
        self.accept()
