"""DocumentMixin — table<->sheet sync and the cell-editing surface: commit,
clipboard, fill, sort/filter, names, validation, styles, undo/redo, row/column
structure and sheet management. (File open/save/import lives in
:class:`abax.gui.mixin_io.DocumentIOMixin`.)

No mixin calls another (spec §2). Each mixin assumes the host QMainWindow
exposes the shared attributes set up in ``MainWindow._setup_ui`` (``_doc``,
``_table``, ``_formula_bar``, ``_settings``).
"""

from __future__ import annotations

from ._qtcompat import QMessageBox, QTableWidgetSelectionRange
from ..core.reference import index_to_col, to_a1


class DocumentMixin:
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
        """Commit an in-cell edit (called from AbaxTableModel.setData).

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

    # --- cell comments / notes -------------------------------------------

    def edit_comment(self) -> None:
        """Add or edit the comment on the current cell via a text prompt."""
        from ._qtcompat import QInputDialog

        row, col = self._table.currentRow(), self._table.currentColumn()
        if row < 0 or col < 0:
            return
        sheet = self._doc.workbook.sheet
        current = sheet.get_comment(row, col) or ""
        text, ok = QInputDialog.getMultiLineText(
            self, "Cell comment", f"Comment for {to_a1(row, col)}:", current)
        if not ok:
            return
        self._set_comment(row, col, text)

    def delete_comment(self) -> None:
        """Remove the comment on the current cell."""
        row, col = self._table.currentRow(), self._table.currentColumn()
        if row < 0 or col < 0:
            return
        if self._doc.workbook.sheet.get_comment(row, col) is None:
            return
        self._set_comment(row, col, "")

    def _set_comment(self, row: int, col: int, text: str) -> None:
        self._doc.checkpoint(f"comment {to_a1(row, col)}")
        self._doc.workbook.sheet.set_comment(row, col, text)
        self._doc.mark_dirty()
        self.refresh_table()

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
        from .dialogs.sort_dialog import SortDialog

        SortDialog(self).exec()

    def show_filter_dialog(self) -> None:
        from .dialogs.filter_dialog import FilterDialog

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
        from .dialogs.name_manager_dialog import NameManagerDialog

        NameManagerDialog(self).exec()

    # --- data validation -------------------------------------------------

    def show_validation_dialog(self) -> None:
        from .dialogs.validation_dialog import ValidationDialog

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
        from .dialogs.undo_history_dialog import UndoHistoryDialog

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


