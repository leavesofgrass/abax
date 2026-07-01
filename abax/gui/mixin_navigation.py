"""NavigationMixin — vim-style keyboard navigation in the cell grid.

Keyboard-first: j/k/h/l move the selection, g/G jump top/bottom, / focuses
search. Works alongside the native arrow keys (mouse still supported).
"""

from __future__ import annotations

from ._qtcompat import Qt


class NavigationMixin:
    def move_selection(self, dr: int, dc: int) -> None:
        row = max(0, self._table.currentRow() + dr)
        col = max(0, self._table.currentColumn() + dc)
        row = min(row, self._table.rowCount() - 1)
        col = min(col, self._table.columnCount() - 1)
        self._table.setCurrentCell(row, col)

    def goto_top(self) -> None:
        self._table.setCurrentCell(0, self._table.currentColumn())

    def goto_bottom(self) -> None:
        self._table.setCurrentCell(self._table.rowCount() - 1, self._table.currentColumn())

    def handle_vim_key(self, key: int, text: str) -> bool:
        """Return True if the key was consumed as a navigation command.

        Only active when not editing a cell and vim_mode is on. The host wires
        this from ``keyPressEvent``.
        """
        if not getattr(self._settings, "vim_mode", True):
            return False
        if self._table.state() == self._table.State.EditingState:
            return False
        if text == "j":
            self.move_selection(1, 0)
            return True
        if text == "k":
            self.move_selection(-1, 0)
            return True
        if text == "h":
            self.move_selection(0, -1)
            return True
        if text == "l":
            self.move_selection(0, 1)
            return True
        if text == "G":
            self.goto_bottom()
            return True
        if text == "g":
            self.goto_top()
            return True
        if text == "/":
            self._formula_bar.setFocus()
            return True
        if key == Qt.Key.Key_Escape:
            self._table.setFocus()
            return True
        return False
