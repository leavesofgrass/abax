"""DocumentMixin — open / save / new and table<->sheet synchronization.

No mixin calls another (spec §2). Each mixin assumes the host QMainWindow
exposes the shared attributes set up in ``MainWindow._setup_ui`` (``_doc``,
``_table``, ``_formula_bar``, ``_settings``).
"""

from __future__ import annotations

from pathlib import Path

from ._qtcompat import QFileDialog, QMessageBox, QTableWidgetSelectionRange
from ..core.reference import index_to_col, to_a1

_OPEN_FILTER = (
    "Spreadsheets (*.csv *.tsv *.tab *.xlsx *.ods *.xml *.json *.qcell *.md "
    "*.ipynb *.R *.parquet *.feather);;"
    "CSV/TSV (*.csv *.tsv *.tab);;Excel (*.xlsx);;LibreOffice (*.ods);;"
    "Parquet/Feather (*.parquet *.pq *.feather *.ft);;XML Spreadsheet (*.xml);;"
    "Markdown (*.md *.markdown);;Jupyter notebook (*.ipynb);;R (*.R *.RData);;"
    "qcell/JSON (*.qcell *.json);;All files (*)"
)
_SAVE_FILTER = (
    "Native JSON (*.qcell);;CSV (*.csv);;TSV (*.tsv);;Excel (*.xlsx);;"
    "LibreOffice (*.ods);;Parquet (*.parquet);;Feather (*.feather);;"
    "XML Spreadsheet (*.xml);;Markdown (*.md);;Jupyter notebook (*.ipynb);;"
    "R data.frame (*.R);;All files (*)"
)


class DocumentMixin:
    def new_document(self) -> None:
        from ..engine.document import Document

        self._doc = Document()
        self.refresh_table()
        self._update_title()

    def open_document(self, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Open spreadsheet", "", _OPEN_FILTER)
            if not path:
                return
        # Off the UI thread: the worker builds a fresh Document from the file and
        # nothing on the main thread touches it until the result arrives, so there
        # is no shared state to race. A large file no longer freezes the window.
        from ..workers import IOWorker

        self._run_io(IOWorker("open", str(path)),
                     on_success=self._open_succeeded,
                     busy_msg=f"opening {Path(path).name}…")

    def _open_succeeded(self, doc) -> None:
        self._doc = doc
        if doc.path:
            self._remember_recent(str(doc.path))
        self.refresh_table()
        self._update_title()
        self._set_status(f"opened {doc.title}")

    # --- async open/save plumbing ----------------------------------------

    def _run_io(self, worker, *, on_success, busy_msg: str) -> None:
        """Run a pre-built worker (IOWorker / FuncWorker) on a background thread.

        Guards against overlapping operations, disables editing and shows a
        progress bar for the duration (visual "busy" + belt-and-braces against
        mutation). Errors surface via a dialog from the main thread; the UI is
        always restored in ``_on_io_done`` (fires on ``thread.finished``).
        """
        if getattr(self, "_io_busy", False):
            self._set_status("an open/save is already in progress")
            return
        from ._qtcompat import QApplication, Qt, QThread

        self._io_busy = True
        self._io_on_success = on_success
        self._table.setEnabled(False)
        self._formula_bar.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._begin_progress(busy_msg)

        thread = QThread()
        worker.moveToThread(thread)
        self._io_thread, self._io_worker = thread, worker  # keep refs (avoid GC)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_io_progress)
        worker.result.connect(self._on_io_result)
        worker.error.connect(self._on_io_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        # Restore + drop refs only on thread.finished — i.e. after the thread has
        # actually stopped. Dropping the QThread ref while it is still running
        # would delete it mid-run and abort the process.
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_io_done)
        thread.start()

    def _begin_progress(self, msg: str) -> None:
        self._set_status(msg)
        bar = getattr(self, "_progress", None)
        if bar is not None:
            bar.setValue(0)
            bar.setVisible(True)

    def _on_io_progress(self, pct: int) -> None:
        bar = getattr(self, "_progress", None)
        if bar is not None:
            bar.setValue(pct)

    def _on_io_result(self, obj) -> None:
        cb = getattr(self, "_io_on_success", None)
        if cb is not None:
            cb(obj)

    def _on_io_error(self, msg: str) -> None:
        QMessageBox.critical(self, "File operation failed", msg)

    def _on_io_done(self) -> None:
        from ._qtcompat import QApplication

        QApplication.restoreOverrideCursor()
        bar = getattr(self, "_progress", None)
        if bar is not None:
            bar.setVisible(False)
        self._table.setEnabled(True)
        self._formula_bar.setEnabled(True)
        self._io_busy = False
        self._io_on_success = None
        self._io_thread = None
        self._io_worker = None

    def import_large_csv(self) -> None:
        """Stream-import a (possibly huge) CSV with type inference + an optional row cap."""
        from ._qtcompat import QFileDialog, QInputDialog, QMessageBox
        from ..core.io import csv_stream

        path, _ = QFileDialog.getOpenFileName(
            self, "Import large CSV (streaming)", "",
            "CSV / TSV (*.csv *.tsv *.txt);;All files (*)")
        if not path:
            return
        try:
            prof = csv_stream.sniff_csv(path)   # fast: just samples the file
        except csv_stream.CsvStreamError as exc:
            QMessageBox.critical(self, "Import CSV", str(exc))
            return
        cap = None
        if prof.approx_rows > 50000:
            n, ok = QInputDialog.getInt(
                self, "Large CSV",
                f"~{prof.approx_rows:,} rows detected.\nRows to import (0 = all):",
                100000, 0, 5_000_000)
            if not ok:
                return
            cap = n or None
        # The streaming parse is the slow part — run it off the UI thread. It
        # builds a fresh Workbook (no shared state), like open.
        from ..workers import FuncWorker

        worker = FuncWorker(
            lambda: csv_stream.load_csv_streaming(path, max_rows=cap, coerce_types=True))
        self._run_io(worker,
                     on_success=lambda wb: self._import_succeeded(wb, path, prof),
                     busy_msg=f"importing {Path(path).name}…")

    def _import_succeeded(self, wb, path, prof) -> None:
        from ..engine.document import Document

        self._doc = Document(wb, Path(path))
        self._remember_recent(path)
        self.refresh_table()
        self._update_title()
        self._set_status(
            f"imported {len(prof.columns)} cols (delim {prof.delimiter!r}, "
            f"~{prof.approx_rows:,} rows)")

    def save_document(self, path: str | None = None) -> None:
        if path is None and self._doc.path is None:
            self.save_document_as()
            return
        target = Path(path) if path else self._doc.path
        self.commit_table_to_sheet()
        # Save an INDEPENDENT snapshot off-thread: the format-specific savers read
        # the workbook's compute caches (get_value / _value_cache / _computing),
        # which the UI thread may still touch while painting. Rebuilding the
        # workbook from its (raw-text) envelope gives the worker its own caches, so
        # there is no cross-thread race. The envelope build is cheap (no formulas).
        from ..core.workbook import Workbook
        from ..engine.document import Document

        snapshot = Document(Workbook.from_envelope(self._doc.workbook.to_envelope()), target)
        from ..workers import IOWorker

        self._run_io(IOWorker("save", str(target), snapshot),
                     on_success=lambda _obj: self._save_succeeded(target),
                     busy_msg=f"saving {target.name}…")

    def _save_succeeded(self, target) -> None:
        self._doc.path = Path(target)
        self._doc.dirty = False
        self._remember_recent(str(target))
        self._update_title()
        self._set_status(f"saved {Path(target).name}")

    def save_document_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save spreadsheet", "", _SAVE_FILTER)
        if path:
            self.save_document(path)

    # --- table <-> sheet sync --------------------------------------------

    def refresh_table(self) -> None:
        # The model renders the viewport lazily; refresh recomputes its cached
        # conditional fills + extent and repaints, preserving the selection.
        self._model.refresh()
        self._reapply_filter()   # keep an active filter applied across refreshes
        frozen = getattr(self, "_frozen", None)
        if frozen is not None and frozen.active:
            frozen.sync()
        rebuild = getattr(self, "_rebuild_tabs", None)
        if rebuild is not None:
            rebuild()
        update_cluster = getattr(self, "_update_status_cluster", None)
        if update_cluster is not None:
            update_cluster()

    def commit_table_to_sheet(self) -> None:
        """Push any edited cell back into the sheet model (raw text wins)."""
        # Edits are applied live via _commit_cell; this is a safety net.
        pass

    def _commit_cell(self, row: int, col: int, new_raw: str) -> bool:
        """Commit an in-cell edit (called from QcellTableModel.setData).

        Returns whether the sheet changed. Validation rejects bad input (the
        edit is discarded). Mirrors the formula-bar commit path so undo,
        macro-recording, and dependent recalculation are identical.
        """
        sheet = self._doc.workbook.sheet
        old_raw = sheet.get_raw(row, col)
        if new_raw == old_raw:
            return False
        rule = sheet.validation_for(row, col)
        if rule is not None and new_raw.strip() != "":
            from ..core.validation import validate

            ok, msg = validate(new_raw, rule)
            if not ok:
                QMessageBox.warning(self, "Invalid entry", msg)
                return False
        self._doc.checkpoint(f"edit {to_a1(row, col)}", coalesce_key="edit")
        sheet.set_cell(row, col, new_raw)
        rec = getattr(self, "_recorder", None)
        if rec is not None:
            rec.record_set(to_a1(row, col), new_raw)
        self._doc.mark_dirty()
        self.refresh_table()  # dependents may have changed
        return True

    # --- copy / paste / fill (grid editing) ------------------------------

    def _record(self, ref: str, raw: str) -> None:
        rec = getattr(self, "_recorder", None)
        if rec is not None:
            rec.record_set(ref, raw)

    # --- sort / filter / go-to -------------------------------------------

    def _sort_region_bounds(self) -> tuple[int, int, int, int]:
        r1, c1, r2, c2 = self._selected_bounds()
        if r1 == r2 and c1 == c2:
            from ..core.navigation import current_region

            sheet = self._doc.workbook.sheet
            populated = {(r, c) for r, c, _ in sheet.iter_cells()}
            return current_region(populated, r1, c1)
        return (r1, c1, r2, c2)

    def show_sort_dialog(self) -> None:
        from .sort_dialog import SortDialog

        SortDialog(self).exec()

    def show_filter_dialog(self) -> None:
        from .filter_dialog import FilterDialog

        FilterDialog(self).exec()

    def apply_sort(self, bounds, keys, has_header: bool) -> None:
        from ..core import sortfilter

        r1, c1, r2, c2 = bounds
        start = r1 + (1 if has_header else 0)
        if start > r2:
            return
        sheet = self._doc.workbook.sheet
        width = c2 - c1 + 1
        src_rows = list(range(start, r2 + 1))
        rows = [[sheet.get_raw(r, c1 + j) for j in range(width)] for r in src_rows]
        rel_keys = [(c - c1, desc) for c, desc in keys]
        try:
            order = sortfilter.sort_order(rows, rel_keys)
        except sortfilter.SortFilterError:
            return
        self._doc.checkpoint("sort")
        styles = [[sheet.cell_styles.get((r, c1 + j)) for j in range(width)] for r in src_rows]
        formats = [[sheet.cell_formats.get((r, c1 + j)) for j in range(width)] for r in src_rows]
        for r in src_rows:
            for j in range(width):
                sheet.cell_styles.pop((r, c1 + j), None)
                sheet.cell_formats.pop((r, c1 + j), None)
        for newi, oldi in enumerate(order):
            destr = start + newi
            for j in range(width):
                sheet.set_cell(destr, c1 + j, rows[oldi][j])
                if styles[oldi][j] is not None:
                    sheet.cell_styles[(destr, c1 + j)] = styles[oldi][j]
                if formats[oldi][j] is not None:
                    sheet.cell_formats[(destr, c1 + j)] = formats[oldi][j]
        self._doc.mark_dirty()
        self.refresh_table()
        self._refresh_undo_history()
        self._set_status("sorted")

    def apply_filter(self, bounds, predicates) -> None:
        shown = self._run_filter(bounds, predicates)
        if shown is None:
            return
        self._active_filter = (bounds, predicates)   # remember so it survives refresh
        self._set_status(f"filter: {shown} rows shown")

    def _run_filter(self, bounds, predicates) -> "int | None":
        from ..core import sortfilter

        r1, c1, r2, c2 = bounds
        sheet = self._doc.workbook.sheet
        src_rows = list(range(r1, r2 + 1))
        rows = [[sheet.get_raw(r, c) for c in range(c1, c2 + 1)] for r in src_rows]
        rel = [(c - c1, op, val) for c, op, val in predicates]
        try:
            keep = set(sortfilter.filter_rows(rows, rel))
        except sortfilter.SortFilterError:
            return None
        for i, r in enumerate(src_rows):
            if r < self._table.rowCount():
                self._table.setRowHidden(r, i not in keep)
        return len(keep)

    def _reapply_filter(self) -> None:
        active = getattr(self, "_active_filter", None)
        if active is not None:
            self._run_filter(*active)

    def clear_filter(self) -> None:
        self._active_filter = None
        for r in range(self._table.rowCount()):
            self._table.setRowHidden(r, False)
        self._set_status("filter cleared")

    def show_goto(self) -> None:
        from ._qtcompat import QInputDialog
        from ..core.navigation import NavError, parse_target

        text, ok = QInputDialog.getText(self, "Go to", "Cell or range (e.g. B12 or A1:C9):")
        if not ok or not text.strip():
            return
        try:
            target = parse_target(text)
        except NavError:
            self._set_status(f"can't parse target: {text}")
            return
        if len(target) == 2:
            self._table.setCurrentCell(target[0], target[1])
        else:
            r1, c1, r2, c2 = target
            self._table.setCurrentCell(r1, c1)
            self._table.clearSelection()
            self._table.setRangeSelected(QTableWidgetSelectionRange(r1, c1, r2, c2), True)
        self._set_status(f"went to {text}")

    # --- named ranges ----------------------------------------------------

    def define_name(self) -> None:
        from ._qtcompat import QInputDialog, QMessageBox
        from ..core.names import NameError as NmError

        r1, c1, r2, c2 = self._selected_bounds()
        target = (to_a1(r1, c1) if (r1 == r2 and c1 == c2)
                  else f"{to_a1(r1, c1)}:{to_a1(r2, c2)}")
        name, ok = QInputDialog.getText(self, "Name range", f"Name for {target}:")
        if not ok or not name.strip():
            return
        try:
            self._doc.checkpoint("define name")
            self._doc.workbook.names.define(name.strip(), target)
        except NmError as exc:
            QMessageBox.warning(self, "Name range", str(exc))
            return
        self._doc.workbook.invalidate_caches()
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status(f"named {name.strip()} = {target}")

    def show_name_manager(self) -> None:
        from .name_manager_dialog import NameManagerDialog

        NameManagerDialog(self).exec()

    # --- data validation -------------------------------------------------

    def show_validation_dialog(self) -> None:
        from .validation_dialog import ValidationDialog

        ValidationDialog(self).exec()

    def apply_validation(self, bounds, rule) -> None:
        r1, c1, r2, c2 = bounds
        self._doc.checkpoint("data validation")
        self._doc.workbook.sheet.validations.append((r1, c1, r2, c2, rule))
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status("validation applied")

    def clear_validation(self) -> None:
        r1, c1, r2, c2 = self._selected_bounds()
        sheet = self._doc.workbook.sheet
        kept = [v for v in sheet.validations
                if not (v[0] <= r2 and v[2] >= r1 and v[1] <= c2 and v[3] >= c1)]
        if len(kept) != len(sheet.validations):
            self._doc.checkpoint("clear validation")
            sheet.validations = kept
            self._doc.mark_dirty()
            self.refresh_table()
            self._set_status("validation cleared")

    # --- cell styling ----------------------------------------------------

    def _selection_cells(self) -> list[tuple[int, int]]:
        r1, c1, r2, c2 = self._selected_bounds()
        return [(r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]

    def _set_style(self, cells, label, **changes) -> None:
        from ..core.format.cellstyle import CellStyle

        self._doc.checkpoint(label)
        sheet = self._doc.workbook.sheet
        for key in cells:
            new = sheet.cell_styles.get(key, CellStyle()).with_changes(**changes)
            if new.is_empty():
                sheet.cell_styles.pop(key, None)
            else:
                sheet.cell_styles[key] = new
        self._doc.mark_dirty()
        self.refresh_table()
        self._refresh_undo_history()
        self._set_status(label)

    def toggle_style(self, field: str) -> None:
        """Toggle a boolean style (bold/italic/underline) across the selection.

        Turns the field ON for all if any cell lacks it, else OFF for all.
        """
        from ..core.format.cellstyle import CellStyle

        cells = self._selection_cells()
        sheet = self._doc.workbook.sheet
        turn_on = any(
            not getattr(sheet.cell_styles.get(k, CellStyle()), field) for k in cells)
        self._set_style(cells, f"{'set' if turn_on else 'unset'} {field}", **{field: turn_on})

    def set_alignment(self, align: str) -> None:
        self._set_style(self._selection_cells(), f"align {align}", align=align)

    def pick_text_color(self) -> None:
        self._pick_color("text_color", "text colour")

    def pick_fill_color(self) -> None:
        self._pick_color("bg_color", "fill colour")

    def _pick_color(self, field: str, label: str) -> None:
        from ._qtcompat import QColorDialog

        color = QColorDialog.getColor(parent=self, title=f"Choose {label}")
        if not color.isValid():
            return
        self._set_style(self._selection_cells(), label, **{field: color.name()})

    def clear_styles(self) -> None:
        cells = [k for k in self._selection_cells()
                 if k in self._doc.workbook.sheet.cell_styles]
        if not cells:
            return
        self._doc.checkpoint("clear styles")
        sheet = self._doc.workbook.sheet
        for key in cells:
            sheet.cell_styles.pop(key, None)
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status("cleared styles")

    def show_precedents(self) -> None:
        """Highlight the cells the selected formula reads from (its precedents)."""
        from ..core import precedents

        r = max(0, self._table.currentRow())
        c = max(0, self._table.currentColumn())
        raw = self._doc.workbook.sheet.get_raw(r, c)
        try:
            cells = precedents.precedent_cells(raw)
        except precedents.PrecedentError as exc:
            self._set_status(f"precedents: {exc}")
            return
        if not cells:
            self._set_status("no precedents — the cell isn't a formula with references")
            return
        table = self._table
        table.clearSelection()
        nr, nc = table.rowCount(), table.columnCount()
        for pr, pc in cells:
            if 0 <= pr < nr and 0 <= pc < nc:
                table.setRangeSelected(QTableWidgetSelectionRange(pr, pc, pr, pc), True)
        self._set_status(
            f"{len(cells)} precedent cell(s) of {to_a1(r, c)} highlighted")

    def _selected_bounds(self) -> tuple[int, int, int, int]:
        ranges = self._table.selectedRanges()
        if ranges:
            r = ranges[0]
            return r.topRow(), r.leftColumn(), r.bottomRow(), r.rightColumn()
        row = max(0, self._table.currentRow())
        col = max(0, self._table.currentColumn())
        return row, col, row, col

    def copy_selection(self) -> None:
        from ._qtcompat import QApplication
        from ..core.fill import copy_region, region_to_tsv

        bounds = self._selected_bounds()
        sheet = self._doc.workbook.sheet
        self._clip = copy_region(sheet, bounds)
        tsv = region_to_tsv(sheet, bounds)  # values, for other apps
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(tsv)
        if getattr(self, "_clipboard", None) is not None:
            self._clipboard.add(tsv)
        self._set_status(f"copied {self._clip.nrows}x{self._clip.ncols}")

    def cut_selection(self) -> None:
        """Copy the selection to the clip/clipboard, then clear it (one undo step)."""
        self.copy_selection()                      # no mutation
        self._doc.checkpoint("cut")
        if self._clear_region(self._selected_bounds()):
            self._doc.mark_dirty()
            self.refresh_table()
        self._set_status("cut")

    def paste_at_cursor(self) -> None:
        from ._qtcompat import QApplication
        from ..core.fill import clip_from_tsv, paste_clip

        row = max(0, self._table.currentRow())
        col = max(0, self._table.currentColumn())
        sheet = self._doc.workbook.sheet
        self._doc.checkpoint("paste")
        if self._clip is not None:
            paste_clip(sheet, self._clip, (row, col), on_set=self._record)  # relative
        else:
            cb = QApplication.clipboard()
            text = cb.text() if cb is not None else ""
            if not text:
                self._set_status("clipboard empty")
                return
            clip = clip_from_tsv(text, (row, col))
            paste_clip(sheet, clip, (row, col), mode="absolute", on_set=self._record)
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status("pasted")

    def fill_down_selection(self) -> None:
        from ..core.fill import fill_down

        self._doc.checkpoint("fill down")
        fill_down(self._doc.workbook.sheet, self._selected_bounds(), on_set=self._record)
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status("filled down")

    def fill_right_selection(self) -> None:
        from ..core.fill import fill_right

        self._doc.checkpoint("fill right")
        fill_right(self._doc.workbook.sheet, self._selected_bounds(), on_set=self._record)
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status("filled right")

    def _clear_region(self, bounds) -> bool:
        """Clear the cells in ``bounds`` (recording each); returns whether anything changed."""
        r1, c1, r2, c2 = bounds
        sheet = self._doc.workbook.sheet
        changed = False
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if sheet.get_raw(r, c) != "":
                    sheet.set_cell(r, c, "")
                    self._record(to_a1(r, c), "")
                    changed = True
        return changed

    def _clear_selection(self) -> None:
        self._doc.checkpoint("clear")
        if self._clear_region(self._selected_bounds()):
            self._doc.mark_dirty()
            self.refresh_table()
            self._set_status("cleared")

    # --- undo / redo -----------------------------------------------------

    def undo_edit(self) -> None:
        if self._doc.undo():
            self.refresh_table()
            self._refresh_undo_history()
            self._set_status("undo")
        else:
            self._set_status("nothing to undo")

    def redo_edit(self) -> None:
        if self._doc.redo():
            self.refresh_table()
            self._refresh_undo_history()
            self._set_status("redo")
        else:
            self._set_status("nothing to redo")

    def jump_undo(self, times: int) -> None:
        for _ in range(times):
            if not self._doc.undo():
                break
        self.refresh_table()
        self._refresh_undo_history()
        self._set_status("undo")

    def jump_redo(self, times: int) -> None:
        for _ in range(times):
            if not self._doc.redo():
                break
        self.refresh_table()
        self._refresh_undo_history()
        self._set_status("redo")

    def show_undo_history(self) -> None:
        from .undo_history_dialog import UndoHistoryDialog

        dlg = getattr(self, "_undo_history_dialog", None)
        if dlg is None:
            dlg = UndoHistoryDialog(self)
            self._undo_history_dialog = dlg
        dlg.refresh()
        dlg.show()
        dlg.raise_()

    def _refresh_undo_history(self) -> None:
        dlg = getattr(self, "_undo_history_dialog", None)
        if dlg is not None and dlg.isVisible():
            dlg.refresh()

    # --- rows & columns --------------------------------------------------

    def insert_row(self, above: bool = True, at: int | None = None) -> None:
        r1, _c1, r2, _c2 = self._selected_bounds()
        count = r2 - r1 + 1
        if at is None:
            line = r1 if above else r2 + 1
        else:
            count, line = 1, at
        self._doc.checkpoint(f"insert {count} row(s)")
        self._doc.workbook.sheet.insert_rows(line, count)
        self._after_structure(
            f"Inserted {count} row(s) at row {line + 1}", rows=(line, line + count - 1))

    def insert_column(self, left: bool = True, at: int | None = None) -> None:
        _r1, c1, _r2, c2 = self._selected_bounds()
        count = c2 - c1 + 1
        if at is None:
            line = c1 if left else c2 + 1
        else:
            count, line = 1, at
        self._doc.checkpoint(f"insert {count} column(s)")
        self._doc.workbook.sheet.insert_cols(line, count)
        self._after_structure(
            f"Inserted {count} column(s) at {index_to_col(line)}",
            cols=(line, line + count - 1))

    def append_row(self) -> None:
        """Add a blank row after the last used row and jump to it."""
        n_rows, _ = self._doc.workbook.sheet.used_bounds()
        self._grid_min_rows = max(self._grid_min_rows, n_rows + 10)
        self.insert_row(at=max(0, n_rows))

    def append_column(self) -> None:
        """Add a blank column after the last used column and jump to it."""
        _, n_cols = self._doc.workbook.sheet.used_bounds()
        self._grid_min_cols = max(self._grid_min_cols, n_cols + 4)
        self.insert_column(at=max(0, n_cols))

    # Growing the grid inserts rows/columns into the model (begin/endInsert*).
    # Doing that *synchronously* inside a scrollbar valueChanged handler mutates
    # the model while the view is mid-scroll/layout, which can re-enter Qt and
    # crash on fast scrolling. So we only detect the edge here and defer the
    # actual structural growth to the next event-loop turn; ``_growing`` coalesces
    # the burst of scroll ticks until the deferred grow has run.

    def _maybe_grow_rows(self, value: int) -> None:
        """Grow the grid downward when the user scrolls to the bottom edge.

        Cheap now: it only bumps the model's reported extent (no per-cell
        materialization), so deep rows become reachable without a full refresh.
        """
        if getattr(self, "_growing", False):
            return
        sb = self._table.verticalScrollBar()
        if sb.maximum() > 0 and value >= sb.maximum() - 1:
            from ._qtcompat import QTimer

            self._growing = True
            QTimer.singleShot(0, self._grow_rows_now)

    def _grow_rows_now(self) -> None:
        try:
            self._grid_min_rows = max(self._table.rowCount() * 2,
                                      self._table.rowCount() + 200)
            self._model.ensure_extent(self._grid_min_rows, self._table.columnCount())
        finally:
            self._growing = False

    def _maybe_grow_cols(self, value: int) -> None:
        """Grow the grid rightward when the user scrolls to the right edge."""
        if getattr(self, "_growing", False):
            return
        sb = self._table.horizontalScrollBar()
        if sb.maximum() > 0 and value >= sb.maximum() - 1:
            from ._qtcompat import QTimer

            self._growing = True
            QTimer.singleShot(0, self._grow_cols_now)

    def _grow_cols_now(self) -> None:
        try:
            self._grid_min_cols = self._table.columnCount() + 16
            self._model.ensure_extent(self._table.rowCount(), self._grid_min_cols)
        finally:
            self._growing = False

    def delete_row(self, at: int | None = None) -> None:
        r1, _c1, r2, _c2 = self._selected_bounds()
        line, count = (r1, r2 - r1 + 1) if at is None else (at, 1)
        self._doc.checkpoint(f"delete {count} row(s)")
        self._doc.workbook.sheet.delete_rows(line, count)
        self._after_structure(f"Deleted {count} row(s)", rows=(line, line))

    def delete_column(self, at: int | None = None) -> None:
        _r1, c1, _r2, c2 = self._selected_bounds()
        line, count = (c1, c2 - c1 + 1) if at is None else (at, 1)
        self._doc.checkpoint(f"delete {count} column(s)")
        self._doc.workbook.sheet.delete_cols(line, count)
        self._after_structure(f"Deleted {count} column(s)", cols=(line, line))

    def _after_structure(self, message: str, rows=None, cols=None) -> None:
        """Refresh after a row/column change, then announce it and highlight +
        scroll to the affected band so the edit is visibly obvious."""
        self._doc.mark_dirty()
        self.refresh_table()
        table = self._table
        nr, nc = table.rowCount(), table.columnCount()
        table.clearSelection()
        if rows is not None and nr and nc:
            r1, r2 = rows
            r1, r2 = max(0, r1), min(r2, nr - 1)
            table.setRangeSelected(QTableWidgetSelectionRange(r1, 0, r2, nc - 1), True)
            table.setCurrentCell(r1, 0)
        elif cols is not None and nr and nc:
            c1, c2 = cols
            c1, c2 = max(0, c1), min(c2, nc - 1)
            table.setRangeSelected(QTableWidgetSelectionRange(0, c1, nr - 1, c2), True)
            table.setCurrentCell(0, c1)
        item = table.item(max(0, table.currentRow()), max(0, table.currentColumn()))
        if item is not None:
            table.scrollToItem(item)
        self._set_status(message)

    # --- sheets ----------------------------------------------------------

    def insert_sheet(self) -> None:
        from ._qtcompat import QInputDialog, QMessageBox

        name, ok = QInputDialog.getText(self, "Insert sheet", "Sheet name (blank = auto):")
        if not ok:
            return
        try:
            sheet = self._doc.workbook.add_sheet(name.strip() or None)
        except ValueError as exc:
            QMessageBox.warning(self, "Insert sheet", str(exc))
            return
        self._doc.workbook.active = self._doc.workbook.sheets.index(sheet)
        self._doc.mark_dirty()
        self.refresh_table()
        self._update_title()
        self._set_status(f"inserted sheet {sheet.name}")

    def duplicate_sheet(self) -> None:
        """Copy the active sheet (cells + styles) into a new sheet and switch to it."""
        wb = self._doc.workbook
        src = wb.sheet
        base = f"{src.name} copy"
        name, i = base, 2
        while wb.get_sheet(name) is not None:
            name, i = f"{base} {i}", i + 1
        new = wb.add_sheet(name)
        nr, nc = src.used_bounds()
        for r in range(nr):
            for c in range(nc):
                raw = src.get_raw(r, c)
                if raw:
                    new.set_cell(r, c, raw)
        for attr in ("cell_styles", "cell_formats", "cond_rules"):
            data = getattr(src, attr, None)
            if isinstance(data, dict):
                setattr(new, attr, dict(data))
        wb.active = wb.sheets.index(new)
        self._doc.mark_dirty()
        self.refresh_table()
        self._update_title()
        rebuild = getattr(self, "_rebuild_tabs", None)
        if rebuild is not None:
            rebuild()
        self._set_status(f"duplicated to {name}")

    def delete_sheet(self) -> None:
        """Delete the active sheet (a workbook keeps at least one)."""
        from ._qtcompat import QMessageBox

        wb = self._doc.workbook
        if len(wb.sheets) <= 1:
            QMessageBox.information(self, "Delete sheet",
                                    "A workbook must keep at least one sheet.")
            return
        name = wb.sheet.name
        if QMessageBox.question(
                self, "Delete sheet",
                f"Delete sheet “{name}”? This can't be undone with Ctrl+Z."
        ) != QMessageBox.StandardButton.Yes:
            return
        wb.remove_sheet(name)
        self._doc.mark_dirty()
        self.refresh_table()
        self._update_title()
        rebuild = getattr(self, "_rebuild_tabs", None)
        if rebuild is not None:
            rebuild()
        self._set_status(f"deleted sheet {name}")

    def next_sheet(self) -> None:
        self._switch_sheet(1)

    def prev_sheet(self) -> None:
        self._switch_sheet(-1)

    def _switch_sheet(self, delta: int) -> None:
        wb = self._doc.workbook
        wb.active = (wb.active + delta) % len(wb.sheets)
        self.refresh_table()
        self._update_title()
        self._set_status(f"sheet: {wb.sheet.name} ({wb.active + 1}/{len(wb.sheets)})")

    def rename_sheet(self) -> None:
        from ._qtcompat import QInputDialog

        wb = self._doc.workbook
        name, ok = QInputDialog.getText(self, "Rename sheet", "New name:", text=wb.sheet.name)
        if ok and name.strip():
            wb.sheet.name = name.strip()
            self._doc.mark_dirty()
            self._update_title()
            rebuild = getattr(self, "_rebuild_tabs", None)
            if rebuild is not None:
                rebuild()
            self._set_status(f"renamed to {name.strip()}")

    def _remember_recent(self, path: str) -> None:
        recent = list(getattr(self._settings, "recent_files", []))
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self._settings.recent_files = recent[:10]

    def _update_title(self) -> None:
        name = self._doc.title
        flag = "*" if self._doc.dirty else ""
        rec = getattr(self, "_recorder", None)
        if rec is not None and rec.recording:
            prefix = "● REL  " if rec.relative else "● REC  "
        else:
            prefix = ""
        wb = self._doc.workbook
        tab = f" [{wb.sheet.name}]" if len(wb.sheets) > 1 else ""
        self.setWindowTitle(f"{prefix}{flag}{name}{tab} — qcell")
