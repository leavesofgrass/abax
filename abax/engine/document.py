"""High-level document façade used by the GUI and TUI.

Dispatches open/save to the right backend by file extension:
``.json``/``.abax`` (native), ``.csv``/``.tsv``, ``.xlsx``. Tracks the
current path and dirty state. This is the single entry point both front-ends
call so they never touch backend modules directly.
"""

from __future__ import annotations

from pathlib import Path

from . import excel_io
from ..core.io import csv_io, exchange_io, flatfile_io, markdown_io, notebook_io, r_io, xml_io
from ..core.workbook import Workbook


class Document:
    def __init__(self, workbook: Workbook | None = None, path: Path | None = None) -> None:
        from ..core.undo import UndoStack

        self.workbook = workbook or Workbook()
        self.path = path
        self.dirty = False
        self._undo = UndoStack()

    @property
    def title(self) -> str:
        return self.path.name if self.path else "untitled"

    # --- undo / redo -----------------------------------------------------

    def checkpoint(self, label: str = "", coalesce_key=None) -> None:
        """Snapshot the current workbook state before a mutation.

        ``coalesce_key`` (with a short time window) groups a rapid burst of like
        edits into a single undo step; ``label`` names the action for the history view.
        """
        import time

        self._undo.checkpoint(
            self.workbook.to_envelope(), label, coalesce_key, now=time.monotonic())

    def undo(self) -> bool:
        res = self._undo.undo(self.workbook.to_envelope())
        if res is None:
            return False
        self.workbook.load_envelope(res[0])
        self.dirty = True
        return True

    def redo(self) -> bool:
        res = self._undo.redo(self.workbook.to_envelope())
        if res is None:
            return False
        self.workbook.load_envelope(res[0])
        self.dirty = True
        return True

    def undo_history(self) -> tuple[list[str], list[str]]:
        """``(undo_labels oldest→newest, redo_labels next-first)`` for a history view."""
        return self._undo.undo_labels(), self._undo.redo_labels()

    @property
    def can_undo(self) -> bool:
        return self._undo.can_undo

    @property
    def can_redo(self) -> bool:
        return self._undo.can_redo

    @classmethod
    def open(cls, path: str | Path) -> "Document":
        path = Path(path)
        ext = path.suffix.lower()
        if ext in (".json", ".abax"):
            # Smart load: our own workbook envelope, or any foreign exchange JSON.
            wb = exchange_io.load_json(path)
        elif ext in (".csv",):
            wb = _single(csv_io.load_csv(path))
        elif ext in (".tsv", ".tab"):
            wb = _single(csv_io.load_csv(path, delimiter="\t"))
        elif ext in (".md", ".markdown"):
            wb = _single(markdown_io.load_markdown(path))
        elif ext in (".ipynb",):
            wb = notebook_io.load_notebook(path)
        elif ext in (".r", ".rdata"):
            wb = r_io.load_r(path)
        elif ext in (".xml",):
            wb = xml_io.load_spreadsheetml(path)
        elif ext in (".jsonl", ".ndjson"):
            wb = _single(flatfile_io.load_jsonl(path))
        elif ext in (".fixed",):
            wb = _single(flatfile_io.load_fixed(path))
        elif ext in (".adi", ".adif"):
            from ..core.io import adif_io

            wb = _single(adif_io.load_adif(path))
        elif ext in (".db", ".sqlite", ".sqlite3"):
            from ..core.io import sqlite_io

            wb = sqlite_io.load_database(path)
        elif ext in (".xlsx", ".xlsm"):
            wb = excel_io.load_xlsx(path)
        elif ext in (".parquet", ".pq", ".feather", ".ft"):
            from . import parquet_io

            wb = parquet_io.load_parquet(path)
        elif ext in (".ods",):
            from . import ods_io

            wb = ods_io.load_ods(path)
        else:
            raise ValueError(f"unsupported file type: {ext!r}")
        return cls(wb, path)

    def save(self, path: str | Path | None = None) -> None:
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError("no path to save to")
        ext = target.suffix.lower()
        if ext in (".json", ".abax"):
            self.workbook.save_json(target)
        elif ext == ".csv":
            csv_io.save_csv(self.workbook.sheet, target)
        elif ext in (".tsv", ".tab"):
            csv_io.save_csv(self.workbook.sheet, target, delimiter="\t")
        elif ext in (".md", ".markdown"):
            markdown_io.save_markdown(self.workbook.sheet, target)
        elif ext in (".ipynb",):
            notebook_io.save_notebook(self.workbook, target)
        elif ext in (".r", ".rdata"):
            r_io.save_r(self.workbook, target)
        elif ext in (".xml",):
            xml_io.save_spreadsheetml(self.workbook, target)
        elif ext in (".jsonl", ".ndjson"):
            flatfile_io.save_jsonl(self.workbook.sheet, target)
        elif ext in (".adi", ".adif"):
            from ..core.io import adif_io

            adif_io.save_adif(self.workbook.sheet, target)
        elif ext in (".fixed",):
            flatfile_io.save_fixed(self.workbook.sheet, target)
        elif ext in (".db", ".sqlite", ".sqlite3"):
            from ..core.io import sqlite_io

            sqlite_io.save_table(self.workbook.sheet, target, self.workbook.sheet.name or "Sheet1")
        elif ext in (".xlsx", ".xlsm"):
            excel_io.save_xlsx(self.workbook, target)
        elif ext in (".parquet", ".pq", ".feather", ".ft"):
            from . import parquet_io

            parquet_io.save_parquet(self.workbook, target)
        elif ext in (".ods",):
            from . import ods_io

            ods_io.save_ods(self.workbook, target)
        else:
            raise ValueError(f"unsupported file type: {ext!r}")
        self.path = target
        self.dirty = False

    def mark_dirty(self) -> None:
        self.dirty = True


def _single(sheet) -> Workbook:
    return Workbook.from_sheets([sheet])
