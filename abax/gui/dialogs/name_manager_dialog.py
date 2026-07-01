"""Named-range manager — list defined names, go to them, or delete them."""

from __future__ import annotations

from .._qtcompat import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)


class NameManagerDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Name manager")
        self.resize(320, 360)
        layout = QVBoxLayout(self)
        self._list = QListWidget(self)
        layout.addWidget(self._list)
        row = QHBoxLayout()
        go = QPushButton("Go to", self)
        go.clicked.connect(self._goto)
        delete = QPushButton("Delete", self)
        delete.clicked.connect(self._delete)
        row.addWidget(go)
        row.addWidget(delete)
        layout.addLayout(row)
        self._targets: list[str] = []
        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        self._targets = []
        for name, target in self._win._doc.workbook.names.names():
            self._list.addItem(f"{name}  =  {target}")
            self._targets.append(target)

    def _selected_index(self) -> int:
        return self._list.currentRow()

    def _goto(self) -> None:
        i = self._selected_index()
        if 0 <= i < len(self._targets):
            from ...core.navigation import parse_target

            tgt = parse_target(self._targets[i].split("!")[-1])
            self._win._table.setCurrentCell(tgt[0], tgt[1])
            self.accept()

    def _delete(self) -> None:
        i = self._selected_index()
        if not (0 <= i < self._list.count()):
            return
        name = self._list.item(i).text().split("  =  ")[0]
        self._win._doc.checkpoint("delete name")
        self._win._doc.workbook.names.remove(name)
        self._win._doc.workbook.invalidate_caches()
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self.refresh()
