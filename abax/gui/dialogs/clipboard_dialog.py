"""Clipboard history manager — review, pin, and reuse past copies.

Reads the window's `ClipboardManager`. Paste drops an entry's text into the
active cell; Copy puts it back on the system clipboard.
"""

from __future__ import annotations

from .._qtcompat import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)


class ClipboardDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Clipboard history")
        self.resize(420, 420)
        self.setModal(False)
        self._build()
        self._reload()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        self._list = QListWidget(self)
        self._list.itemDoubleClicked.connect(lambda *_: self._paste())
        layout.addWidget(self._list)

        row = QHBoxLayout()
        for label, slot in [
            ("Paste", self._paste),
            ("Copy", self._copy),
            ("Pin", self._toggle_pin),
            ("Remove", self._remove),
            ("Clear", self._clear),
        ]:
            b = QPushButton(label, self)
            b.clicked.connect(slot)
            row.addWidget(b)
        layout.addLayout(row)

    def _mgr(self):
        return self._win._clipboard

    def _reload(self) -> None:
        self._list.clear()
        for e in self._mgr().entries():
            prefix = "📌 " if e.pinned else ""
            self._list.addItem(prefix + e.label)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _current(self):
        idx = self._list.currentRow()
        return idx, self._mgr().get(idx)

    def _paste(self) -> None:
        _, entry = self._current()
        if entry is None:
            return
        from ...core.fill import clip_from_tsv, paste_clip

        row = max(0, self._win._table.currentRow())
        col = max(0, self._win._table.currentColumn())
        clip = clip_from_tsv(entry.text, (row, col))
        paste_clip(self._win._doc.workbook.sheet, clip, (row, col), mode="absolute",
                   on_set=self._win._record)
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status("pasted from history")

    def _copy(self) -> None:
        from .._qtcompat import QApplication

        _, entry = self._current()
        if entry is None:
            return
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(entry.text)
        self._win._set_status("copied to system clipboard")

    def _toggle_pin(self) -> None:
        idx, entry = self._current()
        if entry is not None:
            self._mgr().pin(idx, not entry.pinned)
            self._reload()

    def _remove(self) -> None:
        idx, entry = self._current()
        if entry is not None:
            self._mgr().remove(idx)
            self._reload()

    def _clear(self) -> None:
        self._mgr().clear(keep_pinned=True)
        self._reload()
