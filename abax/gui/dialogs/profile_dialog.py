"""Formula recalc profiler — a GUI front for :mod:`abax.core.profile`.

Times every formula cell in the workbook (or the active sheet), lists the
slowest first in a monospace report, and — for whichever cell you pick — draws
its precedent / dependent dependency graph as SVG. Pure presentation: all the
measurement and drawing lives in the stdlib-only ``profile`` core, so this
dialog only wires widgets to it.
"""

from __future__ import annotations

from .._qtcompat import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSvgWidget,
    QVBoxLayout,
)
from ...core import profile


class ProfileDialog(QDialog):
    """Rank formula cells by evaluation cost and inspect a cell's dependency DAG."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Formula profiler")
        self.resize(720, 560)
        self._timings: list = []
        self._build()

    # --- workbook access --------------------------------------------------

    @property
    def _workbook(self):
        return self._win._doc.workbook

    # --- construction -----------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Scope:"))
        self._scope = QComboBox(self)
        self._scope.addItem("All sheets", None)
        for sh in self._workbook.sheets:
            self._scope.addItem(sh.name, sh.name)
        controls.addWidget(self._scope)

        controls.addWidget(QLabel("Repeat:"))
        self._repeat = QSpinBox(self)
        self._repeat.setRange(1, 50)
        self._repeat.setValue(1)
        self._repeat.setToolTip("Average this many passes for a steadier estimate")
        controls.addWidget(self._repeat)

        run = QPushButton("Profile now", self)
        run.clicked.connect(self._run)
        controls.addWidget(run)
        controls.addStretch(1)
        root.addLayout(controls)

        self._report = QPlainTextEdit(self)
        self._report.setReadOnly(True)
        self._report.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        _monospace(self._report)
        self._report.setPlainText("Press “Profile now” to measure formula costs.")
        root.addWidget(self._report, 1)

        # Dependency-graph row.
        graph_row = QHBoxLayout()
        graph_row.addWidget(QLabel("Dependency graph of active cell:"))
        self._direction = QComboBox(self)
        self._direction.addItem("Precedents (feeds in)", "precedents")
        self._direction.addItem("Dependents (feeds out)", "dependents")
        graph_row.addWidget(self._direction)
        graph_btn = QPushButton("Draw graph", self)
        graph_btn.clicked.connect(self._draw_graph)
        graph_row.addWidget(graph_btn)
        self._save_svg = QCheckBox("Save SVG…", self)
        graph_row.addWidget(self._save_svg)
        graph_row.addStretch(1)
        root.addLayout(graph_row)

        if QSvgWidget is not None:
            self._graph = QSvgWidget(self)
            self._graph.setMinimumHeight(180)
            root.addWidget(self._graph, 1)
        else:
            self._graph = None
            note = QLabel("(install the Qt SVG module to see the dependency graph)")
            note.setWordWrap(True)
            root.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    # --- actions ----------------------------------------------------------

    def _run(self) -> None:
        scope = self._scope.currentData()
        self._timings = profile.profile_recalc(
            self._workbook, sheet=scope, repeat=self._repeat.value()
        )
        self._report.setPlainText(profile.format_report(self._timings, limit=200))

    def _draw_graph(self) -> None:
        """Render the active cell's dependency DAG as SVG (optionally saving it)."""
        row, col = self._win._current_cell()
        sheet = self._workbook.sheet
        svg = profile.dependency_svg(
            sheet, row, col, direction=self._direction.currentData()
        )
        if self._graph is not None:
            self._graph.load(bytearray(svg, "utf-8"))
        if self._save_svg.isChecked():
            self._save(svg)

    def _save(self, svg: str) -> None:
        from .._qtcompat import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "Save dependency graph", "dependencies.svg", "SVG (*.svg)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(svg)


def _monospace(widget) -> None:
    """Give ``widget`` a fixed-width font so the report columns line up."""
    from .._qtcompat import QFont

    font = QFont("monospace")
    font.setStyleHint(QFont.StyleHint.Monospace)
    widget.setFont(font)
