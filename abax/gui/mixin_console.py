"""ConsoleMixin — The embedded Python console and system terminal, the code-consent gate, and the default workspace."""

from __future__ import annotations


class ConsoleMixin:
    def _require_code_consent(self, what: str = "This feature") -> bool:
        """One-time consent gate before running untrusted code.

        abax's console, terminal, scripts, and macros execute arbitrary code with
        the user's full privileges. The console/script/macro worker gives crash
        and resource isolation, but not a security boundary. Ask once, remember the
        choice in settings, and otherwise abort the action.
        """
        if getattr(self._settings, "code_consent", False):
            return True
        from ._qtcompat import QMessageBox

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Run untrusted code?")
        box.setText(f"{what} runs code with your full user privileges — it can "
                    "read and write your files, network, and system.")
        isolation = getattr(self._settings, "code_isolation", "isolated")
        if isolation == "off":
            detail = ("Your code-isolation setting is OFF: code runs in this "
                      "process with no isolation or limits — a crash can take "
                      "down abax. ")
        elif isolation == "strict":
            detail = ("Your code-isolation setting is STRICT: code runs in an "
                      "OS-confined worker (no network; writes to a scratch dir "
                      "only) and refuses to run if that can't be established. ")
        else:
            detail = ("Your code-isolation setting is ISOLATED: code runs in a "
                      "separate, resource-limited worker, so a crash or runaway "
                      "there can't take down abax — but it is not a security "
                      "sandbox unless you switch to strict mode. ")
        box.setInformativeText(
            detail + "The code still runs with your privileges. For untrusted "
            "code, use strict mode or run abax inside a throwaway VM or container. "
            "Only continue if you trust the code you'll run; enabling this is "
            "remembered for future sessions. (Change the level from the command "
            "palette: 'Cycle code isolation'.)")
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

    _ISOLATION_ORDER = ("off", "restricted", "isolated", "strict")
    _ISOLATION_LABELS = {
        "off": "&Off — in-process (no isolation)",
        "restricted": "&Restricted — AST-allowlisted worker (blocks OS access)",
        "isolated": "&Isolated — worker + resource limits (default)",
        "strict": "&Strict — OS sandbox (no network, scratch-only writes)",
    }

    def _build_isolation_menu(self, menu) -> None:
        """Populate the Tools → Code isolation submenu with three checkable
        levels reflecting (and setting) ``settings.code_isolation``."""
        from ._qtcompat import QAction

        cur = getattr(self._settings, "code_isolation", "isolated")
        self._isolation_actions = {}
        for level in self._ISOLATION_ORDER:
            act = QAction(self._ISOLATION_LABELS[level], self)
            act.setCheckable(True)
            act.setChecked(level == cur)
            act.triggered.connect(lambda _checked=False, lv=level: self.set_code_isolation(lv))
            menu.addAction(act)
            self._isolation_actions[level] = act

    def set_code_isolation(self, level: str) -> None:
        """Set how the console / scripts / macros are isolated:

        * *off* — run in this process: fastest, full access, no crash isolation.
        * *isolated* — out-of-process worker + memory/CPU/process limits (default).
        * *strict* — also OS-confine filesystem + network (Windows AppContainer,
          Linux bubblewrap, macOS sandbox-exec); refuses to run if that
          confinement can't be established here (fail-closed).

        Takes effect for the next console you open and the next macro/script
        you run."""
        from .. import sandbox as _sandbox

        if level not in self._ISOLATION_ORDER:
            level = "isolated"
        self._settings.code_isolation = level
        # Keep the menu's checkmarks in sync (whether triggered from the menu,
        # the palette cycle, or elsewhere).
        for lv, act in getattr(self, "_isolation_actions", {}).items():
            act.setChecked(lv == level)
        # Reset the macro/script worker so the change applies immediately.
        bridge = getattr(self, "_macro_bridge", None)
        if bridge is not None:
            try:
                bridge.close()
            except Exception:
                pass
            self._macro_bridge = None
        if level == "off":
            self._set_status("code isolation: OFF — code runs in-process, no "
                             "worker or limits (not a security boundary)")
        elif level == "isolated":
            self._set_status("code isolation: ISOLATED — out-of-process worker + "
                             "resource limits (crash isolation, not a boundary)")
        else:  # strict
            strat = _sandbox.select_confinement()
            if strat.available():
                self._set_status(f"code isolation: STRICT — {strat.describe()}")
            else:
                self._set_status("code isolation: STRICT — but no OS confinement "
                                 "is available here, so code execution will "
                                 "refuse to run (fail-closed).")

    def cycle_code_isolation(self) -> None:
        """Cycle the code-isolation level off → isolated → strict → off (the
        command-palette entry point; the menu offers the levels directly)."""
        cur = getattr(self._settings, "code_isolation", "isolated")
        order = self._ISOLATION_ORDER
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "isolated"
        self.set_code_isolation(nxt)

    def _selection_env(self) -> "dict[str, str] | None":
        """``os.environ`` overlaid with the ``$ABAX_*`` selection context.

        Mirrors the TUI ``:!`` drop-to-shell so a GUI terminal command can see
        the active cell / selection (`$ABAX_ACTIVE_CELL`, `$ABAX_SELECTION_RANGE`
        / `_JSON` / `_TSV`). Best-effort: returns ``None`` on any failure so the
        terminal still opens. Captured when the terminal starts.
        """
        try:
            from ..core.shellenv import merged_env

            sheet = self._doc.workbook.sheet
            table = self._table
            r = max(0, table.currentRow())
            c = max(0, table.currentColumn())
            ranges = table.selectedRanges()
            if ranges:
                rg = ranges[0]
                r1, c1, r2, c2 = rg.topRow(), rg.leftColumn(), rg.bottomRow(), rg.rightColumn()
            else:
                r1, c1, r2, c2 = r, c, r, c
            return merged_env(None, sheet, r1, c1, r2, c2)
        except Exception:  # noqa: BLE001 — env is optional; never block the terminal
            return None

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
