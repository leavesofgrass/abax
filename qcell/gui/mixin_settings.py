"""SettingsMixin — theme switching, the command palette, and autosave.

The command palette (Ctrl+Shift+P) is mandatory per spec §9: every action is
reachable from it.
"""

from __future__ import annotations

from .theming import apply_theme, theme_for
from ..core.reference import to_a1


class SettingsMixin:
    def apply_current_theme(self) -> None:
        from ._qtcompat import QApplication

        name = getattr(self._settings, "theme", "obsidian")
        theme = theme_for(name)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, name, theme.tokens(), self._ui_font_qss() + self._zoom_qss())
        self._theme = theme  # custom-painted surfaces read this
        self._update_status_cluster()

    def _ui_font_qss(self) -> str:
        """Stylesheet layer forcing the dyslexia font on text-heavy widgets (cells,
        console, terminal, lists) when enabled — applied over the theme.

        A stylesheet beats ``setFont()``, so this reaches widgets that set their own
        font (the terminal/console). ``QLabel`` and the QPainter-drawn calculator
        faceplates are deliberately excluded, so the LCD/keypad keep their display
        fonts.
        """
        fam = getattr(self, "_ui_font_family", "")
        if not fam:
            return ""
        return ("\nQAbstractItemView, QHeaderView, QTableView, QTableWidget, "
                "QListView, QTreeView, QPlainTextEdit, QTextEdit "
                f'{{ font-family: "{fam}"; }}\n')

    # --- UI zoom (scales the base font via a QSS layer; persisted in settings) --

    def _zoom_qss(self) -> str:
        """Stylesheet layer scaling the base font size by ``settings.zoom``. The
        theme .qss sets ``font-size`` on the base selector, so zoom must go through
        the stylesheet (a ``setFont`` would be overridden)."""
        z = float(getattr(self._settings, "zoom", 1.0) or 1.0)
        if abs(z - 1.0) < 1e-6:
            return ""
        return f"\n* {{ font-size: {max(6, round(13 * z))}px; }}\n"

    def _set_zoom(self, z: float) -> None:
        z = max(0.5, min(3.0, round(z, 1)))
        self._settings.zoom = z
        self.apply_current_theme()
        self._set_status(f"zoom {int(z * 100)}%")

    def zoom_in(self) -> None:
        self._set_zoom(float(getattr(self._settings, "zoom", 1.0) or 1.0) + 0.1)

    def zoom_out(self) -> None:
        self._set_zoom(float(getattr(self._settings, "zoom", 1.0) or 1.0) - 0.1)

    def reset_zoom(self) -> None:
        self._set_zoom(1.0)

    def choose_theme(self) -> None:
        from .dialogs.theme_dialog import ThemeDialog

        ThemeDialog(self).exec()

    def set_theme(self, name: str) -> None:
        self._settings.theme = name
        self.apply_current_theme()
        self._set_status(f"theme: {name}")

    def toggle_vim_mode(self) -> None:
        self._settings.vim_mode = not getattr(self._settings, "vim_mode", True)
        self._set_status(f"vim mode: {'on' if self._settings.vim_mode else 'off'}")
        self._update_status_cluster()

    def _shortcut_actions(self) -> dict:
        """A ``{"Menu > Action    ·    Shortcut": action.trigger}`` mapping over
        every menu action that has a keyboard shortcut — powers the searchable
        shortcuts dialog (which also launches the action)."""
        out: dict = {}

        def walk(menu, prefix: str) -> None:
            for act in menu.actions():
                sub = act.menu()
                if sub is not None:
                    walk(sub, f"{prefix}{act.text().replace('&', '')} › ")
                    continue
                sc = act.shortcut().toString()
                if sc and act.text():
                    out[f"{prefix}{act.text().replace('&', '')}    ·    {sc}"] = act.trigger

        for menu_action in self.menuBar().actions():
            menu = menu_action.menu()
            if menu is not None:
                walk(menu, f"{menu_action.text().replace('&', '')} › ")
        return out

    def show_shortcuts(self) -> None:
        """A rofi/dmenu-style searchable list of keyboard shortcuts (Help, F1).

        Type to fuzzy-filter by action name or key; Enter runs the highlighted
        action. Reuses the command palette, so it shares its clean rendering."""
        from .command_palette import CommandPalette

        dlg = CommandPalette(self, self._shortcut_actions(),
                             placeholder="Filter shortcuts…")
        dlg.setWindowTitle("Keyboard shortcuts")
        if dlg.exec() and dlg.chosen() is not None:
            dlg.chosen()()

    def show_about(self) -> None:
        from ._qtcompat import QMessageBox
        from .. import __version__

        QMessageBox.about(
            self,
            "About qcell",
            f"<b>qcell {__version__}</b><br>"
            "A keyboard-first statistics and data-science workstation.<br><br>"
            "A scriptable spreadsheet with ~150 formula functions (including "
            "statistical distributions), built-in analysis, pivot/recode, "
            "graphing, and a pandas hand-off — over CSV, Excel, Parquet, SQLite, "
            "JSON, R, and more.<br><br>"
            "Includes built-in calculators — RPN (programmer, scientific, "
            "financial), graphing, and algebraic — that exchange values with "
            "the grid.",
        )

    def show_command_palette(self) -> None:
        from .command_palette import CommandPalette

        dlg = CommandPalette(self, self._palette_actions())
        # Run the chosen command only after the palette closes, so any dialog it
        # opens doesn't fight the palette for focus.
        if dlg.exec() and dlg.chosen() is not None:
            dlg.chosen()()

    def _palette_actions(self) -> dict:
        recording = getattr(self, "_recorder", None) and self._recorder.recording
        actions = {
            "New": self.new_document,
            "Open…": lambda: self.open_document(None),
            "Import large CSV…": self.import_large_csv,
            "Save": lambda: self.save_document(None),
            "Save As…": self.save_document_as,
            "Choose theme…": self.choose_theme,
            "Toggle vim mode": self.toggle_vim_mode,
            "Recalculate": self._recalculate,
            "Find / Replace…": self.show_find_replace,
            "Show formula precedents": self.show_precedents,
            "Statistics / analysis…": self.show_stats_tool,
            "Open selection in pandas…": self.show_dataframe,
            "Recode / clean column…": self.show_recode,
            "Pivot / group-by…": self.show_pivot,
            "New sheet": self.insert_sheet,
            "Duplicate sheet": self.duplicate_sheet,
            "Delete sheet": self.delete_sheet,
            "Rename sheet…": self.rename_sheet,
            "Append row (end)": self.append_row,
            "Append column (end)": self.append_column,
            "Function browser…": self.show_formula_browser,
            "Show/hide calculator": self.toggle_calculator,
            "Get cell value → calculator": self.cell_to_calc,
            "Send calculator value → cell": self.calc_to_cells,
            "Terminal…": self.show_terminal,
            "Matrix tool…": self.show_matrix_tool,
            "Python console…": self.show_pyconsole,
            "Graph…": self.show_graph,
            "Equation editor…": self.show_equation,
            "Clipboard history…": self.show_clipboard,
            "Manage clipboard…": self.manage_clipboard,
            "Toggle OpenDyslexic font": self.toggle_dyslexic_font,
            "Conditional format…": self.add_conditional_format,
            "Clear conditional formats": self.clear_conditional_formats,
            "Fill series": self._fill_series_selection,
            "Sort ascending": lambda: self._sort_selection(False),
            "Sort descending": lambda: self._sort_selection(True),
            "Copy selection as Markdown": self._copy_as_markdown,
            ("Stop recording" if recording else "Start recording"): self._toggle_recording,
            "Start relative recording": self._start_relative_recording,
            "Save recorded macro…": self._save_recording,
            "Load macro / UDF file…": self.load_macros,
            "Run Python script…": self.run_script,
            "Replay recording at cursor": self._replay_recording,
            "Quit": self.close,
        }
        registry = getattr(self, "_macro_registry", None)
        if registry:
            for name in sorted(registry.macros):
                actions[f"Macro: {name}"] = lambda n=name: self._run_macro(n)
        return actions

    def _run_macro(self, name: str) -> None:
        from ._qtcompat import QMessageBox
        from ..macros import MacroError, run_macro

        try:
            ctx = run_macro(self._macro_registry, name, self._doc.workbook, cursor=self._current_cell())
        except MacroError as exc:
            QMessageBox.critical(self, "Macro failed", str(exc))
            return
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status(f"ran macro {name}" + (f" — {ctx.messages[-1]}" if ctx.messages else ""))

    def _current_cell(self) -> tuple[int, int]:
        row = max(0, self._table.currentRow())
        col = max(0, self._table.currentColumn())
        return row, col

    def _recalculate(self) -> None:
        self._doc.workbook.recalculate()
        self.refresh_table()
        self._set_status("recalculated")

    # --- find / replace, conditional format, function browser ------------

    def show_find_replace(self) -> None:
        from .dialogs.find_dialog import FindReplaceDialog

        if getattr(self, "_find_dialog", None) is None:
            self._find_dialog = FindReplaceDialog(self)
        self._find_dialog.show()
        self._find_dialog.raise_()
        self._find_dialog._find.setFocus()

    def add_conditional_format(self) -> None:
        from .dialogs.condformat_dialog import CondFormatDialog

        CondFormatDialog(self).exec()

    def clear_conditional_formats(self) -> None:
        self._doc.workbook.sheet.cond_rules.clear()
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status("cleared conditional formats")

    def show_formula_browser(self) -> None:
        from .dialogs.formula_browser import FormulaBrowser

        if getattr(self, "_browser_dialog", None) is None:
            self._browser_dialog = FormulaBrowser(self)
        self._browser_dialog.show()
        self._browser_dialog.raise_()

    # --- RPN calculator, clipboard manager, dyslexia font ----------------

    def _paste_history_text(self, text: str) -> None:
        """Paste a clipboard-history fragment (TSV) at the cursor."""
        from ..core.fill import clip_from_tsv, paste_clip

        row = max(0, self._table.currentRow())
        col = max(0, self._table.currentColumn())
        clip = clip_from_tsv(text, (row, col))
        paste_clip(self._doc.workbook.sheet, clip, (row, col),
                   mode="absolute", on_set=self._record)
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status("pasted from clipboard history")

    def _clipboard_actions(self) -> dict:
        """``{label: paste-callable}`` over the clipboard history, newest/pinned
        first — the data behind the searchable clipboard palette."""
        mgr = getattr(self, "_clipboard", None)
        entries = mgr.entries() if mgr is not None else []
        actions = {}
        for i, e in enumerate(entries):
            mark = "📌 " if e.pinned else ""
            actions[f"{i + 1}. {mark}{e.label}"] = (
                lambda t=e.text: self._paste_history_text(t))
        return actions

    def show_clipboard(self) -> None:
        """Searchable rofi/dmenu-style clipboard history — type to filter, Enter
        pastes the chosen entry at the cursor. (Pin/remove/clear live in the
        management dialog, `manage_clipboard`.)"""
        from .command_palette import CommandPalette

        actions = self._clipboard_actions()
        if not actions:
            self._set_status("clipboard history is empty")
            return
        dlg = CommandPalette(self, actions, placeholder="Filter clipboard history…")
        dlg.setWindowTitle("Clipboard history")
        if dlg.exec() and dlg.chosen() is not None:
            dlg.chosen()()

    def manage_clipboard(self) -> None:
        """The full clipboard dialog: pin, remove, clear, copy-back."""
        from .dialogs.clipboard_dialog import ClipboardDialog

        if getattr(self, "_clip_dialog", None) is None:
            self._clip_dialog = ClipboardDialog(self)
        self._clip_dialog._reload()
        self._clip_dialog.show()
        self._clip_dialog.raise_()

    def _calculator_window(self):
        """The floating calculator window (created once)."""
        win = getattr(self, "_calc_window", None)
        if win is None:
            from ._qtcompat import QDialog, QVBoxLayout
            from .calc.calculator_panel import CalculatorPanel

            win = QDialog(self)
            win.setWindowTitle("Calculator")
            win.setModal(False)
            lay = QVBoxLayout(win)
            lay.setContentsMargins(0, 0, 0, 0)
            panel = CalculatorPanel(self)
            lay.addWidget(panel)
            win._panel = panel
            win.resize(380, 660)
            self._calc_window = win
        return win

    def show_calculator(self) -> None:
        win = self._calculator_window()
        win.show()
        win.raise_()
        win.activateWindow()
        if getattr(win._panel, "_widget", None) is not None:
            win._panel._widget.setFocus()   # so the keyboard drives the calculator

    def toggle_calculator(self) -> None:
        """Pop the floating calculator in or out (Ctrl+K / menu)."""
        win = self._calculator_window()
        if win.isVisible():
            win.hide()
        else:
            self.show_calculator()

    def _refresh_calculator(self) -> None:
        """Rebuild the calculator's current faceplate (e.g. after new HP art)."""
        win = getattr(self, "_calc_window", None)
        if win is not None and getattr(win, "_panel", None) is not None:
            win._panel._rebuild()

    # -- calculator <-> cell value bridge ---------------------------------
    # One implementation behind both the panel buttons and the menu shortcuts.

    def _calc_panel(self):
        win = getattr(self, "_calc_window", None)
        return getattr(win, "_panel", None) if win is not None else None

    def calc_to_cells(self) -> None:
        """Write the calculator's current value into every selected cell (undoable)."""
        panel = self._calc_panel()
        if panel is None:
            self._set_status("calculator isn't open — press Ctrl+K")
            return
        text = panel.current_text()
        if text is None:
            self._set_status("the calculator has no numeric value")
            return
        from ..core.reference import to_a1

        r1, c1, r2, c2 = self._selected_bounds()
        self._doc.checkpoint("calculator → cell")
        sheet = self._doc.workbook.sheet
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                sheet.set_cell(r, c, text)
                self._record(to_a1(r, c), text)
        self._doc.mark_dirty()
        self.refresh_table()
        # Re-anchor the target as the current cell and scroll it into view: the
        # written value stays visible even if the floating calculator overlaps the
        # grid, and the next send has a valid anchor (guards a "second send did
        # nothing" report where the current cell/selection had gone stale).
        if r1 == r2 and c1 == c2:
            self._table.setCurrentCell(r1, c1)
        self._table.scrollTo(self._model.index(r1, c1))
        count = (r2 - r1 + 1) * (c2 - c1 + 1)
        self._set_status(f"wrote {text} to {to_a1(r1, c1)}"
                         + (f" +{count - 1} more cell(s)" if count > 1 else ""))

    def cell_to_calc(self) -> None:
        """Load the active cell's numeric value into the calculator."""
        self.show_calculator()   # make sure it's visible first
        panel = self._calc_panel()
        if panel is None:
            return
        table = self._table
        item = table.item(max(0, table.currentRow()), max(0, table.currentColumn()))
        try:
            v = float(item.text()) if item is not None else None
        except (TypeError, ValueError):
            v = None
        if v is None:
            self._set_status("the active cell isn't a number")
            return
        panel.load_value(v)
        self._set_status(f"loaded {item.text()} into the calculator")

    # legacy name kept for any external callers
    show_faceplate = toggle_calculator

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

    def _show_dock(self, attr: str, title: str, build_content, area):
        """Create (once) a movable/floatable QDockWidget panel and show it."""
        from ._qtcompat import QDockWidget, Qt

        dock = getattr(self, attr, None)
        if dock is None:
            dock = QDockWidget(title, self)
            dock.setObjectName(title.replace(" ", "_"))
            dock.setWidget(build_content())
            dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
            dock.setFeatures(
                QDockWidget.DockWidgetFeature.DockWidgetMovable
                | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                | QDockWidget.DockWidgetFeature.DockWidgetClosable)
            self.addDockWidget(area, dock)
            setattr(self, attr, dock)
        dock.show()
        dock.raise_()
        return dock

    def _require_code_consent(self, what: str = "This feature") -> bool:
        """One-time consent gate before running untrusted code.

        qcell's console, terminal, scripts, and macros execute arbitrary code with
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
            "there can't take down qcell — but this is not a security sandbox. For "
            "stronger isolation, run qcell inside a dedicated Python virtual "
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

    def show_matrix_tool(self) -> None:
        from .dialogs.matrix_dialog import MatrixDialog

        MatrixDialog(self).exec()

    def show_solver(self) -> None:
        from .dialogs.solver_dialog import SolverDialog

        SolverDialog(self).exec()

    def show_signal_tool(self) -> None:
        from .dialogs.signal_dialog import SignalDialog

        SignalDialog(self).exec()

    def show_ode_solver(self) -> None:
        from .dialogs.ode_dialog import ODEDialog

        ODEDialog(self).exec()

    def show_stats_tool(self) -> None:
        from .dialogs.stats_dialog import StatsDialog

        StatsDialog(self).show()

    def show_dataframe(self) -> None:
        from .dialogs.dataframe_dialog import DataFrameDialog

        DataFrameDialog(self).show()

    def toggle_toolbar(self) -> None:
        tb = getattr(self, "_toolbar", None)
        if tb is None:
            return
        visible = not tb.isVisible()
        tb.setVisible(visible)
        self._settings.show_toolbar = visible
        self._set_status(f"toolbar {'shown' if visible else 'hidden'}")

    def show_recode(self) -> None:
        from .dialogs.recode_dialog import RecodeDialog

        RecodeDialog(self).exec()

    def show_pivot(self) -> None:
        from .dialogs.pivot_dialog import PivotDialog

        PivotDialog(self).exec()

    def show_ml_tool(self) -> None:
        from .dialogs.ml_dialog import MLDialog

        MLDialog(self).exec()

    def set_faceplate_folder(self) -> None:
        from ._qtcompat import QFileDialog

        start = getattr(self._settings, "faceplate_assets_dir", "") or ""
        chosen = QFileDialog.getExistingDirectory(
            self, "Select faceplate image folder (e.g. qv assets/voyager)", start)
        if not chosen:
            return
        self._settings.faceplate_assets_dir = chosen
        from .. import _runtime as rt
        from ..settings import save_settings

        save_settings(self._settings, rt.CONFIG_DIR / "settings.json")
        # rebuild an open faceplate so the new art takes effect immediately
        self._refresh_calculator()
        self._set_status(f"faceplate folder: {chosen}")

    def show_graph(self) -> None:
        from .dialogs.graph_dialog import GraphDialog

        if getattr(self, "_graph_dialog", None) is None:
            self._graph_dialog = GraphDialog(self)
        self._graph_dialog.show()
        self._graph_dialog.raise_()

    def show_equation(self) -> None:
        from .dialogs.equation_dialog import EquationDialog

        if getattr(self, "_eq_dialog", None) is None:
            self._eq_dialog = EquationDialog(self)
        self._eq_dialog.show()
        self._eq_dialog.raise_()

    def set_number_format(self, spec: str) -> None:
        r1, c1, r2, c2 = self._selected_bounds()
        sheet = self._doc.workbook.sheet
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if spec == "general":
                    sheet.cell_formats.pop((r, c), None)
                else:
                    sheet.cell_formats[(r, c)] = spec
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status(f"number format: {spec}")

    def show_pyconsole(self) -> None:
        if not self._require_code_consent("The Python console"):
            return
        from ._qtcompat import Qt
        from .console.pyconsole import PyConsole

        self._show_dock("_pyconsole_dock", "Python console",
                        lambda: PyConsole(self), Qt.DockWidgetArea.BottomDockWidgetArea)

    def apply_dyslexic_font(self, on: bool, fetch: bool = True) -> None:
        from ._qtcompat import QApplication, QFont, QFontDatabase
        from ..core import fonts as fontmod

        app = QApplication.instance()
        if not on:
            self._ui_font_family = ""
            if app is not None:
                app.setFont(QFont())
            self._settings.dyslexic_font = False
            self.apply_current_theme()           # drop the font layer from the QSS
            if getattr(self, "_model", None) is not None:
                self.refresh_table()             # re-query cell FontRole
            self._set_status("default font")
            return
        paths = fontmod.fetched_paths()
        if not paths and fetch:
            self._set_status("fetching OpenDyslexic…")
            paths = fontmod.fetch()
        if not paths:
            self._set_status("OpenDyslexic unavailable (offline?)")
            return
        family = None
        for p in paths:
            fid = QFontDatabase.addApplicationFont(str(p))
            fams = QFontDatabase.applicationFontFamilies(fid)
            if fams:
                family = fams[0]
        if family and app is not None:
            app.setFont(QFont(family, 11))          # menus, dialogs, buttons, labels
            self._ui_font_family = family
            self._settings.dyslexic_font = True
            self.apply_current_theme()              # + console, terminal, lists
            if getattr(self, "_model", None) is not None:
                self.refresh_table()                # cells pick up the family via FontRole
            self._set_status(f"font: {family} (applied across the UI)")

    def toggle_dyslexic_font(self) -> None:
        self.apply_dyslexic_font(not getattr(self._settings, "dyslexic_font", False))

    # --- grid operations (gnumeric-style) --------------------------------

    def _fill_series_selection(self) -> None:
        from ..core.fill import fill_series

        fill_series(self._doc.workbook.sheet, self._selected_bounds(), on_set=self._record)
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status("filled series")

    def _sort_selection(self, descending: bool) -> None:
        from ..core.fill import sort_region

        sort_region(
            self._doc.workbook.sheet, self._selected_bounds(),
            descending=descending, on_set=self._record,
        )
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status("sorted " + ("descending" if descending else "ascending"))

    def _copy_as_markdown(self) -> None:
        from ._qtcompat import QApplication
        from ..core.fill import copy_region
        from ..core.io.markdown_io import to_markdown
        from ..core.sheet import Sheet

        clip = copy_region(self._doc.workbook.sheet, self._selected_bounds())
        tmp = Sheet()
        for i, row in enumerate(clip.grid):
            for j, raw in enumerate(row):
                if raw != "":
                    tmp.set_cell(i, j, raw)
        md = to_markdown(tmp)
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(md)
        if getattr(self, "_clipboard", None) is not None:
            self._clipboard.add(md, label="Markdown table")
        self._set_status("copied selection as Markdown")

    # --- macro recording --------------------------------------------------

    def _toggle_recording(self) -> None:
        on = self._recorder.toggle()
        self._update_title()
        self._set_status(
            "● recording — edit cells, then Save recorded macro"
            if on
            else f"stopped — recorded {self._recorder.count} action(s)"
        )

    def _start_relative_recording(self) -> None:
        self._recorder.start(relative=True)
        self._update_title()
        self._set_status("● recording (relative) — replays relative to the active cell")

    def load_macros(self) -> None:
        """Load a macro/UDF .py file into the registry so it's immediately runnable."""
        if not self._require_code_consent("Loading a macro / UDF file"):
            return
        from ._qtcompat import QFileDialog, QMessageBox

        path, _ = QFileDialog.getOpenFileName(
            self, "Load macro / UDF file", "", "Python (*.py);;All files (*)")
        if not path:
            return
        from ..macros import MacroError, load_macro_file

        try:
            load_macro_file(path, self._macro_registry)
        except (MacroError, OSError, SyntaxError) as exc:
            QMessageBox.critical(self, "Load macros", str(exc))
            return
        rebuild = getattr(self, "_rebuild_macros_menu", None)
        if rebuild is not None:
            rebuild()
        self._set_status(f"loaded macros from {path}")

    def run_script(self) -> None:
        """Run an arbitrary Python script against the workbook (no sandbox)."""
        if not self._require_code_consent("Running a Python script"):
            return
        from ._qtcompat import QFileDialog, QMessageBox

        path, _ = QFileDialog.getOpenFileName(
            self, "Run Python script", "", "Python (*.py);;All files (*)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
        except OSError as exc:
            QMessageBox.critical(self, "Run script", str(exc))
            return
        wb = self._doc.workbook
        ns = {
            "__name__": "qcell_script",
            "doc": self._doc,
            "wb": wb,
            "sheet": wb.sheet,
            "cell": lambda ref: wb.sheet.get(ref),
            "put": lambda ref, val: wb.sheet.set(ref, val if isinstance(val, str) else str(val)),
            "refresh": self.refresh_table,
        }
        try:
            exec(compile(src, path, "exec"), ns)
        except Exception:  # noqa: BLE001 - report any script error to the user
            import traceback

            QMessageBox.critical(self, "Run script", traceback.format_exc())
            return
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status(f"ran script {path}")

    def _save_recording(self) -> None:
        from ._qtcompat import QFileDialog

        if self._recorder.count == 0:
            self._set_status("nothing recorded yet")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save recorded macro", "", "Python macro (*.py)"
        )
        if not path:
            return
        saved = self._recorder.save_macro(path)
        if self._macro_registry is not None:
            from ..macros import load_macro_file

            load_macro_file(saved, self._macro_registry)  # immediately runnable
            rebuild = getattr(self, "_rebuild_macros_menu", None)
            if rebuild is not None:
                rebuild()
        self._set_status(f"saved macro {saved}")

    def _replay_recording(self) -> None:
        if self._recorder.count == 0:
            self._set_status("nothing recorded to replay")
            return
        self._recorder.replay(self._doc.workbook, at=self._current_cell())
        self._doc.mark_dirty()
        self.refresh_table()
        where = f" at {to_a1(*self._current_cell())}" if self._recorder.relative else ""
        self._set_status(f"replayed {self._recorder.count} action(s){where}")
