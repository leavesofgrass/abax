"""ToolsMixin — Data/science tools and cell actions: analysis dialogs, conditional format, formula browser, find/replace, number format, fill/sort/markdown, clipboard."""

from __future__ import annotations


class ToolsMixin:
    def _current_cell(self) -> tuple[int, int]:
        row = max(0, self._table.currentRow())
        col = max(0, self._table.currentColumn())
        return row, col

    def _recalculate(self) -> None:
        wb = self._doc.workbook
        if getattr(self._settings, "calc_iterative", False):
            # Iterative mode: resolve circular references by capped fixed-point.
            wb.calc_iterative = True
            wb.calc_max_iterations = int(getattr(self._settings, "calc_max_iterations", 100))
            wb.calc_max_change = float(getattr(self._settings, "calc_max_change", 0.001))
            iters, converged = wb.recalculate_iterative()
            self.refresh_table()
            self._set_status(
                f"iterative recalc: {iters} pass(es), "
                + ("converged" if converged else "did NOT converge (hit the cap)"))
            return
        # Large sheets: a cancellable progress dialog (F9 can be aborted). The
        # cancellation is cooperative — QProgressDialog pumps its own events on
        # setValue(), so the Cancel button registers between chunks (no threads).
        total = sum(len(s._cells) for s in wb.sheets)
        if total >= 20000:
            from ._qtcompat import QProgressDialog, Qt

            dlg = QProgressDialog("Recalculating…", "Cancel", 0, total, self)
            dlg.setWindowModality(Qt.WindowModality.WindowModal)
            dlg.setMinimumDuration(0)
            completed = wb.recalculate(
                should_cancel=dlg.wasCanceled,
                progress=lambda done, tot: dlg.setValue(done))
            dlg.close()
            self.refresh_table()
            self._set_status("recalculated" if completed else "recalc cancelled (sheet stays dirty)")
            return
        wb.recalculate()
        self.refresh_table()
        self._set_status("recalculated")

    def _recalculate_sheet(self) -> None:
        self._doc.workbook.sheet.recalculate()
        self.refresh_table()
        self._set_status("recalculated sheet")

    def _toggle_calc_mode(self) -> None:
        wb = self._doc.workbook
        new = "auto" if getattr(wb, "calc_mode", "auto") == "manual" else "manual"
        wb.set_calc_mode(new)
        self.refresh_table()  # switching to auto flushes deferred edits
        if new == "manual":
            self._set_status("calculation: MANUAL — press F9 to recalculate")
        else:
            self._set_status("calculation: automatic")

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

    def export_smith_svg(self) -> None:
        """Prompt for a load Z and Z0, then export a Smith chart as a standalone SVG."""
        from pathlib import Path

        from ._qtcompat import QFileDialog, QInputDialog
        from ..core.science import rf, smithsvg

        zt, ok = QInputDialog.getText(self, "Smith chart", "Load Z = R+jX (Ω):",
                                      text="75+25j")
        if not ok:
            return
        z0t, ok2 = QInputDialog.getText(self, "Smith chart", "System Z0 (Ω):",
                                        text="50")
        if not ok2:
            return
        try:
            zl = complex(zt.replace(" ", "").replace("i", "j"))
            z0 = float(z0t)
        except (ValueError, TypeError):
            self._set_status("enter Z as R+jX (e.g. 75+25j) and a numeric Z0")
            return
        svg = smithsvg.smith_svg([zl], z0=z0, show_vswr=True,
                                 title=f"Z = {zl.real:g}{zl.imag:+g}j on {z0:g}Ω")
        path, _ = QFileDialog.getSaveFileName(self, "Export Smith chart SVG",
                                              "smith.svg", "SVG image (*.svg)")
        if not path:
            return
        Path(path).write_text(svg, encoding="utf-8")
        vswr = rf.vswr_from_gamma(abs(rf.reflection_coefficient(zl, z0)))
        self._set_status(f"VSWR {vswr:.2f}:1 -> {Path(path).name}")

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

    def _print_workbook(self) -> None:
        from .print_export import print_document

        print_document(self)

    def _export_pdf(self) -> None:
        from .print_export import export_pdf

        export_pdf(self)

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

    def show_convert(self, paths: "list[str] | None" = None) -> None:
        """Batch file-conversion dialog — tabular via the engine, documents via
        pandoc. Optionally pre-filled with ``paths`` (e.g. a file-manager selection)."""
        from .dialogs.convert_dialog import ConvertDialog

        ConvertDialog(self, paths).exec()

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

    def show_antenna_modeler(self) -> None:
        """Model a real dipole / Yagi with method-of-moments (wire_mom).

        Reports gain (dBi), front-to-back (dB) and feed-point impedance from the
        physical dimensions, with an azimuth radiation pattern."""
        from .dialogs.antenna_modeler_dialog import AntennaModelerDialog

        AntennaModelerDialog(self).exec()

    def show_satellite(self) -> None:
        """Predict satellite passes from a TLE over an observer (SGP4)."""
        from .dialogs.satellite_dialog import SatelliteDialog

        SatelliteDialog(self).exec()

    def show_hamlog(self) -> None:
        """POTA/SOTA/contest activation log — dupe check, points, write to sheet."""
        from .dialogs.hamlog_dialog import HamLogDialog

        HamLogDialog(self).exec()

    def show_adif_logbook(self) -> None:
        """Open an amateur-radio logbook (ADIF ``.adi``/``.adif``) as a sheet.

        Routes through the normal document-open path (Document dispatches ADIF to
        :mod:`abax.core.io.adif_io` and enriches CALL -> DXCC entity)."""
        from ._qtcompat import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "Open logbook (ADIF)", "", "ADIF logbook (*.adi *.adif);;All files (*)")
        if not path:
            return
        self.open_document(path)

    def show_rf_reference(self) -> None:
        """Open the RF reference panel (amateur bands + CTCSS tones).

        Non-modal and reused across opens, so its values can be sent into the grid
        (double-click / Send) while you keep working — like the calculator."""
        from .dialogs.rf_reference_dialog import RfReferenceDialog

        dlg = getattr(self, "_rf_ref_dialog", None)
        if dlg is None:
            dlg = self._rf_ref_dialog = RfReferenceDialog(self)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

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

    def show_describe(self) -> None:
        from .dialogs.describe_dialog import DescribeDialog

        DescribeDialog(self).exec()

    def show_dataframe(self) -> None:
        from .dialogs.dataframe_dialog import DataFrameDialog

        DataFrameDialog(self).show()

    def show_recode(self) -> None:
        from .dialogs.recode_dialog import RecodeDialog

        RecodeDialog(self).exec()

    def show_pivot(self) -> None:
        from .dialogs.pivot_dialog import PivotDialog

        PivotDialog(self).exec()

    def format_as_table(self) -> None:
        """Name the selected region (header row on top) as a structured table,
        enabling ``Table1[Column]`` / ``Table1[@Column]`` references."""
        from ._qtcompat import QInputDialog, QMessageBox
        from ..core.reference import to_a1
        from ..core.tables import TableError, detect_table

        wb = self._doc.workbook
        sheet = wb.sheet
        ranges = self._table.selectedRanges()
        if ranges:
            rg = ranges[0]
            r1, c1, r2, c2 = rg.topRow(), rg.leftColumn(), rg.bottomRow(), rg.rightColumn()
        else:
            r1 = r2 = max(0, self._table.currentRow())
            c1 = c2 = max(0, self._table.currentColumn())
        if r2 <= r1:
            QMessageBox.warning(self, "Format as Table",
                                "Select a region with a header row plus at least one data row.")
            return
        default = f"Table{len(wb.tables) + 1}"
        name, ok = QInputDialog.getText(
            self, "Format as Table",
            f"Table name for {to_a1(r1, c1)}:{to_a1(r2, c2)} (top row = headers):",
            text=default)
        if not ok or not name.strip():
            return
        headers = ["" if sheet.get_value(r1, c) is None else str(sheet.get_value(r1, c))
                   for c in range(c1, c2 + 1)]
        try:
            wb.tables.add(detect_table(sheet.name, r1, c1, r2, c2, name.strip(), headers))
        except (TableError, ValueError) as exc:
            QMessageBox.warning(self, "Format as Table", str(exc))
            return
        self._doc.mark_dirty()
        self._set_status(f"table {name.strip()}: use ={name.strip()}[{headers[0]}] in formulas")

    def show_pivot_sidebar(self) -> None:
        """Toggle the drag-drop PivotTable Fields dock (create once, reuse)."""
        from ._qtcompat import Qt
        from .dialogs.pivot_sidebar import PivotSidebar

        dock = getattr(self, "_pivot_sidebar", None)
        if dock is None:
            dock = PivotSidebar(self)
            self._pivot_sidebar = dock
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        else:
            dock.reload_fields()
        dock.show()
        dock.raise_()

    def show_ml_tool(self) -> None:
        from .dialogs.ml_dialog import MLDialog

        MLDialog(self).exec()

    def show_curve_fit(self) -> None:
        from .dialogs.curvefit_dialog import CurveFitDialog

        CurveFitDialog(self).exec()

    def show_what_if(self) -> None:
        """One/two-variable data tables + a scenario manager over the sheet."""
        from .dialogs.whatif_dialog import WhatIfDialog

        WhatIfDialog(self).exec()

    def show_formula_profiler(self) -> None:
        """Rank formula cells by recalc cost and draw a cell's dependency graph."""
        from .dialogs.profile_dialog import ProfileDialog

        ProfileDialog(self).exec()

    def show_graph(self) -> None:
        from .dialogs.graph_dialog import GraphDialog

        if getattr(self, "_graph_dialog", None) is None:
            self._graph_dialog = GraphDialog(self)
        self._graph_dialog.show()
        self._graph_dialog.raise_()

    def show_business_chart(self) -> None:
        """Turn the current selection into a waterfall/sunburst/treemap/sparkline
        chart (SVG, with a live preview and Save-SVG)."""
        from .dialogs.business_chart_dialog import BusinessChartDialog

        BusinessChartDialog(self).exec()

    # --- embedded charts (floating ChartObjects on the sheet) -------------

    def show_insert_chart(self) -> None:
        """Insert an embedded chart anchored on the active sheet (Insert menu)."""
        from .dialogs.chart_dialog import ChartDialog

        dlg = ChartDialog(self)
        if not dlg.exec():
            return
        self.insert_embedded_chart(dlg.values())

    def insert_embedded_chart(self, values: dict) -> None:
        """Append a new ChartObject built from dialog ``values`` (one undo step).

        The chart is anchored just right of the current selection (top-aligned),
        so it doesn't cover the data it was made from.
        """
        from ..core.chartobj import ChartObject, new_chart_id

        sheet = self._doc.workbook.sheet
        r1, _c1, _r2, c2 = self._selected_bounds()
        self._doc.checkpoint("insert chart")
        chart = ChartObject(
            id=new_chart_id(sheet.charts),
            kind=values["kind"],
            source=values["source"],
            title=values.get("title", ""),
            labels=values.get("labels", ""),
            anchor=(r1, c2 + 2),
            width=int(values.get("width", 480)),
            height=int(values.get("height", 320)),
        )
        sheet.charts.append(chart)
        self._doc.mark_dirty()
        self.refresh_table()
        self._refresh_undo_history()
        self._set_status(f"inserted {chart.kind} chart {chart.id} ({chart.source})")

    def edit_embedded_chart(self, chart) -> None:
        """Reopen the chart dialog against ``chart`` and apply (one undo step)."""
        from .dialogs.chart_dialog import ChartDialog

        dlg = ChartDialog(self, chart=chart)
        if not dlg.exec():
            return
        values = dlg.values()
        self._doc.checkpoint("edit chart")
        chart.kind = values["kind"]
        chart.source = values["source"]
        chart.labels = values["labels"]
        chart.title = values["title"]
        chart.width = int(values["width"])
        chart.height = int(values["height"])
        self._doc.mark_dirty()
        self.refresh_table()
        self._refresh_undo_history()
        self._set_status(f"edited chart {chart.id}")

    def delete_embedded_chart(self, chart) -> None:
        """Remove ``chart`` from the active sheet (one undo step)."""
        sheet = self._doc.workbook.sheet
        if chart not in sheet.charts:
            return
        self._doc.checkpoint("delete chart")
        sheet.charts.remove(chart)
        self._doc.mark_dirty()
        self.refresh_table()
        self._refresh_undo_history()
        self._set_status(f"deleted chart {chart.id}")

    def _refresh_chart_overlays(self) -> None:
        """(Re)build and re-render the floating chart overlays (refresh_table hook).

        Lazy on both axes: the manager is only created once a sheet actually has
        charts, so chart-free sessions pay nothing on the (hot) refresh path.
        """
        manager = getattr(self, "_chart_overlays", None)
        if manager is None:
            table = getattr(self, "_table", None)
            sheet = self._doc.workbook.sheet
            if table is None or not getattr(sheet, "charts", None):
                return
            from .chart_overlay import ChartOverlayManager

            manager = self._chart_overlays = ChartOverlayManager(self)
        manager.refresh()

    def show_hex_viewer(self) -> None:
        """A streaming offset/hex/ASCII inspector for any file (non-modal)."""
        from .dialogs.hex_dialog import HexDialog

        HexDialog(self).show()

    def show_deptrace(self) -> None:
        """The current cell's precedents/dependents as a dependency tree."""
        from .dialogs.deptrace_dialog import DepTraceDialog

        DepTraceDialog(self).exec()

    def show_macro_manager(self) -> None:
        """A panel to view, run, and load macros (and init.py macro-menu entries)."""
        from .dialogs.macro_manager_dialog import MacroManagerDialog

        MacroManagerDialog(self).exec()

    def show_equation(self) -> None:
        from .dialogs.equation_dialog import EquationDialog

        if getattr(self, "_eq_dialog", None) is None:
            self._eq_dialog = EquationDialog(self)
        self._eq_dialog.show()
        self._eq_dialog.raise_()

    def set_number_format(self, spec: str) -> None:
        r1, c1, r2, c2 = self._selected_bounds()
        sheet = self._doc.workbook.sheet
        # Checkpoint before mutating so Ctrl+Z reverts the format change.
        self._doc.checkpoint(f"number format: {spec}")
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if spec == "general":
                    sheet.cell_formats.pop((r, c), None)
                else:
                    sheet.cell_formats[(r, c)] = spec
        self._doc.mark_dirty()
        self.refresh_table()
        self._refresh_undo_history()
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
