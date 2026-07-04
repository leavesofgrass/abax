"""Cell Borders — pick which edges get a border and how thick.

The dialog gathers a per-edge ``{edge: style}`` map (the shape
:meth:`abax.core.sheet.Sheet.set_cell_border` stores) plus an *apply mode*: the
window then writes that map over the whole selection as one undo checkpoint.

Two mode shortcuts sit above the per-edge pickers: **All** ticks every edge and
**None** clears them. "None" produces an empty map, which the caller reads as
"remove every border in the selection" — so the same dialog both sets and clears
borders. Style is one of the fidelity model's three weights: thin / medium /
thick.
"""

from __future__ import annotations

from .._qtcompat import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

# The border weights the core fidelity model understands (Sheet.set_cell_border).
STYLES = ("thin", "medium", "thick")

# Cell edges, in the order they appear in the dialog / a border map.
EDGES = ("top", "bottom", "left", "right")


class BorderDialog(QDialog):
    """Edge pickers (top/bottom/left/right + All/None) × a thin/medium/thick style.

    :meth:`border_spec` returns ``(edges_map, clear)`` where ``edges_map`` is the
    ``{edge: style}`` dict to stamp onto each selected cell and ``clear`` is True
    when the user chose "None" (an empty map that means *remove all borders*).
    """

    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Cell borders")
        self.setModal(True)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        style_row = QGroupBox("Line weight", self)
        style_layout = QVBoxLayout(style_row)
        self._style = QComboBox(style_row)
        self._style.addItems(STYLES)
        self._style.setCurrentIndex(0)  # thin by default
        style_layout.addWidget(self._style)
        layout.addWidget(style_row)

        edge_box = QGroupBox("Edges", self)
        edge_layout = QVBoxLayout(edge_box)
        self._edges: dict[str, QCheckBox] = {}
        for edge in EDGES:
            cb = QCheckBox(edge.capitalize(), edge_box)
            self._edges[edge] = cb
            edge_layout.addWidget(cb)
        layout.addWidget(edge_box)

        # Quick presets: tick / clear every edge in one click.
        preset_row = QGroupBox("Presets", self)
        preset_layout = QVBoxLayout(preset_row)
        self._all_btn = QPushButton("All edges", preset_row)
        self._none_btn = QPushButton("No borders", preset_row)
        self._all_btn.clicked.connect(self._select_all)
        self._none_btn.clicked.connect(self._select_none)
        preset_layout.addWidget(self._all_btn)
        preset_layout.addWidget(self._none_btn)
        layout.addWidget(preset_row)

        note = QLabel("“No borders” clears every border in the selection.", self)
        note.setEnabled(False)  # muted caption
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Track whether the user hit "No borders" so an all-unticked-by-hand OK
        # is distinguishable from an explicit clear.
        self._clear = False

    def _select_all(self) -> None:
        self._clear = False
        for cb in self._edges.values():
            cb.setChecked(True)

    def _select_none(self) -> None:
        self._clear = True
        for cb in self._edges.values():
            cb.setChecked(False)

    def border_spec(self) -> "tuple[dict[str, str], bool]":
        """``(edges_map, clear)`` — the ``{edge: style}`` map + the clear flag.

        ``clear`` is True when the user pressed "No borders": the caller removes
        every border in the selection. Otherwise ``edges_map`` names each ticked
        edge with the chosen weight.
        """
        style = self._style.currentText()
        edges = {edge: style for edge, cb in self._edges.items() if cb.isChecked()}
        clear = self._clear and not edges
        return edges, clear

    @classmethod
    def get_border(cls, window) -> "tuple[dict[str, str], bool] | None":
        """Show modally; return ``(edges_map, clear)`` or None if cancelled."""
        dlg = cls(window)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return dlg.border_spec()
