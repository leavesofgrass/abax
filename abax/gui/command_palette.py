"""A rofi/dmenu-style command palette.

A search box with fuzzy autocomplete over a filtered list of commands, in a
clean floating panel. Keyboard-driven: type to filter, Up/Down (or PageUp/Down)
to move, Enter to run the highlighted command, Esc to cancel. Replaces the old
single-combobox prompt.
"""

from __future__ import annotations

from ._qtcompat import (
    QDialog,
    QEvent,
    QLineEdit,
    QListWidget,
    Qt,
    QVBoxLayout,
)

_WORD_STARTS = " /-—…(→.:"


def fuzzy_score(query: str, text: str) -> float | None:
    """Case-insensitive subsequence match.

    Returns a score (higher is better) when every character of ``query`` appears
    in ``text`` in order, else ``None``. Contiguous runs and word-boundary hits
    score higher so, e.g., ``pgb`` ranks ``Pivot / group-by`` above a scattered
    match.
    """
    if not query:
        return 0.0
    t = text.lower()
    score = 0.0
    ti = 0
    last = -2
    for qc in query.lower():
        idx = t.find(qc, ti)
        if idx < 0:
            return None
        if idx == last + 1:
            score += 4.0                       # contiguous with previous hit
        if idx == 0 or t[idx - 1] in _WORD_STARTS:
            score += 6.0                       # start of a word
        score -= (idx - ti) * 0.5              # penalise gaps
        last = idx
        ti = idx + 1
    score -= len(t) * 0.02                     # mild nudge toward shorter labels
    return score


class CommandPalette(QDialog):
    """Modal fuzzy-filter palette. Build with the ``{label: callable}`` mapping;
    after ``exec()`` returns truthy, ``chosen()`` is the selected callable."""

    def __init__(self, parent, actions: dict, placeholder: str = "Type a command…") -> None:
        super().__init__(parent)
        self.setWindowTitle("Command palette")
        self._placeholder = placeholder
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setModal(True)
        self._actions = list(actions.items())   # preserve insertion (grouped) order
        self._filtered: list = []
        self._chosen = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        self._input = QLineEdit(self)
        self._input.setPlaceholderText(self._placeholder)
        self._input.setClearButtonEnabled(True)
        lay.addWidget(self._input)

        self._list = QListWidget(self)
        self._list.setUniformItemSizes(True)
        lay.addWidget(self._list)

        # palette() roles keep the frame/selection theme-aware across presets.
        self.setStyleSheet(
            "CommandPalette { border: 1px solid palette(mid); border-radius: 8px; }"
            "QLineEdit { padding: 7px 9px; font-size: 14px; }"
            "QListWidget { border: none; font-size: 13px; }"
            "QListWidget::item { padding: 4px 6px; }"
        )
        self.resize(580, 440)

        self._input.textChanged.connect(self._refilter)
        self._list.itemDoubleClicked.connect(lambda *_: self._accept_current())
        self._input.installEventFilter(self)

        self._refilter("")
        self._input.setFocus()

    # --- filtering -------------------------------------------------------
    def _refilter(self, text: str) -> None:
        query = text.strip()
        if not query:
            self._filtered = list(self._actions)
        else:
            scored = []
            for label, fn in self._actions:
                s = fuzzy_score(query, label)
                if s is not None:
                    scored.append((s, label, fn))
            scored.sort(key=lambda t: (-t[0], t[1]))
            self._filtered = [(label, fn) for _, label, fn in scored]
        self._list.clear()
        for label, _ in self._filtered:
            self._list.addItem(label)
        if self._filtered:
            self._list.setCurrentRow(0)

    # --- keyboard --------------------------------------------------------
    def eventFilter(self, obj, event):
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self._move(1); return True
            if key == Qt.Key.Key_Up:
                self._move(-1); return True
            if key == Qt.Key.Key_PageDown:
                self._move(10); return True
            if key == Qt.Key.Key_PageUp:
                self._move(-10); return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._accept_current(); return True
        return super().eventFilter(obj, event)

    def _move(self, delta: int) -> None:
        n = self._list.count()
        if not n:
            return
        row = max(0, min(n - 1, self._list.currentRow() + delta))
        self._list.setCurrentRow(row)

    def _accept_current(self) -> None:
        row = self._list.currentRow()
        if 0 <= row < len(self._filtered):
            self._chosen = self._filtered[row][1]
        self.accept()

    def chosen(self):
        return self._chosen

    # --- placement: float near the top-centre of the parent window -------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        p = self.parentWidget()
        if p is not None:
            g = p.geometry()
            x = g.x() + (g.width() - self.width()) // 2
            y = g.y() + max(40, g.height() // 8)
            self.move(x, y)
