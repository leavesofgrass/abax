"""High-level document façade used by the GUI and TUI.

Dispatches open/save to the right backend by file extension:
``.json``/``.abax`` (native), ``.csv``/``.tsv``, ``.xlsx``, ``.parquet``,
``.ods``, ``.h5``/``.hdf5`` (read-only), and more. Tracks the current path and
dirty state. This is the single entry point both front-ends call so they never
touch backend modules directly.
"""

from __future__ import annotations

from pathlib import Path

from . import excel_io
from ..core.io import csv_io, exchange_io, flatfile_io, markdown_io, notebook_io, r_io, xml_io
from ..core.workbook import Workbook


class Document:
    def __init__(self, workbook: Workbook | None = None, path: Path | None = None,
                 windowed_capacity: int | None = None) -> None:
        from ..core.undo import UndoStack

        self.workbook = workbook or Workbook()
        self.path = path
        self.dirty = False
        self._undo = UndoStack()
        # The windowed_store_capacity policy this document was opened under
        # (``Document.open`` retains it). Undo/redo rebuild the workbook from an
        # envelope snapshot, so they re-apply the same policy — a large windowed
        # workbook stays on the bounded store across a restore instead of
        # rehydrating every cell into RAM. ``None`` (the default for direct
        # constructions) means no policy: restores stay on plain stores.
        self.windowed_capacity = windowed_capacity

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
        # Restore under the document's windowing policy so a large workbook
        # lands back on the bounded store (see __init__).
        self.workbook.load_envelope(res[0], windowed_capacity=self.windowed_capacity)
        self.dirty = True
        return True

    def redo(self) -> bool:
        res = self._undo.redo(self.workbook.to_envelope())
        if res is None:
            return False
        self.workbook.load_envelope(res[0], windowed_capacity=self.windowed_capacity)
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
    def open(cls, path: str | Path, windowed_capacity: int = 0) -> "Document":
        """Load a file into a Document.

        ``windowed_capacity`` is the ``windowed_store_capacity`` setting:
        ``> 0`` windows every sheet into a bounded, disk-spilling cell store
        at that capacity; ``0`` (the default) **auto-windows only large
        sheets** (>= ``AUTO_WINDOW_THRESHOLD`` populated cells, at the store's
        default capacity); ``< 0`` never windows.

        The native format applies the policy **during** load — a sheet that
        will be windowed streams straight into the windowed store, so opening
        a huge ``.abax``/``.json`` never materializes every cell in memory
        first. Every other format loads plain and then migrates via
        ``apply_windowing_policy`` (a no-op for the already-windowed native
        sheets).

        The policy is retained on the returned document
        (``self.windowed_capacity``), and undo/redo re-apply it when they
        rebuild the workbook from a snapshot — so one Ctrl+Z on a windowed
        workbook cannot silently rehydrate every cell into RAM.
        """
        path = Path(path)
        ext = path.suffix.lower()
        if ext in (".json", ".abax"):
            # Smart load: our own workbook envelope, or any foreign exchange JSON.
            # The windowing policy rides into the loader so a to-be-windowed
            # sheet is built on the windowed store from the first cell.
            wb = exchange_io.load_json(path, windowed_capacity=windowed_capacity)
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

            sheet = adif_io.load_adif(path)
            _enrich_dxcc(sheet)
            wb = _single(sheet)
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
        elif ext in (".dta", ".sav", ".zsav", ".por"):
            from . import statfiles

            wb = statfiles.load_statfile(path)
        elif ext in (".h5", ".hdf5"):
            from . import hdf5_io

            wb = hdf5_io.load_hdf5(path)
        else:
            raise ValueError(f"unsupported file type: {ext!r}")
        wb.apply_windowing_policy(windowed_capacity)
        # Retain the policy on the document so undo/redo restores re-apply it.
        return cls(wb, path, windowed_capacity=windowed_capacity)

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


def _enrich_dxcc(sheet) -> None:
    """Append a ``DXCC`` column to a logbook sheet, resolved from each ``CALL``.

    Best-effort: a sheet with a header row containing ``CALL`` gets a new column
    of DXCC entity names (blank where the callsign is unknown). Does nothing if
    there is no CALL column or the DXCC data is unavailable."""
    try:
        from ..core.science.dxcc import entity_for_call
    except Exception:  # noqa: BLE001 - optional enrichment, never fatal
        return
    nr, nc = sheet.used_bounds()
    if nr < 1 or nc < 1:
        return
    headers = [str(sheet.get_value(0, c) or "").strip().upper() for c in range(nc)]
    if "CALL" not in headers or "DXCC" in headers:
        return
    call_col = headers.index("CALL")
    dxcc_col = nc
    sheet.set_cell(0, dxcc_col, "DXCC")
    for r in range(1, nr):
        call = sheet.get_value(r, call_col)
        if call:
            entity = entity_for_call(str(call))
            if entity:
                sheet.set_cell(r, dxcc_col, entity)
