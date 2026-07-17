"""Formula manager — browse every function by category, with guidance.

A three-part dialog: a category list (from :mod:`abax.core.funcmeta`), a
searchable function list, and a guidance pane explaining what the selected
function *is and is used for* (signature + plain-English description + the
category's blurb). Double-click or Insert drops ``=NAME(`` into the formula
bar of the active cell. Backed by core.completion/funcmeta, so user-defined
functions appear automatically under "User-defined".
"""

from __future__ import annotations

from .._qtcompat import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    Qt,
    QVBoxLayout,
)
from ...core.funcmeta import catalog, describe

_ALL = "All functions"


class FormulaBrowser(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Formula manager")
        self.resize(680, 480)
        self._catalog = catalog()
        self._build()
        self._populate()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        self._filter = QLineEdit(self)
        self._filter.setPlaceholderText("Search functions…")
        self._filter.setAccessibleName("Search functions")
        self._filter.textChanged.connect(self._populate)
        root.addWidget(self._filter)

        body = QHBoxLayout()
        self._cats = QListWidget(self)
        self._cats.setAccessibleName("Function categories")
        self._cats.addItem(_ALL)
        self._cats.addItems(list(self._catalog))
        self._cats.setCurrentRow(0)
        self._cats.setMaximumWidth(190)
        self._cats.currentTextChanged.connect(lambda *_: self._populate())
        body.addWidget(self._cats)

        self._list = QListWidget(self)
        self._list.setAccessibleName("Functions")
        self._list.currentTextChanged.connect(self._show_info)
        self._list.itemDoubleClicked.connect(lambda *_: self._insert())
        body.addWidget(self._list, 1)
        root.addLayout(body, 1)

        # Guidance pane: name + signature, what it does, what the family is for.
        self._info = QLabel("", self)
        self._info.setWordWrap(True)
        self._info.setTextFormat(Qt.TextFormat.RichText)
        self._info.setAccessibleName("Function guidance")
        self._info.setMinimumHeight(84)
        root.addWidget(self._info)

        row = QHBoxLayout()
        b_insert = QPushButton("Insert", self)
        b_insert.setDefault(True)
        b_insert.clicked.connect(self._insert)
        row.addStretch(1)
        row.addWidget(b_insert)
        root.addLayout(row)

    def _names_for_scope(self) -> list[str]:
        cat = self._cats.currentItem().text() if self._cats.currentItem() else _ALL
        if cat == _ALL:
            return sorted(n for names in self._catalog.values() for n in names)
        return self._catalog.get(cat, [])

    def _populate(self, *_a) -> None:
        text = self._filter.text().upper()
        self._list.clear()
        self._list.addItems([n for n in self._names_for_scope() if text in n])
        if self._list.count():
            self._list.setCurrentRow(0)
        else:
            self._show_info("")

    def _show_info(self, name: str) -> None:
        if not name:
            # No function selected: show the category's own guidance.
            cat = self._cats.currentItem().text() if self._cats.currentItem() else _ALL
            if cat != _ALL and self._list.count() == 0:
                self._info.setText("")
            elif cat != _ALL:
                self._info.setText(f"<i>{cat}</i>")
            else:
                self._info.setText("")
            return
        d = describe(name)
        self._info.setText(
            f"<b>{d['signature']}</b><br>{d['description']}<br>"
            f"<i>{d['category']}</i> — {d['category_blurb']}"
        )

    def _insert(self) -> None:
        """Insert ``NAME(`` and hand the user the formula bar to finish it.

        The dialog **closes first**: it is non-modal, so left open it hides the
        updated bar — and the next grid click would rewrite the bar from the
        clicked cell, silently discarding the insert (the "Insert did nothing"
        trap). Closing + focusing the bar makes the state obvious: the stub is
        visible, the cursor is inside the call, Enter commits to the active cell.
        """
        item = self._list.currentItem()
        if item is None:
            return
        bar = self._win._formula_bar
        self.accept()
        bar.setFocus()
        bar.setText((bar.text() or "=") + item.text() + "(")
        bar.setCursorPosition(len(bar.text()))
        self._win._set_status(
            f"{item.text()}( inserted — type the arguments, Enter commits to the cell")
