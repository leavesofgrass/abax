"""Incremental recalc dependency graph — the inverse of :mod:`precedents`.

Editing one cell today clears **every** sheet's value cache
(:meth:`abax.core.workbook.Workbook.invalidate_caches`), because any formula
anywhere *might* depend on the edit. That is always correct but O(all cells): a
single keystroke throws away the whole workbook's memoized values.

This module builds a **reverse-dependents index** so an edit invalidates only
the cells it can actually affect — the edited cell plus the transitive closure
of formulas whose *static precedents* reach it — plus an **always-dirty** set for
formulas whose true inputs cannot be known statically (volatiles like ``NOW`` /
``RAND``, dynamic refs like ``INDIRECT`` / ``OFFSET``, spill refs ``A1#``,
defined-name references, and unknown user macros).

Soundness is by **over-approximation**: for every formula cell we either index a
*superset* of its true precedents, or mark it always-dirty, or fall back to the
verbatim full clear. Extra invalidations only cost a recompute; a *missed*
dependent would serve a stale value, which must never happen. Anything the
static analysis can't prove — a parse failure, an unknown macro, a workbook that
currently spills, a structural edit — degrades to the blanket clear.

Phase B (see :meth:`abax.core.workbook.Workbook.invalidate_dependents`): a spill's
extent changes only when its anchor recomputes, which happens iff the anchor is in
the edit's static closure. So spilling workbooks stay incremental — only edits that
*interact* with a spill (redefine/remove an array formula, land inside a live spill
region, unblock a ``#SPILL!``, or feed an anchor) take the sound full clear; every
other edit is scoped precisely even when spills exist elsewhere. Standalone sheets
(no workbook) keep the blanket clear. See ``dev/roadmap.md`` (WS1).

Pure stdlib — the ``abax.core`` invariant. Toggle the whole feature with
:data:`ABAX_INCREMENTAL` (``False`` restores the blanket-clear behaviour exactly,
for instant rollback).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from . import ast_nodes as A
from .errors import FormulaError
from .parser import parse
from .reference import parse_a1, parse_range

# Master switch. False => byte-for-byte revert to the global clear. Overridable
# via the environment (``ABAX_INCREMENTAL=0``) for an instant, no-code rollback
# and for running the suite both ways.
ABAX_INCREMENTAL = os.environ.get("ABAX_INCREMENTAL", "1") not in ("0", "false", "False")

# Functions whose value or precedents cannot be captured by a static AST walk:
#   volatile     — value changes with no input change
#   dynamic-ref  — the cells they read are computed from runtime values
ALWAYS_DIRTY_FUNCS = frozenset({
    "NOW", "TODAY", "RAND", "RANDBETWEEN", "RANDARRAY",  # volatile
    "REST", "WEBSOCKET", "WEBSERVICE",                    # live data (push-updated)
    "INDIRECT", "OFFSET",                                 # dynamic reference
})

# Bare identifiers that are literal constants, not defined-name references.
_CONSTANT_NAMES = frozenset({"TRUE", "FALSE"})

# CellKey = (sheet_name: str, row: int, col: int)
# Rect    = (sheet_name: str, r1: int, c1: int, r2: int, c2: int)


def _known_pure_funcs() -> frozenset:
    """Every registered function name MINUS the always-dirty set.

    Built from the live registries so a *user macro* (not registered here) is
    treated conservatively as always-dirty. Imported lazily to avoid an import
    cycle (``functions`` transitively imports low-level core modules).
    """
    from .functions import CONTEXT_FUNCTIONS, FUNCTIONS, LAZY_FUNCTIONS

    return frozenset(set(FUNCTIONS) | set(LAZY_FUNCTIONS) | set(CONTEXT_FUNCTIONS)) - ALWAYS_DIRTY_FUNCS


@dataclass
class Analysis:
    """The static precedents of one formula.

    ``ok`` is False when the formula could not be parsed — the caller must then
    fall back to the full clear (its true inputs are unknown). ``always_dirty``
    is True when the formula parsed but uses a construct whose real inputs are
    not statically knowable (volatile / dynamic ref / spill ref / defined name /
    unknown macro).
    """

    cells: set          # set[CellKey] — single-cell precedents
    rects: list         # list[Rect]   — range precedents, never expanded
    always_dirty: bool
    ok: bool


def _canon_sheet(node_sheet: str, owner: str, sheet_names) -> tuple[str, bool]:
    """Resolve a node's sheet qualifier to a canonical workbook sheet name.

    Empty qualifier => the owner sheet. A qualifier naming a sheet we do not
    have returns ``(owner, True)`` — *unknown* — so the caller marks the formula
    always-dirty (its precedents can't be located; matches how the evaluator
    surfaces the ref as ``#REF!``).
    """
    if not node_sheet:
        return owner, False
    for nm in sheet_names:
        if nm == node_sheet:
            return nm, False
    low = node_sheet.lower()
    for nm in sheet_names:
        if nm.lower() == low:
            return nm, False
    return owner, True


def analyze(raw: str, owner: str, sheet_names) -> Analysis:
    """Statically analyse a raw formula into its precedent cells / rectangles.

    ``owner`` is the canonical name of the sheet the formula lives on and
    ``sheet_names`` the workbook's canonical sheet names. A non-formula has no
    precedents; a parse failure returns ``ok=False``; an unknowable construct
    returns ``always_dirty=True``.
    """
    cells: set = set()
    rects: list = []
    dirty = [False]
    if not isinstance(raw, str) or not raw.startswith("="):
        return Analysis(cells, rects, False, True)
    try:
        ast = parse(raw[1:])
    except FormulaError:
        return Analysis(cells, rects, False, False)
    known_pure = _known_pure_funcs()

    def walk(node) -> None:
        if isinstance(node, A.Ref):
            name, unknown = _canon_sheet(node.sheet, owner, sheet_names)
            if unknown:
                dirty[0] = True
                return
            try:
                r, c = parse_a1(node.text.replace("$", ""))
            except Exception:
                dirty[0] = True
                return
            cells.add((name, r, c))
        elif isinstance(node, A.Range):
            name, unknown = _canon_sheet(node.sheet, owner, sheet_names)
            if unknown:
                dirty[0] = True
                return
            try:
                r1, c1, r2, c2 = parse_range(node.text.replace("$", ""))
            except Exception:
                dirty[0] = True
                return
            rects.append((name, r1, c1, r2, c2))
        elif isinstance(node, A.SpillRef):
            dirty[0] = True  # runtime-sized block; true deps unknown statically
        elif isinstance(node, A.Name):
            if node.text not in _CONSTANT_NAMES:
                dirty[0] = True  # a defined-name reference — resolved at runtime
        elif isinstance(node, A.Func):
            if node.name in ALWAYS_DIRTY_FUNCS or node.name not in known_pure:
                dirty[0] = True
            for arg in node.args:
                walk(arg)
        elif isinstance(node, A.Unary):
            walk(node.operand)
        elif isinstance(node, A.Binary):
            walk(node.left)
            walk(node.right)
        elif isinstance(node, A.ArrayLiteral):
            for row in node.rows:
                for el in row:
                    walk(el)
        # Number / String / Error: no references.

    try:
        walk(ast)
    except RecursionError:
        return Analysis(set(), [], True, True)  # pathologically deep — be safe
    return Analysis(cells, rects, dirty[0], True)


class DepGraph:
    """Workbook-scoped reverse-dependents index.

    ``cell_rdeps`` inverts single-cell references (precedent -> dependents);
    ``range_rdeps`` holds range references as *unexpanded* rectangles per sheet
    (so ``=SUM(A1:A100000)`` costs one entry, not 100k edges); ``forward`` keeps
    each cell's own outgoing edges so a re-edit can remove them precisely (no
    index drift); ``always_dirty`` are the BFS seeds invalidated on every edit.
    """

    def __init__(self) -> None:
        self.cell_rdeps: dict = {}   # CellKey -> set[CellKey]
        self.range_rdeps: dict = {}  # sheet_name -> list[(r1, c1, r2, c2, dep_key)]
        self.forward: dict = {}      # CellKey -> (cells tuple, rects tuple)
        self.always_dirty: set = set()
        self._built = False

    @property
    def is_built(self) -> bool:
        return self._built

    def clear(self) -> None:
        self.cell_rdeps.clear()
        self.range_rdeps.clear()
        self.forward.clear()
        self.always_dirty.clear()
        self._built = False

    def _add_edges(self, key, an: Analysis) -> None:
        for pc in an.cells:
            self.cell_rdeps.setdefault(pc, set()).add(key)
        for (sname, r1, c1, r2, c2) in an.rects:
            self.range_rdeps.setdefault(sname, []).append((r1, c1, r2, c2, key))
        if an.always_dirty or not an.ok:
            self.always_dirty.add(key)
        self.forward[key] = (tuple(an.cells), tuple(an.rects))

    def _remove_edges(self, key) -> None:
        rec = self.forward.pop(key, None)
        self.always_dirty.discard(key)
        if rec is None:
            return
        cells, rects = rec
        for pc in cells:
            s = self.cell_rdeps.get(pc)
            if s is not None:
                s.discard(key)
                if not s:
                    del self.cell_rdeps[pc]
        for sname in {t[0] for t in rects}:
            lst = self.range_rdeps.get(sname)
            if lst:
                kept = [t for t in lst if t[4] != key]
                if kept:
                    self.range_rdeps[sname] = kept
                else:
                    del self.range_rdeps[sname]

    def build(self, sheets) -> None:
        """Full scan: index every formula cell across ``sheets``."""
        self.clear()
        names = [s.name for s in sheets]
        for sh in sheets:
            name = sh.name
            for (r, c), cell in sh._cells.items():
                if cell.raw.startswith("="):
                    self._add_edges((name, r, c), analyze(cell.raw, name, names))
        self._built = True

    def on_cell_changed(self, sheets, owner_name, row, col, raw) -> bool:
        """Re-index one edited cell. Return True if the new formula analysed
        cleanly, False if it forces a full-clear fallback for this edit."""
        key = (owner_name, row, col)
        self._remove_edges(key)
        if not (isinstance(raw, str) and raw.startswith("=")):
            return True  # literal or cleared cell — no outgoing edges
        an = analyze(raw, owner_name, [s.name for s in sheets])
        self._add_edges(key, an)
        return an.ok

    def closure(self, seeds) -> set:
        """Every cell reachable from ``seeds`` through the reverse edges,
        including the seeds themselves. Range membership is tested against the
        unexpanded rectangles. A ``visited`` set terminates on cycles."""
        seen = set(seeds)
        stack = list(seen)
        while stack:
            sname, r, c = stack.pop()
            deps = self.cell_rdeps.get((sname, r, c))
            if deps:
                for d in deps:
                    if d not in seen:
                        seen.add(d)
                        stack.append(d)
            lst = self.range_rdeps.get(sname)
            if lst:
                for (r1, c1, r2, c2, dep) in lst:
                    if r1 <= r <= r2 and c1 <= c <= c2 and dep not in seen:
                        seen.add(dep)
                        stack.append(dep)
        return seen
