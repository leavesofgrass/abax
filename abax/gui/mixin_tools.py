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

    def show_sql_query(self) -> None:
        from .dialogs.sql_dialog import SqlDialog

        SqlDialog(self).exec()

    def show_goal_seek(self) -> None:
        from .dialogs.goalseek_dialog import GoalSeekDialog

        GoalSeekDialog(self).exec()

    def export_iq_svg(self) -> None:
        """Read a 2-column (I, Q) selection and export the constellation as SVG."""
        from pathlib import Path

        from ._qtcompat import QFileDialog
        from ..core.science import chartsvg, iq

        r1, c1, r2, c2 = self._selected_bounds()
        sheet = self._doc.workbook.sheet
        samples = []
        for r in range(r1, r2 + 1):
            i = sheet.get_value(r, c1)
            q = sheet.get_value(r, c1 + 1) if c2 > c1 else 0
            if isinstance(i, (int, float)) and not isinstance(i, bool):
                qv = float(q) if isinstance(q, (int, float)) and not isinstance(q, bool) else 0.0
                samples.append(complex(float(i), qv))
        if not samples:
            self._set_status("select I (and Q) columns of numbers")
            return
        svg = chartsvg.scatter_svg(iq.constellation_points(samples), title="I/Q constellation")
        path, _ = QFileDialog.getSaveFileName(self, "Export constellation SVG",
                                              "constellation.svg", "SVG image (*.svg)")
        if not path:
            return
        Path(path).write_text(svg, encoding="utf-8")
        self._set_status(f"{len(samples)} symbols, {iq.power_dbfs(samples):.1f} dBFS "
                         f"-> {Path(path).name}")

    def compare_workbook(self) -> None:
        """Diff the current workbook against another file into a new 'Diff' sheet."""
        from ._qtcompat import QFileDialog
        from ..core import wbdiff
        from ..engine.document import Document

        path, _ = QFileDialog.getOpenFileName(self, "Compare with workbook", "")
        if not path:
            return
        try:
            other = Document.open(path)
        except Exception as exc:  # noqa: BLE001
            from ._qtcompat import QMessageBox
            QMessageBox.warning(self, "Compare", str(exc))
            return
        diff = wbdiff.diff_workbooks(self._doc.workbook, other.workbook)
        wb = self._doc.workbook
        rep = wb.add_sheet(self._unique_sheet_name("Diff"))
        rep.set_cell(0, 0, wbdiff.summary(diff))
        headers = ["sheet", "row", "col", "kind", "this", "other"]
        for c, h in enumerate(headers):
            rep.set_cell(2, c, h)
        row = 3
        for sname, changes in diff["sheets"].items():
            for ch in changes:
                for c, v in enumerate([sname, ch["row"] + 1, ch["col"] + 1,
                                       ch["kind"], ch["a"], ch["b"]]):
                    rep.set_cell(row, c, str(v))
                row += 1
        wb.active = len(wb.sheets) - 1
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status("compared: " + wbdiff.summary(diff))

    def export_html_report(self) -> None:
        from pathlib import Path

        from ._qtcompat import QFileDialog
        from ..core.io import html_report

        path, _ = QFileDialog.getSaveFileName(self, "Export as HTML report",
                                              "report.html", "HTML (*.html *.htm)")
        if not path:
            return
        Path(path).write_text(html_report.workbook_to_html(self._doc.workbook),
                              encoding="utf-8")
        self._set_status(f"saved HTML report: {Path(path).name}")

    def _unique_sheet_name(self, base: str) -> str:
        existing = {s.name for s in self._doc.workbook.sheets}
        if base not in existing:
            return base
        n = 2
        while f"{base} {n}" in existing:
            n += 1
        return f"{base} {n}"

    def profile_columns(self) -> None:
        """Write a per-column profile of the active sheet to a new report sheet."""
        from ..core import profile

        stats = profile.profile_sheet(self._doc.workbook.sheet)
        if not stats:
            self._set_status("nothing to profile")
            return
        wb = self._doc.workbook
        rep = wb.add_sheet(self._unique_sheet_name("Profile"))
        headers = ["column", "dtype", "count", "missing", "unique",
                   "min", "max", "mean", "median", "std"]
        for c, h in enumerate(headers):
            rep.set_cell(0, c, h)
        for r, st in enumerate(stats, start=1):
            rep.set_cell(r, 0, str(st.get("name", "")))
            for c, key in enumerate(headers[1:], start=1):
                v = st.get(key)
                rep.set_cell(r, c, "" if v is None else
                             (f"{v:.4g}" if isinstance(v, float) else str(v)))
        wb.active = len(wb.sheets) - 1
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status(f"profiled {len(stats)} column(s)")

    def export_chart_svg(self) -> None:
        """Export the selected numeric range as an SVG chart (scatter if 2 columns)."""
        from pathlib import Path

        from ._qtcompat import QFileDialog
        from ..core.science import chartsvg

        r1, c1, r2, c2 = self._selected_bounds()
        sheet = self._doc.workbook.sheet
        cols: list[list[float]] = []
        for c in range(c1, c2 + 1):
            vals = [float(v) for r in range(r1, r2 + 1)
                    if isinstance((v := sheet.get_value(r, c)), (int, float))
                    and not isinstance(v, bool)]
            if vals:
                cols.append(vals)
        if not cols:
            self._set_status("select some numeric cells to chart")
            return
        if len(cols) >= 2:
            n = min(len(cols[0]), len(cols[1]))
            svg = chartsvg.scatter_svg(list(zip(cols[0][:n], cols[1][:n])), title="Selection")
        else:
            svg = chartsvg.line_svg([("series", list(enumerate(cols[0])))], title="Selection")
        path, _ = QFileDialog.getSaveFileName(self, "Export chart as SVG", "chart.svg",
                                              "SVG image (*.svg)")
        if not path:
            return
        Path(path).write_text(svg, encoding="utf-8")
        self._set_status(f"saved chart: {Path(path).name}")

    def install_optional_features(self) -> None:
        """Open the optional-feature chooser (Thin / All / custom)."""
        from .dialogs.deps_dialog import DependencyChooser

        DependencyChooser(self).exec()

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

    def show_rf_reference(self) -> None:
        """Open the RF reference panel (amateur bands + CTCSS tones)."""
        from .dialogs.rf_reference_dialog import RfReferenceDialog

        RfReferenceDialog(self).exec()

    def solve_nec_pynec(self) -> None:
        """Solve a NEC deck with PyNEC (reference-grade) if it is installed.

        Falls back to a clear message when PyNEC is absent — the built-in MoM
        (Scientific → RF toolkit / Antenna pattern) always works without it."""
        from ._qtcompat import QFileDialog, QMessageBox
        from ..engine import necpy

        if not necpy.available():
            QMessageBox.information(
                self, "PyNEC",
                "PyNEC is not installed. The built-in method-of-moments solver "
                "(RF toolkit / Antenna pattern) works without it; install the "
                "optional 'PyNEC' package for reference-grade results.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Solve NEC deck with PyNEC", "", "NEC deck (*.nec *.ez *.txt);;All files (*)")
        if not path:
            return
        try:
            from pathlib import Path

            res = necpy.solve_deck(Path(path).read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "PyNEC", str(exc))
            return
        z = res["feed_impedance"]
        QMessageBox.information(
            self, "PyNEC result",
            f"Frequency: {res['frequency_mhz']:g} MHz\n"
            f"Segments: {res['n_segments']}\n"
            f"Feed impedance: {z.real:.2f} {'+' if z.imag >= 0 else '-'} "
            f"j{abs(z.imag):.2f} Ω")
        self._set_status(f"PyNEC: Zin = {z.real:.1f}{z.imag:+.1f}j ohms")

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
