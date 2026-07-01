"""Function browser — searchable list of all functions (built-ins + UDFs).

Double-click or Insert drops ``=NAME(`` into the formula bar of the active cell.
Backed by core.completion (so user-defined functions appear automatically).
"""

from __future__ import annotations

from .._qtcompat import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)
from ...core.completion import function_names, signature


class FormulaBrowser(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Function browser")
        self.resize(420, 480)
        self._build()
        self._populate("")

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        self._filter = QLineEdit(self)
        self._filter.setPlaceholderText("Filter functions...")
        self._filter.textChanged.connect(self._populate)
        layout.addWidget(self._filter)

        self._list = QListWidget(self)
        self._list.currentTextChanged.connect(self._show_sig)
        self._list.itemDoubleClicked.connect(lambda *_: self._insert())
        layout.addWidget(self._list)

        self._sig = QLabel("", self)
        self._sig.setWordWrap(True)
        self._sig.setAccessibleName("Function signature")
        layout.addWidget(self._sig)

        b_insert = QPushButton("Insert", self)
        b_insert.clicked.connect(self._insert)
        layout.addWidget(b_insert)

    def _populate(self, text: str) -> None:
        text = text.upper()
        self._list.clear()
        self._list.addItems([n for n in function_names() if text in n])
        if self._list.count():
            self._list.setCurrentRow(0)

    def _show_sig(self, name: str) -> None:
        self._sig.setText(signature(name) if name else "")

    def _insert(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        bar = self._win._formula_bar
        bar.setText((bar.text() or "=") + item.text() + "(")
        bar.setFocus()
        self._win._set_status(f"inserted {item.text()}(")
