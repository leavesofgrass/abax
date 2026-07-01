"""Undo-history panel — a timeline of undoable/redoable actions.

Lists past actions (oldest at top) -> a current-state marker -> future (redo)
actions. Clicking a past action reverts to *before* it (undoing it and
everything after); clicking a future action redoes up to and including it.
Reads labels from :meth:`Document.undo_history`.
"""

from __future__ import annotations

from .._qtcompat import QDialog, QLabel, QListWidget, QVBoxLayout


class UndoHistoryDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self._actions: list = []        # parallel to list rows: ("undo"|"redo", times) | None
        self.setWindowTitle("Undo history")
        self.resize(260, 380)
        self.setModal(False)
        layout = QVBoxLayout(self)
        self._list = QListWidget(self)
        self._list.itemClicked.connect(self._on_click)
        layout.addWidget(self._list)
        layout.addWidget(QLabel("Click an entry to jump there.", self))

    def refresh(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        self._actions = []
        undo_labels, redo_labels = self._win._doc.undo_history()
        n = len(undo_labels)
        if not undo_labels and not redo_labels:
            self._list.addItem("(nothing to undo yet)")
            self._actions.append(None)
        for i, lab in enumerate(undo_labels):       # oldest -> newest
            self._list.addItem(f"↶  {lab or 'edit'}")
            self._actions.append(("undo", n - i))   # undo (n-i) times -> before this action
        self._list.addItem("*  current state")
        self._actions.append(None)
        for j, lab in enumerate(redo_labels):       # next-to-redo first
            self._list.addItem(f"↷  {lab or 'edit'}")
            self._actions.append(("redo", j + 1))
        self._list.blockSignals(False)

    def _on_click(self, item) -> None:
        row = self._list.row(item)
        if not (0 <= row < len(self._actions)) or self._actions[row] is None:
            return
        kind, times = self._actions[row]
        if kind == "undo":
            self._win.jump_undo(times)
        else:
            self._win.jump_redo(times)
