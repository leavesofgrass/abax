"""A plain algebraic (infix) calculator faceplate — a button grid + display.

Drives :class:`qcell.core.calc.algebraic.AlgebraicCalc`. Unlike the HP RPN faceplates
you build an expression and press ``=``. Exposes ``value()``/``set_value()`` so the
calculator panel can move numbers to/from the active spreadsheet cell.
"""

from __future__ import annotations

from ._qtcompat import QGridLayout, QLabel, QPushButton, Qt, QVBoxLayout, QWidget
from ..core.calc.algebraic import AlgebraicCalc

# (label, action) — action is a token to input, or a "@name" command.
_KEYS = [
    [("Deg", "@deg"), ("C", "@clear"), ("DEL", "@bksp"), ("(", "("), (")", ")")],
    [("sin", "sin("), ("cos", "cos("), ("tan", "tan("), ("^", "^"), ("/", "/")],
    [("7", "7"), ("8", "8"), ("9", "9"), ("ln", "ln("), ("*", "*")],
    [("4", "4"), ("5", "5"), ("6", "6"), ("log", "log("), ("-", "-")],
    [("1", "1"), ("2", "2"), ("3", "3"), ("sqrt", "sqrt("), ("+", "+")],
    [("0", "0"), (".", "."), ("pi", "pi"), ("Ans", "Ans"), ("=", "@equals")],
    [("M+", "@madd"), ("MR", "@mrecall"), ("MC", "@mclear"), ("e", "e"), ("%", "%")],
]


class AlgebraicFaceplate(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._calc = AlgebraicCalc()
        s = self._host_settings()
        if s is not None:                       # restore the saved Deg/Rad mode
            self._calc.set_degrees(bool(getattr(s, "calc_degrees", False)))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        self._display = QLabel("0", self)
        self._display.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._display.setMinimumHeight(46)
        self._display.setStyleSheet(
            "QLabel { background:#0c1410; color:#7bf2a8; font-family:Consolas,monospace;"
            " font-size:20px; padding:4px 10px; border:1px solid #2a3a30; }")
        layout.addWidget(self._display)
        grid = QGridLayout()
        grid.setSpacing(3)
        for r, row in enumerate(_KEYS):
            for c, (label, action) in enumerate(row):
                btn = QPushButton(label, self)
                btn.setMinimumSize(42, 34)
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn.clicked.connect(lambda _=False, a=action: self._do(a))
                grid.addWidget(btn, r, c)
        layout.addLayout(grid)
        self._refresh()

    # -- interop -----------------------------------------------------------

    def _host_settings(self):
        """The window's Settings, reached via the owning calculator panel (or None)."""
        win = getattr(self.parent(), "_window", None)
        return getattr(win, "_settings", None)

    def value(self) -> float:
        # The currently shown/typed value (evaluating an un-equalled expression),
        # so "Send to cell" captures what's on screen — not just the last Ans.
        try:
            return self._calc._current_value()
        except Exception:
            return self._calc.ans

    def set_value(self, v: float) -> None:
        self._calc.clear()
        self._calc.input(repr(v))
        self._refresh()

    # -- input -------------------------------------------------------------

    def _do(self, action: str) -> None:
        if action == "@clear":
            self._calc.clear()
        elif action == "@bksp":
            self._calc.backspace()
        elif action == "@equals":
            self._calc.equals()
        elif action == "@madd":
            self._calc.memory_add()
        elif action == "@mrecall":
            self._calc.memory_recall()
        elif action == "@mclear":
            self._calc.memory_clear()
        elif action == "@deg":
            self._calc.set_degrees(not self._calc.degrees)
            s = self._host_settings()
            if s is not None:                   # remember Deg/Rad across sessions
                s.calc_degrees = self._calc.degrees
        else:
            self._calc.input(action)
        self._refresh()

    def _refresh(self) -> None:
        text = self._calc.display or "0"
        mode = "DEG" if self._calc.degrees else "RAD"
        self._display.setText(f"{text}    {mode}")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        text = event.text()
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Equal):
            self._do("@equals")
        elif key == Qt.Key.Key_Backspace:
            self._do("@bksp")
        elif key == Qt.Key.Key_Escape:
            self._do("@clear")
        elif text and text in "0123456789.+-*/^()%":
            self._do(text)
        else:
            super().keyPressEvent(event)
