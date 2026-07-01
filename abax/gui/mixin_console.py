"""ConsoleMixin — The embedded Python console and system terminal, the code-consent gate, and the default workspace."""

from __future__ import annotations


class ConsoleMixin:
    def _require_code_consent(self, what: str = "This feature") -> bool:
        """One-time consent gate before running untrusted code.

        abax's console, terminal, scripts, and macros execute arbitrary code with
        the user's full privileges — there is no sandbox. Ask once, remember the
        choice in settings, and otherwise abort the action. (A real sandbox is a
        planned follow-up; this is the interim safeguard.)
        """
        if getattr(self._settings, "code_consent", False):
            return True
        from ._qtcompat import QMessageBox

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Run untrusted code?")
        box.setText(f"{what} runs code with your full user privileges — it can "
                    "read and write your files, network, and system.")
        box.setInformativeText(
            "The Python console runs in its own sub-process, so a crash or runaway "
            "there can't take down abax — but this is not a security sandbox. For "
            "stronger isolation, run abax inside a dedicated Python virtual "
            "environment. Only continue if you trust the code you'll run; enabling "
            "this is remembered for future sessions.")
        enable = box.addButton("Enable code execution", QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        if box.clickedButton() is enable:
            self._settings.code_consent = True
            self._set_status("code execution enabled for this profile")
            return True
        self._set_status("code execution stays disabled")
        return False

    def show_terminal(self) -> None:
        if not self._require_code_consent("The system terminal"):
            return
        # Dockable panel. Prefer a true PTY terminal; fall back to the line terminal.
        from ._qtcompat import Qt

        def build():
            try:
                from .console.ptyterminal import PtyView, available

                if available():
                    view = PtyView(self)
                    view.start()
                    return view
            except Exception:
                pass
            from .console.terminal import Terminal

            return Terminal(self)

        self._show_dock("_terminal_dock", "Terminal", build,
                        Qt.DockWidgetArea.BottomDockWidgetArea)

    def show_pyconsole(self) -> None:
        if not self._require_code_consent("The Python console"):
            return
        from ._qtcompat import Qt
        from .console.pyconsole import PyConsole

        self._show_dock("_pyconsole_dock", "Python console",
                        lambda: PyConsole(self), Qt.DockWidgetArea.BottomDockWidgetArea)

    def open_default_workspace(self) -> None:
        """The everyday layout: spreadsheet upper-left, a floating Calculator, and the
        Python console (lower-left) + Terminal (lower-right) side by side at the bottom."""
        from ._qtcompat import Qt, QTimer

        self.show_pyconsole()       # bottom
        self.show_terminal()        # bottom
        con = getattr(self, "_pyconsole_dock", None)
        term = getattr(self, "_terminal_dock", None)
        if con is not None and term is not None:
            # console on the left, terminal on the right — not tabbed, even split
            self.splitDockWidget(con, term, Qt.Orientation.Horizontal)
            # defer the 50/50 sizing until the docks are actually laid out
            QTimer.singleShot(0, lambda: self.resizeDocks(
                [con, term], [self.width() // 2, self.width() // 2],
                Qt.Orientation.Horizontal))
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.show_calculator()      # floating, not docked
