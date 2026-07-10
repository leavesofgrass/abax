"""External workbook references — the hub behind ``=[Book.abax]Sheet1!A1``.

A formula may reference a cell in *another*, closed workbook by qualifying the
sheet with a bracketed file name: ``[Book.abax]Sheet1!A1`` (or the quoted form
``'[Book.abax]Sheet1'!A1`` when the name has spaces). The tokenizer accepts the
bracket prefix and the parser keeps it on the ref node's sheet string; when the
evaluator's resolver (:meth:`abax.core.sheet.Sheet._resolve`) sees a sheet name
beginning with ``[`` it hands the lookup to the process-wide :data:`HUB` here.

The referenced workbook is loaded **once, in the background**, and cached — the
first lookup returns ``#N/A`` and, when the load finishes, a bumped *generation*
counter nudges the front-end (the same GUI/TUI poll that drives live data) to
recalc, at which point the value appears. Because an external sheet is unknown to
the dependency graph it is treated as always-dirty, so no per-cell wiring is
needed for the refresh.

Security — consent gated, off by default
-----------------------------------------
Reading another file the moment a workbook opens is a side effect a malicious
``.abax`` should not get for free, so the hub starts **disabled**: until the user
opts in (settings ``external_refs_enabled``), every external ref resolves to
``#OFF!`` and no file is read. Paths are resolved relative to the open workbook's
directory (set via :meth:`ExternalRefHub.set_base_dir`) and only known workbook
extensions are loaded. The loader is injected/lazy so this module stays within
the pure-core layer and is unit-testable with a fake loader.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Callable

from .errors import CellError

#: Shown when external refs are disabled (mirrors live data's marker).
OFF_MARKER = "#OFF!"

#: Workbook file extensions the hub is willing to load. The native formats are
#: listed here for the pure-core path; the full set (adding .xlsx/.csv/.tsv via
#: the engine loaders) is ``engine.extloaders.SUPPORTED_SUFFIXES``, consulted
#: lazily in ``_resolve_path`` so core stays import-clean when engine is absent.
ALLOWED_SUFFIXES = (".abax", ".json")

_EXTERNAL_RE = re.compile(r"^\[([^\]]+)\](.*)$")

# A loader turns a resolved path into an object exposing
# ``get_sheet(name) -> sheet`` / ``sheet.get_value(row, col)``.
Loader = Callable[[Path], Any]


def parse_external(sheet_name: str) -> "tuple[str, str] | None":
    """Split ``[Book.abax]Sheet1`` into ``("Book.abax", "Sheet1")``.

    Returns ``None`` if *sheet_name* is not an external qualifier. An empty sheet
    part (``[Book.abax]``) yields ``("Book.abax", "")`` — the workbook's first
    sheet.
    """
    m = _EXTERNAL_RE.match(sheet_name)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def _default_loader(path: Path) -> Any:
    """Load a workbook via the engine loaders (imported lazily to stay in core).

    Routes by extension: native .abax/.json through Document, and .xlsx/.csv/.tsv
    through the read-only external loaders (values only — an external xlsx's
    formulas are never evaluated).
    """
    from ..engine.extloaders import load_external

    return load_external(path)


class _Book:
    """A cache slot for one external workbook: loading / loaded / errored."""

    __slots__ = ("workbook", "error", "loading")

    def __init__(self) -> None:
        self.workbook: Any = None
        self.error: str | None = None
        self.loading = True


class ExternalRefHub:
    """Process-wide cache + background loader for closed-workbook references."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._books: dict[str, _Book] = {}     # resolved path str -> slot
        self._generation = 0
        self._enabled = False
        self._base_dir: Path | None = None
        self.loader: Loader = _default_loader

    # -- consent + configuration -------------------------------------------

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, flag: bool) -> None:
        flag = bool(flag)
        with self._lock:
            changed = flag != self._enabled
            self._enabled = flag
        if not flag:
            self.clear()
        elif changed:
            self._bump()

    def set_base_dir(self, path: "str | Path | None") -> None:
        """Directory that bare/relative external paths resolve against."""
        with self._lock:
            self._base_dir = Path(path) if path else None

    # -- generation counter ------------------------------------------------

    def generation(self) -> int:
        with self._lock:
            return self._generation

    def _bump(self) -> None:
        with self._lock:
            self._generation += 1

    def clear(self) -> None:
        """Forget every cached workbook (on disable / manual refresh)."""
        with self._lock:
            self._books.clear()
        self._bump()

    def book_count(self) -> int:
        with self._lock:
            return len(self._books)

    # -- path resolution + security ----------------------------------------

    def _resolve_path(self, workbook_ref: str) -> "Path | None":
        p = Path(workbook_ref)
        if not p.is_absolute():
            with self._lock:
                base = self._base_dir
            if base is None:
                return None
            p = base / p
        # Prefer the engine's full suffix set (native + xlsx/csv/tsv); fall back
        # to the native-only tuple if engine is unavailable (pure-core install).
        try:
            from ..engine.extloaders import SUPPORTED_SUFFIXES as allowed
        except Exception:  # noqa: BLE001
            allowed = ALLOWED_SUFFIXES
        if p.suffix.lower() not in allowed:
            return None
        return p

    # -- lookup ------------------------------------------------------------

    def lookup(self, workbook_ref: str, sheet: str, row: int, col: int) -> Any:
        """Resolve one external cell to a value or a :class:`CellError`.

        ``#OFF!`` when disabled; ``#N/A`` while the workbook loads; ``#REF!`` if
        the path is disallowed/missing or the sheet/cell cannot be found.
        """
        if not self.enabled:
            return OFF_MARKER
        path = self._resolve_path(workbook_ref)
        if path is None:
            return CellError(CellError.REF)
        key = str(path)

        with self._lock:
            book = self._books.get(key)
            if book is None:
                book = _Book()
                self._books[key] = book
                start = True
            else:
                start = False
        if start:
            self._spawn_load(key, path)

        if book.loading:
            return CellError(CellError.NA)
        if book.error is not None or book.workbook is None:
            return CellError(CellError.REF)
        return self._read(book.workbook, sheet, row, col)

    def _spawn_load(self, key: str, path: Path) -> None:
        def _run() -> None:
            book = self._books.get(key)
            if book is None:
                return
            try:
                if not path.is_file():
                    raise FileNotFoundError(path)
                wb = self.loader(path)
            except Exception as exc:  # noqa: BLE001 — record, never crash
                book.error = f"{type(exc).__name__}: {exc}"
                book.workbook = None
            else:
                book.workbook = wb
                book.error = None
            book.loading = False
            self._bump()

        threading.Thread(target=_run, name=f"externref-{key}", daemon=True).start()

    @staticmethod
    def _read(workbook: Any, sheet: str, row: int, col: int) -> Any:
        try:
            target = workbook.get_sheet(sheet) if sheet else workbook.sheet
        except Exception:  # noqa: BLE001
            return CellError(CellError.REF)
        if target is None:
            return CellError(CellError.REF)
        try:
            value = target.get_value(row, col)
        except Exception:  # noqa: BLE001
            return CellError(CellError.REF)
        return value


#: Process-wide default hub used by the evaluator's resolver and the app.
HUB = ExternalRefHub()
