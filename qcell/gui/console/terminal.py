"""In-app terminal — a line-oriented passthrough to the system shell.

Runs each command through :class:`qcell.core.shell.ShellSession` (which tracks
cwd across commands) on a background thread so the UI never freezes. Not a full
PTY — interactive/curses programs aren't supported; it's for `ls`, `git`,
`python`, build commands, etc.
"""

from __future__ import annotations

import threading

from .._qtcompat import (
    QDialog,
    QFont,
    QLineEdit,
    QPlainTextEdit,
    QTimer,
    QVBoxLayout,
)
from ...core.shell import ShellSession


class Terminal(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self._session = ShellSession()
        self._result = None
        self._timer = None  # one reused poll timer (not one per command)
        self.setWindowTitle("Terminal")
        self.resize(680, 420)
        self.setModal(False)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        mono = QFont("monospace")
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        self._out = QPlainTextEdit(self)
        self._out.setReadOnly(True)
        self._out.setFont(mono)
        self._out.setStyleSheet("background:#0c1014; color:#c8e0c8;")
        self._out.setPlainText(f"qcell terminal — system shell passthrough\n{self._session.prompt()}")
        layout.addWidget(self._out)
        self._in = QLineEdit(self)
        self._in.setFont(mono)
        self._in.returnPressed.connect(self._run)
        layout.addWidget(self._in)

    def _append(self, text: str) -> None:
        self._out.appendPlainText(text)

    def _run(self) -> None:
        cmd = self._in.text().strip()
        self._in.clear()
        self._append(self._session.prompt() + cmd)
        if not cmd:
            self._append(self._session.prompt())
            return
        self._in.setEnabled(False)
        self._result = None
        threading.Thread(target=self._work, args=(cmd,), daemon=True).start()
        if self._timer is None:  # reuse a single timer across commands
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._poll)
        self._timer.start(40)

    def _work(self, cmd: str) -> None:
        self._result = self._session.execute(cmd)

    def _poll(self) -> None:
        if self._result is None:
            return
        self._timer.stop()
        res, self._result = self._result, None
        if res.stdout:
            self._append(res.stdout.rstrip("\n"))
        if res.stderr:
            self._append(res.stderr.rstrip("\n"))
        self._append(self._session.prompt())
        self._in.setEnabled(True)
        self._in.setFocus()
