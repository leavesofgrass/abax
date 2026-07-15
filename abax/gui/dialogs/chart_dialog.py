"""Insert / edit an embedded chart — a ChartObject anchored on the active sheet.

The dialog only gathers the fields (kind, source range prefilled from the
current selection, optional labels range, title, pixel size). Appending to
``sheet.charts`` (insert) or mutating the object (edit) happens in the window's
ToolsMixin under a single undo checkpoint, mirroring every other sheet
mutation. Range validity is deliberately not enforced here: a dead or not-yet
filled range renders as a placeholder box on the grid (see
``abax/gui/chart_overlay.py``), which is friendlier than blocking OK.
"""

from __future__ import annotations

from .._qtcompat import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)
from ...core.chartobj import CHART_KINDS
from ...core.reference import to_a1


class ChartDialog(QDialog):
    """Gather the fields of one embedded chart (create when ``chart`` is None)."""

    def __init__(self, window, chart=None) -> None:
        super().__init__(window)
        self._win = window
        self._chart = chart
        self.setWindowTitle("Edit embedded chart" if chart is not None
                            else "Insert embedded chart")
        self._build()
        if chart is not None:
            self._load(chart)

    # --- construction ------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        form = QFormLayout()

        self._kind = QComboBox(self)
        self._kind.addItems(list(CHART_KINDS))
        form.addRow("Kind:", self._kind)

        self._source = QLineEdit(self)
        self._source.setPlaceholderText("e.g. A1:B10 or Data!A1:C10")
        selection = self._selection_range()
        if selection:
            self._source.setText(selection)
        form.addRow("Source range:", self._source)

        self._labels = QLineEdit(self)
        self._labels.setPlaceholderText(
            "optional — category labels (bar / waterfall / heatmap)")
        form.addRow("Labels range:", self._labels)

        self._title = QLineEdit(self)
        form.addRow("Title:", self._title)

        self._width = QSpinBox(self)
        self._width.setRange(80, 4000)
        self._width.setValue(480)
        self._width.setSuffix(" px")
        form.addRow("Width:", self._width)

        self._height = QSpinBox(self)
        self._height.setRange(60, 4000)
        self._height.setValue(320)
        self._height.setSuffix(" px")
        form.addRow("Height:", self._height)

        root.addLayout(form)

        hint = QLabel(
            "Ranges are A1-style and may be sheet-qualified (Data!A1:C10). The "
            "chart floats over the grid anchored to a cell, re-renders after "
            "every edit and recalc, and is saved with the workbook.", self)
        hint.setWordWrap(True)
        root.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # --- data --------------------------------------------------------------

    def _selection_range(self) -> str:
        """The current grid selection as an A1 range ("" when unavailable)."""
        try:
            r1, c1, r2, c2 = self._win._selected_bounds()
        except Exception:
            return ""
        first = to_a1(r1, c1)
        return first if (r1, c1) == (r2, c2) else f"{first}:{to_a1(r2, c2)}"

    def _load(self, chart) -> None:
        """Seed the widgets from an existing chart (edit mode)."""
        idx = self._kind.findText(chart.kind)
        if idx >= 0:
            self._kind.setCurrentIndex(idx)
        self._source.setText(chart.source)
        self._labels.setText(chart.labels)
        self._title.setText(chart.title)
        self._width.setValue(int(chart.width))
        self._height.setValue(int(chart.height))

    def values(self) -> dict:
        """The gathered ChartObject fields (anchor/id are the caller's concern)."""
        return {
            "kind": self._kind.currentText(),
            "source": self._source.text().strip(),
            "labels": self._labels.text().strip(),
            "title": self._title.text().strip(),
            "width": int(self._width.value()),
            "height": int(self._height.value()),
        }

    def _on_ok(self) -> None:
        if not self._source.text().strip():
            QMessageBox.warning(self, "Embedded chart",
                                "A source range is required (e.g. A1:B10).")
            return
        self.accept()
