"""PaletteMixin — Discoverability: the command palette, the keyboard-shortcuts palette, and About."""

from __future__ import annotations


class PaletteMixin:
    def _shortcut_actions(self) -> dict:
        """A ``{"Menu > Action    -    Shortcut": action.trigger}`` mapping over
        every menu action that has a keyboard shortcut — powers the searchable
        shortcuts dialog (which also launches the action).

        Labels stay pure ASCII: the OpenDyslexic accessibility font has no glyphs
        for ``>``/``-``, so Qt would fall back to a CJK font and render them as
        overlapping full-width characters."""
        out: dict = {}

        def walk(menu, prefix: str) -> None:
            for act in menu.actions():
                sub = act.menu()
                if sub is not None:
                    walk(sub, f"{prefix}{act.text().replace('&', '')} > ")
                    continue
                sc = act.shortcut().toString()
                if sc and act.text():
                    out[f"{prefix}{act.text().replace('&', '')}    -    {sc}"] = act.trigger

        for menu_action in self.menuBar().actions():
            menu = menu_action.menu()
            if menu is not None:
                walk(menu, f"{menu_action.text().replace('&', '')} > ")
        return out

    def show_shortcuts(self) -> None:
        """A rofi/dmenu-style searchable list of keyboard shortcuts (Help, F1).

        Type to fuzzy-filter by action name or key; Enter runs the highlighted
        action. Reuses the command palette, so it shares its clean rendering."""
        from .command_palette import CommandPalette

        dlg = CommandPalette(self, self._shortcut_actions(),
                             placeholder="Filter shortcuts...")
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
            "Open...": lambda: self.open_document(None),
            "Import large CSV...": self.import_large_csv,
            "Save": lambda: self.save_document(None),
            "Save As...": self.save_document_as,
            "Choose theme...": self.choose_theme,
            "Toggle vim mode": self.toggle_vim_mode,
            "Recalculate": self._recalculate,
            "Find / Replace...": self.show_find_replace,
            "Show formula precedents": self.show_precedents,
            "Statistics / analysis...": self.show_stats_tool,
            "Open selection in pandas...": self.show_dataframe,
            "Recode / clean column...": self.show_recode,
            "Pivot / group-by...": self.show_pivot,
            "New sheet": self.insert_sheet,
            "Duplicate sheet": self.duplicate_sheet,
            "Delete sheet": self.delete_sheet,
            "Rename sheet...": self.rename_sheet,
            "Append row (end)": self.append_row,
            "Append column (end)": self.append_column,
            "Function browser...": self.show_formula_browser,
            "Show/hide calculator": self.toggle_calculator,
            "Get cell value -> calculator": self.cell_to_calc,
            "Send calculator value -> cell": self.calc_to_cells,
            "Terminal...": self.show_terminal,
            "Matrix tool...": self.show_matrix_tool,
            "File manager...": self.show_file_manager,
            "Budget wizard...": self.show_budget_wizard,
            "Install optional features now": self.install_optional_features,
            "RF toolkit...": self.show_rf_tool,
            "Smith chart...": self.show_smith_chart,
            "Antenna pattern...": self.show_antenna_pattern,
            "Python console...": self.show_pyconsole,
            "Graph...": self.show_graph,
            "Equation editor...": self.show_equation,
            "Clipboard history...": self.show_clipboard,
            "Manage clipboard...": self.manage_clipboard,
            "Toggle OpenDyslexic font": self.toggle_dyslexic_font,
            "Conditional format...": self.add_conditional_format,
            "Clear conditional formats": self.clear_conditional_formats,
            "Fill series": self._fill_series_selection,
            "Sort ascending": lambda: self._sort_selection(False),
            "Sort descending": lambda: self._sort_selection(True),
            "Copy selection as Markdown": self._copy_as_markdown,
            ("Stop recording" if recording else "Start recording"): self._toggle_recording,
            "Start relative recording": self._start_relative_recording,
            "Save recorded macro...": self._save_recording,
            "Load macro / UDF file...": self.load_macros,
            "Run Python script...": self.run_script,
            "Replay recording at cursor": self._replay_recording,
            "Quit": self.close,
        }
        registry = getattr(self, "_macro_registry", None)
        if registry:
            for name in sorted(registry.macros):
                actions[f"Macro: {name}"] = lambda n=name: self._run_macro(n)
        return actions
