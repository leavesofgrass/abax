"""A true colour terminal widget — renders a real PTY via :mod:`abax.core.ptyterm`.

Spawns the shell in a pseudo-terminal (ConPTY on Windows, ``pty`` on POSIX) and
paints the ``pyte`` screen grid cell-by-cell with full SGR styling: 16-colour /
256-colour / true-colour foreground+background, bold, italic, underline, and
reverse-video, plus a block cursor. Key events become xterm byte sequences sent
to the PTY; a ``QTimer`` polls the screen snapshot and repaints on change.

Interactive/full-screen programs (vim, top, less) work. If the PTY backend is
unavailable, callers should fall back to the line-oriented terminal — see
:func:`available`.
"""

from __future__ import annotations

# Paint-heavy widget: geometry/metrics + higher-level classes all come through
# the binding shim, so it runs on PySide6 or PyQt6.
from .._qtcompat import (
    QColor,
    QDialog,
    QFont,
    QFontMetricsF,
    QPainter,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from ...core.format.ansipalette import resolve
from ...core.ptyterm import PtyTerminal, pty_available

_COLS, _ROWS = 100, 30
_FG = (212, 221, 228)
_BG = (12, 16, 20)
_CURSOR = (170, 200, 170, 130)


def available() -> bool:
    return pty_available()


def _seq_for(key, text, ctrl) -> "str | None":
    K = Qt.Key
    table = {
        K.Key_Return: "\r", K.Key_Enter: "\r", K.Key_Backspace: "\x7f",
        K.Key_Tab: "\t", K.Key_Escape: "\x1b",
        K.Key_Up: "\x1b[A", K.Key_Down: "\x1b[B",
        K.Key_Right: "\x1b[C", K.Key_Left: "\x1b[D",
        K.Key_Home: "\x1b[H", K.Key_End: "\x1b[F",
        K.Key_PageUp: "\x1b[5~", K.Key_PageDown: "\x1b[6~",
        K.Key_Delete: "\x1b[3~",
    }
    if key in table:
        return table[key]
    if ctrl and text and text.isalpha():
        return chr(ord(text.upper()) - 64)  # Ctrl+A..Z -> 0x01..0x1a
    if ctrl and key == Qt.Key.Key_C:
        return "\x03"
    return text or None


class PtyView(QWidget):
    """A QWidget that paints a PTY screen with colour + attributes."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self.setFont(font)
        fm = QFontMetricsF(font)
        self._cw = max(1.0, fm.horizontalAdvance("M"))
        self._ch = max(1.0, fm.height())
        self._ascent = fm.ascent()

        self._window = parent
        self._term = PtyTerminal(cols=_COLS, rows=_ROWS)
        self._started = False
        self._cells: list = []
        self._cur = (0, 0)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # A modest minimum (not the full _COLS×_ROWS) so the view can sit in a
        # half-width dock; the PTY reflows to the actual widget size on resize.
        self.setMinimumSize(int(self._cw * 24), int(self._ch * 8))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

    def start(self) -> None:
        if self._started:
            return
        # Export the $ABAX_* selection context to the shell (captured at spawn).
        getter = getattr(self._window, "_selection_env", None)
        if getter is not None:
            env = getter()
            if env is not None:
                self._term.env = env
        self._term.start()           # may raise PtyError
        self._started = True
        self._timer.start(40)
        self._poll()

    def _poll(self) -> None:
        if not self._started:
            return
        cells = self._term.read_cells()
        cur = self._term.cursor()
        if cells != self._cells or cur != self._cur:
            self._cells = cells
            self._cur = cur
            self.update()
        if not self._term.alive:
            self._timer.stop()

    # -- painting -----------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(*_BG))
        f = self.font()
        cw, ch, asc = self._cw, self._ch, self._ascent
        for y, row in enumerate(self._cells):
            ry = y * ch
            for x, cell in enumerate(row):
                data, fg, bg, bold, italics, underscore, reverse = cell
                fgc = resolve(fg, _FG, bold)
                bgc = resolve(bg, _BG)
                if reverse:
                    fgc, bgc = bgc, fgc
                rx = x * cw
                if bgc != _BG:
                    p.fillRect(QRectF(rx, ry, cw + 0.6, ch), QColor(*bgc))
                if data and data != " ":
                    f.setBold(bool(bold))
                    f.setItalic(bool(italics))
                    f.setUnderline(bool(underscore))
                    p.setFont(f)
                    p.setPen(QColor(*fgc))
                    p.drawText(QPointF(rx, ry + asc), data)
        cy, cx = self._cur
        p.fillRect(QRectF(cx * cw, cy * ch, cw, ch), QColor(*_CURSOR))
        p.end()

    # -- input --------------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802
        if not self._started:
            return
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        seq = _seq_for(event.key(), event.text(), ctrl)
        if seq:
            try:
                self._term.write(seq)
            except Exception:
                pass

    def resizeEvent(self, _event) -> None:  # noqa: N802
        cols = max(20, int(self.width() / self._cw))
        rows = max(4, int(self.height() / self._ch))
        if self._started and (cols, rows) != (self._term.cols, self._term.rows):
            try:
                self._term.resize(cols, rows)
            except Exception:
                pass

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        try:
            self._term.close()
        except Exception:
            pass
        super().closeEvent(event)


class PtyTerminalDialog(QDialog):
    """Window hosting a :class:`PtyView` colour terminal."""

    def __init__(self, window, parent=None) -> None:
        super().__init__(parent or window)
        self.setWindowTitle("Terminal (PTY)")
        self.resize(840, 500)
        self.setModal(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self.view = PtyView(self)
        layout.addWidget(self.view)
        self.view.start()
        self.view.setFocus()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.view.close()
        super().closeEvent(event)
