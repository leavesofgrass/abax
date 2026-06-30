"""DocumentIOMixin -- file lifecycle: new / open / save / import and the
background IOWorker plumbing (progress, error, restore) plus the recent-files
list and the window title.

Split out of :mod:`qcell.gui.mixin_document` so the cell-editing surface and the
file-I/O surface live apart. No mixin calls another by name (spec section 2);
these methods only touch the shared host attributes (``_doc``, ``_table``,
``_formula_bar``, ``_settings``, ``_progress``) and host methods like
``refresh_table`` / ``commit_table_to_sheet`` via ``self``.
"""

from __future__ import annotations

from pathlib import Path

from ._qtcompat import QFileDialog, QMessageBox

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


class DocumentIOMixin:
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
                     busy_msg=f"opening {Path(path).name}...")

    def _open_succeeded(self, doc) -> None:
        self._doc = doc
        if doc.path:
            self._remember_recent(str(doc.path))
        self.refresh_table()
        self._update_title()
        self._set_status(f"opened {doc.title}")

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
                     busy_msg=f"importing {Path(path).name}...")

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
                     busy_msg=f"saving {target.name}...")

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
            prefix = "* REL  " if rec.relative else "* REC  "
        else:
            prefix = ""
        wb = self._doc.workbook
        tab = f" [{wb.sheet.name}]" if len(wb.sheets) > 1 else ""
        self.setWindowTitle(f"{prefix}{flag}{name}{tab} — qcell")
