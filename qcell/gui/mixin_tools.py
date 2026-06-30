"""ToolsMixin — Data/science tools and cell actions: analysis dialogs, conditional format, formula browser, find/replace, number format, fill/sort/markdown, clipboard."""

from __future__ import annotations


class ToolsMixin:
    def _current_cell(self) -> tuple[int, int]:
        row = max(0, self._table.currentRow())
        col = max(0, self._table.currentColumn())
        return row, col

    def _recalculate(self) -> None:
        self._doc.workbook.recalculate()
        self.refresh_table()
        self._set_status("recalculated")

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
        dlg = CommandPalette(self, actions, placeholder="Filter clipboard history...")
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

    def show_matrix_tool(self) -> None:
        from .dialogs.matrix_dialog import MatrixDialog

        MatrixDialog(self).exec()

    def show_budget_wizard(self) -> None:
        from .dialogs.budget_dialog import BudgetWizard

        BudgetWizard(self).exec()

    def install_optional_features(self) -> None:
        """Force a background fetch of every optional dependency (full-fat)."""
        from .. import autodeps

        autodeps.set_enabled(True)
        pending = autodeps.prefetch_all(force=True)
        if pending:
            self._set_status(
                f"installing {len(pending)} optional package(s) in the background "
                "(numerics, Excel/Parquet, terminal, Jupyter)...")
        else:
            self._set_status("all optional features are already installed")

    def show_file_manager(self) -> None:
        from .dialogs.filemanager_dialog import FileManagerDialog

        if getattr(self, "_file_manager", None) is None:
            self._file_manager = FileManagerDialog(self)
        self._file_manager.refresh_both()
        self._file_manager.show()
        self._file_manager.raise_()

    def show_solver(self) -> None:
        from .dialogs.solver_dialog import SolverDialog

        SolverDialog(self).exec()

    def show_rf_tool(self) -> None:
        from .dialogs.rf_dialog import RFDialog

        RFDialog(self).exec()

    def show_smith_chart(self) -> None:
        from .dialogs.smith_dialog import SmithDialog

        SmithDialog(self).exec()

    def show_antenna_pattern(self) -> None:
        from .dialogs.antenna_dialog import AntennaDialog

        AntennaDialog(self).exec()

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

    def show_recode(self) -> None:
        from .dialogs.recode_dialog import RecodeDialog

        RecodeDialog(self).exec()

    def show_pivot(self) -> None:
        from .dialogs.pivot_dialog import PivotDialog

        PivotDialog(self).exec()

    def show_ml_tool(self) -> None:
        from .dialogs.ml_dialog import MLDialog

        MLDialog(self).exec()

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
