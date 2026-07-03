"""Paste Special — choose how the clipboard block lands in the sheet.

Offers the three operations that are both common and unambiguous: paste
**formulas** (the normal relative-shift paste) or **values only** (drop the
formulas, keep the computed results), optionally **transposed** (rows ↔ columns)
and/or **skipping blanks** (don't overwrite the destination where the source is
empty). Transpose implies values — rotating relative references is out of scope,
so transposing formulas would silently mis-shift them.
"""

from __future__ import annotations

from .._qtcompat import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)


class PasteSpecialDialog(QDialog):
    def __init__(self, window, *, formulas_available: bool = True) -> None:
        super().__init__(window)
        self.setWindowTitle("Paste Special")
        self.setModal(True)
        self._formulas_available = formulas_available
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        box = QGroupBox("Paste", self)
        box_layout = QVBoxLayout(box)
        self._rb_formulas = QRadioButton("Formulas", box)
        self._rb_values = QRadioButton("Values only", box)
        box_layout.addWidget(self._rb_formulas)
        box_layout.addWidget(self._rb_values)
        layout.addWidget(box)

        self._cb_transpose = QCheckBox("Transpose (rows ↔ columns)", self)
        self._cb_skip_blanks = QCheckBox("Skip blanks", self)
        layout.addWidget(self._cb_transpose)
        layout.addWidget(self._cb_skip_blanks)

        note = QLabel("Transpose pastes values.", self)
        note.setEnabled(False)  # muted caption
        layout.addWidget(note)

        if self._formulas_available:
            self._rb_formulas.setChecked(True)
        else:
            self._rb_formulas.setChecked(False)
            self._rb_formulas.setEnabled(False)
            self._rb_values.setChecked(True)

        # Transpose forces values (see module docstring); reflect that in the UI.
        self._cb_transpose.toggled.connect(self._on_transpose_toggled)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_transpose_toggled(self, on: bool) -> None:
        if on:
            self._rb_values.setChecked(True)
            self._rb_formulas.setEnabled(False)
        else:
            self._rb_formulas.setEnabled(self._formulas_available)

    def options(self) -> dict:
        transpose = self._cb_transpose.isChecked()
        return {
            "values": self._rb_values.isChecked() or transpose,
            "transpose": transpose,
            "skip_blanks": self._cb_skip_blanks.isChecked(),
        }

    @classmethod
    def get_options(cls, window, *, formulas_available: bool = True) -> dict | None:
        """Show the dialog modally; return the chosen options, or None if cancelled."""
        dlg = cls(window, formulas_available=formulas_available)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return dlg.options()
