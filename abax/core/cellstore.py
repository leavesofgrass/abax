"""The cell-storage seam for :class:`abax.core.sheet.Sheet`.

Today a sheet keeps **every** populated cell resident in a single
``dict[(row, col) -> Cell]``. That is fast and simple, and it is the scaling
ceiling: a workbook with millions of populated cells holds every ``Cell`` object
in memory at once. The *windowed / lazy backing store* track (see the roadmap)
wants to keep only a bounded **hot working set** resident and page cold cells to
a compact on-disk spill, transparently.

This module is the **seam** that makes that swap possible without touching the
~two dozen call sites — in :mod:`~abax.core.sheet` and in six other modules
(`depgraph`, `workbook`, `engine.extloaders`, `gui.mixin_tools`, `tui.editor`,
plus tests) — that read the store as a plain mapping (`.items()`, `.keys()`,
`len()`, `in`, iteration, item get/set/pop).

## Design: a `dict` subclass, not a wrapper

:class:`DictCellStore` is a **subclass of ``dict``**, not a wrapper around one.
That is deliberate:

* Every existing caller uses ordinary mapping operations, several of them
  *outside* ``Sheet``. A ``dict`` subclass is 100% substitutable for all of
  them — zero behavioural change, no call-site churn — so introducing it is
  near-risk-free and the differential recalc fuzz stays green.
* It still gives a real swap point. A future ``WindowedCellStore(DictCellStore)``
  overrides ``__missing__`` (Python's hook for "key absent on lookup") to page a
  cold ``Cell`` back in from the spill file, and evicts from a bounded resident
  set on insert — while ``items()`` / ``keys()`` / ``len()`` continue to work for
  every consumer (they would iterate resident + spilled keys). The dict *is* the
  interface the rest of the engine already programs against.

## Contract a replacement store must honour

:class:`CellStore` documents that contract as a ``Protocol`` for type-checking
and as the checklist a windowed implementation must satisfy. In practice a
subclass gets most of it from ``dict`` for free; the work is in ``__missing__``
(load), ``__setitem__`` (insert + maybe evict), and keeping ``__iter__`` /
``keys`` / ``items`` / ``__len__`` consistent across resident + spilled cells.

Keys are ``(row, col)`` tuples; values are :class:`abax.core.cell.Cell`. The
store holds **only populated cells** — a missing key means an empty cell, and
callers already treat ``store.get(key)`` returning ``None`` as "blank".

Nothing here changes behaviour yet: :class:`DictCellStore` is exactly a ``dict``.
It is the foundation the windowed store builds on.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
from typing import Callable, Iterator, Optional, Protocol, runtime_checkable

from .cells import Cell

_Key = "tuple[int, int]"

# Sentinel so pop() can distinguish "no default given" (raise) from `default=None`.
_MISSING = object()


@runtime_checkable
class CellStore(Protocol):
    """The mapping contract :class:`abax.core.sheet.Sheet` relies on.

    Any backing store — the default :class:`DictCellStore`, or a future
    windowed/lazy store — must behave as a ``{(row, col): Cell}`` mapping across
    at least these operations, which are the ones the engine actually uses:

    * ``store[key] = cell`` / ``store[key]`` — insert / fetch (fetch may raise
      ``KeyError`` for a missing key, like ``dict``);
    * ``store.get(key)`` — fetch or ``None`` (the "blank cell" path);
    * ``store.pop(key, default)`` — remove;
    * ``key in store`` — membership;
    * ``iter(store)`` / ``store.keys()`` — iterate populated keys;
    * ``store.items()`` — iterate ``(key, cell)`` pairs;
    * ``len(store)`` / ``bool(store)`` — population count / emptiness.

    A windowed store satisfies this while keeping only a bounded resident set in
    memory and paging the rest to disk. Because :class:`DictCellStore` subclasses
    ``dict``, ``isinstance(store, CellStore)`` is ``True`` for it and for any
    ``dict`` — the Protocol is documentation + a type-checker aid, not a gate.
    """

    def __getitem__(self, key: _Key) -> "Cell": ...
    def __setitem__(self, key: _Key, value: "Cell") -> None: ...
    def __contains__(self, key: object) -> bool: ...
    def __iter__(self) -> Iterator[_Key]: ...
    def __len__(self) -> int: ...
    def get(self, key: _Key, default=None): ...
    def pop(self, key: _Key, default=None): ...
    def keys(self): ...
    def items(self): ...


class DictCellStore(dict):
    """The default cell store: every populated cell resident in a ``dict``.

    A thin, named ``dict`` subclass — behaviourally identical to the bare ``dict``
    that :class:`Sheet` used before — so it is a drop-in for all existing callers
    (including the ones outside ``Sheet``). Its only job today is to *be the named
    type* at the swap point; a windowed store subclasses it (see the module
    docstring) and overrides ``__missing__`` / ``__setitem__`` to page cold cells.
    """

    __slots__ = ()

    def remap(self, move: Callable[[_Key], "Optional[_Key]"]) -> None:  # noqa: D401
        return _dict_remap(self, move)


def _dict_remap(store: dict, move: Callable[[_Key], "Optional[_Key]"]) -> None:
    """Relocate every key of ``store`` through ``move(key) -> newkey | None``.

    Builds the remapped mapping first, then swaps it in, so a shift that moves
    keys past each other can never overwrite a not-yet-moved cell. Shared by
    :meth:`DictCellStore.remap` (used by ``Sheet`` on row/column insert/delete).
    """
    remapped = {}
    for key, cell in list(store.items()):
        nk = move(key)
        if nk is not None:
            remapped[nk] = cell
    store.clear()
    store.update(remapped)


class BoundedCache(dict):
    """A size-capped ``dict`` for per-cell *recompute* memoization.

    Only for caches whose entries can be dropped freely — a parsed AST, a
    resolved AST — where dropping one costs at most a re-parse of a single
    formula (no recursion, no cascade). NOT for value caches: dropping a cached
    *value* can force a deep recompute cascade that blows the recursion limit.

    With ``capacity=None`` it is a plain unbounded ``dict`` (the default, used
    with :class:`DictCellStore` — zero behaviour change). With a capacity it
    evicts the oldest-inserted entry whenever an insert pushes it over, so a
    windowed sheet's AST caches stay bounded to roughly the working-set size
    regardless of how a full recalc scans cells. Reinserting an existing key
    refreshes its position (so a re-parse after a miss counts as recent).
    """

    __slots__ = ("_cap",)

    def __init__(self, capacity: "int | None" = None) -> None:
        super().__init__()
        self._cap = None if capacity is None else max(1, int(capacity))

    def __setitem__(self, key, value) -> None:
        if dict.__contains__(self, key):
            dict.__delitem__(self, key)          # refresh insertion order
        dict.__setitem__(self, key, value)
        if self._cap is not None:
            while dict.__len__(self) > self._cap:
                dict.__delitem__(self, next(iter(dict.__iter__(self))))


class WindowedCellStore(DictCellStore):
    """A cell store that keeps a bounded **resident window** and spills the rest.

    Same mapping contract as :class:`DictCellStore` (it *is* a ``dict`` subclass,
    so ``items()`` / ``keys()`` / ``len()`` / ``in`` all span resident **and**
    spilled cells for every consumer), but only up to ``capacity`` ``Cell``
    objects are held in memory at once. When an insert pushes the resident set
    over capacity the oldest-inserted cell is **evicted**: its source text is
    written to a small on-disk SQLite spill and the ``Cell`` object is dropped.
    Touching an evicted key (``store[key]`` / ``get``) **pages it back in** via
    ``__missing__``, evicting another if needed. A full ``items()`` scan yields
    spilled cells transiently (without making them resident), so iterating the
    whole sheet — save, a cold recalc — never blows the window.

    **Opt-in, off by default.** ``Sheet`` uses :class:`DictCellStore` unless a
    ``WindowedCellStore`` is passed in, so nothing changes for existing users.

    **What is spilled.** Only ``Cell.raw`` (the source text — the single source of
    truth). ``Cell.value`` / ``_dirty`` are a recompute cache; a paged-in cell is
    fresh + dirty and recomputes on next read, exactly as a just-loaded workbook
    would. So results are identical to :class:`DictCellStore`; only *when* values
    are computed differs. (A cross-check test drives a windowed and a plain sheet
    through identical random edits and asserts identical values.)

    **Eviction is LRU.** Reading a cell (``store[key]`` / ``get``) moves it to the
    most-recently-used end; an insert that overflows evicts from the
    least-recently-used front. Bulk iteration (``items`` / ``keys`` / a full scan)
    deliberately does **not** count as a use, so scanning the whole sheet never
    churns the window.

    **Cache windowing.** When a ``Sheet`` is backed by a windowed store it also
    caps its parsed-AST caches (``_ast_cache`` / ``_rast_cache``) to the same
    ``capacity`` via :class:`BoundedCache` — those are the biggest per-cell
    memory and re-parse cheaply on a miss. It deliberately leaves ``_value_cache``
    unbounded: a value is tiny next to an AST, and keeping values shallowly
    resolves reads of already-computed precedents. Formatting maps
    (cell_formats/styles/borders) are sparse and stay resident.

    **Deep dependency chains.** Long reference chains (``A2=A1+1, …``) evaluate
    correctly regardless of ``capacity`` — a chain deeper than the window simply
    pages through it. (An earlier limitation note blamed the window for deep
    chains yielding ``#CIRC!``; measurement showed the plain store failed the
    same way — the cause was the interpreter's default recursion limit capping
    cold evaluation at a chain ~166 deep on *any* store. The evaluator now
    raises its recursion headroom for the outermost computation — see
    ``_EVAL_RECURSION_LIMIT`` in :mod:`abax.core.sheet` — which handles chains
    ~10k deep; only beyond that does the ``#CIRC!`` backstop fire.)

    Not thread-safe across *different* stores sharing a file; each store owns its
    own private temp spill, guarded by a lock for the background-thread callers.
    """

    # A generous default: the window only matters for very large sheets, and a
    # small window would thrash. Callers tune it for their memory budget.
    DEFAULT_CAPACITY = 50_000

    # dict subclasses can't declare __slots__ meaningfully here (we add attrs).
    def __init__(
        self,
        initial=None,
        *,
        capacity: "int | None" = None,
        spill_dir: "str | None" = None,
    ) -> None:
        super().__init__()
        self.capacity = max(1, int(capacity)) if capacity else self.DEFAULT_CAPACITY
        self._spill_dir = spill_dir
        self._spilled: set = set()          # keys currently on disk (in-memory index)
        self._lock = threading.RLock()
        fd, self._spill_path = tempfile.mkstemp(
            prefix="abax-cellspill-", suffix=".db", dir=spill_dir
        )
        os.close(fd)
        self._db: "sqlite3.Connection | None" = sqlite3.connect(
            self._spill_path, check_same_thread=False
        )
        self._db.execute("CREATE TABLE spill (r INT, c INT, raw TEXT, PRIMARY KEY (r, c))")
        self._db.commit()
        if initial:
            for key, cell in dict(initial).items():
                self[key] = cell

    # --- spill I/O (raw text only) ----------------------------------------

    def _spill_put(self, key: _Key, raw: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO spill (r, c, raw) VALUES (?, ?, ?)",
            (key[0], key[1], raw),
        )

    def _spill_take(self, key: _Key) -> str:
        cur = self._db.execute("SELECT raw FROM spill WHERE r = ? AND c = ?", key)
        row = cur.fetchone()
        self._db.execute("DELETE FROM spill WHERE r = ? AND c = ?", key)
        return row[0] if row else ""

    def _spill_peek(self, key: _Key) -> str:
        cur = self._db.execute("SELECT raw FROM spill WHERE r = ? AND c = ?", key)
        row = cur.fetchone()
        return row[0] if row else ""

    def _touch(self, key: _Key) -> Cell:
        """Move a resident key to the MRU end (dict preserves insertion order)."""
        cell = dict.pop(self, key)
        dict.__setitem__(self, key, cell)
        return cell

    def _evict_if_full(self) -> None:
        """Evict least-recently-used resident cells until within capacity."""
        while dict.__len__(self) > self.capacity:
            okey = next(iter(dict.__iter__(self)))   # LRU = front (oldest touched)
            ocell = dict.pop(self, okey)
            self._spill_put(okey, ocell.raw)
            self._spilled.add(okey)

    # --- mapping surface (spans resident + spilled) -----------------------

    def __setitem__(self, key: _Key, cell: Cell) -> None:
        with self._lock:
            if key in self._spilled:
                self._db.execute("DELETE FROM spill WHERE r = ? AND c = ?", key)
                self._spilled.discard(key)
            elif dict.__contains__(self, key):
                dict.pop(self, key)          # re-insert at end (keep FIFO order sane)
            dict.__setitem__(self, key, cell)
            self._evict_if_full()

    def __getitem__(self, key: _Key) -> Cell:
        with self._lock:
            if dict.__contains__(self, key):
                return self._touch(key)      # MRU on read
        return dict.__getitem__(self, key)   # absent -> __missing__ (spilled / KeyError)

    def __missing__(self, key: _Key) -> Cell:
        # Called by ``dict.__getitem__`` when key is not resident.
        with self._lock:
            if key in self._spilled:
                raw = self._spill_take(key)
                self._spilled.discard(key)
                cell = Cell(raw)
                dict.__setitem__(self, key, cell)   # paged in = MRU end
                self._evict_if_full()
                return cell
        raise KeyError(key)

    def get(self, key: _Key, default=None):
        with self._lock:
            if dict.__contains__(self, key):
                return self._touch(key)      # MRU on read
            if key in self._spilled:
                return self[key]             # triggers __missing__ (pages in)
            return default

    def pop(self, key: _Key, default=_MISSING):
        with self._lock:
            if dict.__contains__(self, key):
                return dict.pop(self, key)
            if key in self._spilled:
                raw = self._spill_take(key)
                self._spilled.discard(key)
                return Cell(raw)
            if default is _MISSING:
                raise KeyError(key)
            return default

    def __contains__(self, key: object) -> bool:
        return dict.__contains__(self, key) or key in self._spilled

    def __len__(self) -> int:
        return dict.__len__(self) + len(self._spilled)

    def __iter__(self) -> Iterator[_Key]:
        yield from dict.__iter__(self)
        yield from list(self._spilled)

    def keys(self):
        return iter(self)

    def values(self):
        for _key, cell in self.items():
            yield cell

    def items(self):
        # Resident cells directly; spilled cells transiently (peek, don't page
        # in) so a full scan keeps the window bounded.
        for key in list(dict.__iter__(self)):
            yield key, dict.__getitem__(self, key)
        for key in list(self._spilled):
            yield key, Cell(self._spill_peek(key))

    def clear(self) -> None:
        with self._lock:
            dict.clear(self)
            self._spilled.clear()
            if self._db is not None:
                self._db.execute("DELETE FROM spill")
                self._db.commit()

    def update(self, other=(), /, **kwds) -> None:  # noqa: D401 - dict override
        pairs = other.items() if hasattr(other, "items") else other
        for key, cell in pairs:
            self[key] = cell
        for key, cell in kwds.items():
            self[key] = cell

    def copy(self) -> "DictCellStore":
        """A plain resident snapshot (all cells paged in) — semantics unambiguous."""
        return DictCellStore(dict(self.items()))

    def remap(self, move: Callable[[_Key], "Optional[_Key]"]) -> None:
        with self._lock:
            pairs = []
            for key, cell in list(self.items()):
                nk = move(key)
                if nk is not None:
                    pairs.append((nk, cell))
            self.clear()
            for nk, cell in pairs:
                self[nk] = cell

    # --- lifecycle --------------------------------------------------------

    def resident_count(self) -> int:
        """How many cells are currently in memory (for tests / diagnostics)."""
        return dict.__len__(self)

    def close(self) -> None:
        """Close the spill DB and delete its temp file. Idempotent."""
        db, self._db = self._db, None
        if db is not None:
            try:
                db.close()
            finally:
                try:
                    os.unlink(self._spill_path)
                except OSError:
                    pass

    def __del__(self) -> None:  # best-effort cleanup
        try:
            self.close()
        except Exception:
            pass
