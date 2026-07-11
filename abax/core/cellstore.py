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

from typing import TYPE_CHECKING, Iterator, Protocol, runtime_checkable

if TYPE_CHECKING:  # avoid importing Cell at module load (keeps this light)
    from .cells import Cell

_Key = "tuple[int, int]"


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
