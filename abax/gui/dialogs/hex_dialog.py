"""Streaming binary / hex file inspector dialog.

A thin Qt front-end over :class:`abax.core.hexview.HexView`. Open a file and
page through its bytes in the classic three-column layout — offset, hex pairs,
ASCII gutter — without ever loading the whole file into memory. Only a
screenful of rows is read per page, so multi-gigabyte files scroll in constant
memory.

Controls: "Open file…" picks a file; Prev / Next page move a screenful at a
time; "Go to offset" jumps to a hex (``0x1F0``) or decimal byte offset. A
status label shows the file size and the current top offset.

The Qt-picker path is kept out of :meth:`load_path` / :meth:`load_bytes` so
tests (and callers) can drive the viewer without a file dialog.
"""

from __future__ import annotations

from .._qtcompat import (
    QDialog,
    QFileDialog,
    QFontDatabase,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)
from ...core.hexview import HexView

_WIDTH = 16  # bytes per row; matches HexView's default.


class HexDialog(QDialog):
    """Page through a file's raw bytes as a hex dump."""

    def __init__(self, window, rows_per_page: int = 32) -> None:
        super().__init__(window)
        self._win = window
        self._view: HexView | None = None
        self._top: int = 0
        self._rows_per_page = max(1, rows_per_page)
        self.setWindowTitle("Hex viewer")
        self.resize(760, 560)
        self._build()
        self._render()

    # ------------------------------------------------------------------ #
    @property
    def _page_bytes(self) -> int:
        return self._rows_per_page * _WIDTH

    def _build(self) -> None:
        root = QVBoxLayout(self)

        # --- top action bar ---
        bar = QHBoxLayout()
        open_btn = QPushButton("Open file…", self)
        open_btn.clicked.connect(self._pick_file)
        bar.addWidget(open_btn)

        self._prev_btn = QPushButton("◀ Prev", self)
        self._prev_btn.clicked.connect(self.prev_page)
        self._next_btn = QPushButton("Next ▶", self)
        self._next_btn.clicked.connect(self.next_page)
        bar.addWidget(self._prev_btn)
        bar.addWidget(self._next_btn)

        bar.addWidget(QLabel("Go to offset:", self))
        self._goto = QLineEdit(self)
        self._goto.setPlaceholderText("0x1F0 or 496")
        self._goto.setMaximumWidth(140)
        self._goto.returnPressed.connect(self._go_to_offset)
        bar.addWidget(self._goto)
        go_btn = QPushButton("Go", self)
        go_btn.clicked.connect(self._go_to_offset)
        bar.addWidget(go_btn)
        bar.addStretch(1)
        root.addLayout(bar)

        # --- hex dump ---
        self._dump = QPlainTextEdit(self)
        self._dump.setReadOnly(True)
        self._dump.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono.setStyleHint(mono.StyleHint.Monospace)
        self._dump.setFont(mono)
        root.addWidget(self._dump, 1)

        # --- status ---
        self._status = QLabel("", self)
        root.addWidget(self._status)

    # ------------------------------------------------------------------ #
    # Loading (Qt-picker-free entry points for callers and tests).
    def load_path(self, path: str) -> None:
        """Open ``path`` as the current view and render from offset 0.

        A missing or zero-byte file leaves the viewer empty and shows a note
        instead of raising.
        """
        try:
            view = HexView(path)
        except OSError as exc:
            self._set_view(None)
            self._status.setText(f"Could not open file: {exc}")
            return
        self._adopt(view, note=f"Opened {path}")

    def load_bytes(self, data: bytes) -> None:
        """Adopt an in-memory ``bytes`` buffer as the current view."""
        self._adopt(HexView.from_bytes(data), note="Loaded in-memory bytes")

    def _adopt(self, view: HexView, *, note: str) -> None:
        self._set_view(view)
        self._top = 0
        if view.size == 0:
            self._status.setText(f"{note} — empty file (0 bytes)")
            self._render()
            return
        self._render()

    def _set_view(self, view: HexView | None) -> None:
        """Install ``view`` as current, closing any previous one first."""
        if self._view is not None and self._view is not view:
            self._view.close()
        self._view = view

    # ------------------------------------------------------------------ #
    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open file for hex view")
        if path:
            self.load_path(path)

    def _last_row_start(self) -> int:
        """Byte offset of the first byte of the final row (a page/row anchor)."""
        if self._view is None or self._view.size == 0:
            return 0
        last = (self._view.size - 1) // _WIDTH * _WIDTH
        return last

    def _clamp_top(self) -> None:
        self._top = max(0, min(self._top, self._last_row_start()))

    def next_page(self) -> None:
        if self._view is None:
            return
        self._top += self._page_bytes
        self._clamp_top()
        self._render()

    def prev_page(self) -> None:
        if self._view is None:
            return
        self._top -= self._page_bytes
        self._clamp_top()
        self._render()

    def _go_to_offset(self) -> None:
        text = self._goto.text().strip()
        if not text:
            return
        try:
            base = 16 if text.lower().startswith("0x") else 10
            offset = int(text, base)
        except ValueError:
            self._status.setText(f"Not a valid offset: {text!r}")
            return
        if offset < 0:
            self._status.setText(f"Not a valid offset: {text!r}")
            return
        # Align down to the start of the row containing the offset.
        self._top = offset - (offset % _WIDTH)
        self._clamp_top()
        self._render()

    # ------------------------------------------------------------------ #
    def _render(self) -> None:
        have = self._view is not None and self._view.size > 0
        self._prev_btn.setEnabled(have)
        self._next_btn.setEnabled(have)
        if self._view is None:
            self._dump.setPlainText("")
            if not self._status.text():
                self._status.setText("No file loaded — click “Open file…”.")
            return
        if self._view.size == 0:
            self._dump.setPlainText("")
            return
        self._clamp_top()
        self._dump.setPlainText(
            self._view.format_rows(self._top, self._rows_per_page, width=_WIDTH)
        )
        end = min(self._top + self._page_bytes, self._view.size)
        self._status.setText(
            f"size {self._view.size} bytes  "
            f"|  showing 0x{self._top:X}–0x{end:X}"
            f"  (top offset 0x{self._top:X} / {self._top})"
        )

    # ------------------------------------------------------------------ #
    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._set_view(None)
        super().closeEvent(event)
