"""Visual theme selector — pick a theme with a live preview.

Each row is painted in that theme's own colours so you can see it before
committing. Selecting a row applies it live; OK keeps it, Cancel reverts to the
theme that was active when the dialog opened.
"""

from __future__ import annotations

from .._qtcompat import (
    QColor,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)
from ..theming import PRESETS, theme_for

_NICE = {
    "galaxy": "Galaxy (default)",
    "dark_one": "Dark One",
    "dracula": "Dracula",
    "tokyo_night": "Tokyo Night",
    "gruvbox_dark": "Gruvbox Dark",
    "monokai": "Monokai",
    "nord": "Nord",
    "solarized": "Solarized",
    "crt_green": "CRT — green",
    "crt_amber": "CRT — amber",
    "high_contrast": "High contrast",
    "light": "Light",
}


class ThemeDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Theme")
        self.resize(300, 400)
        self._original = getattr(window._settings, "theme", "galaxy")
        self._names = list(PRESETS)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Click a theme to preview it live:", self))
        self._list = QListWidget(self)
        for name in self._names:
            self._list.addItem(_NICE.get(name, name))
            item = self._list.item(self._list.count() - 1)
            t = theme_for(name)
            item.setBackground(QColor(t.bg_primary))
            item.setForeground(QColor(t.fg_primary))
        if self._original in self._names:
            self._list.setCurrentRow(self._names.index(self._original))
        self._list.currentRowChanged.connect(self._preview)
        layout.addWidget(self._list)
        row = QHBoxLayout()
        cancel = QPushButton("Cancel", self)
        cancel.clicked.connect(self._cancel)
        ok = QPushButton("OK", self)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)
        layout.addLayout(row)

    def _preview(self, row: int) -> None:
        if 0 <= row < len(self._names):
            self._win.set_theme(self._names[row])

    def _cancel(self) -> None:
        self._win.set_theme(self._original)
        self.reject()
