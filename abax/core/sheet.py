"""The `Sheet` — a sparse grid of cells with lazy, memoized recalculation.

Cells are stored sparsely in a dict keyed by ``(row, col)``. Values are
computed on demand and cached; any edit clears the value cache so dependents
recompute. Circular references are detected during evaluation and surface as
``#CIRC!`` rather than a Python ``RecursionError``.

This module is the public face of the core engine for the engine/GUI/TUI
layers above it.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from .cells import Cell
from .errors import CellError, FormulaError
from .evaluator import EvalContext, evaluate
from .lambda_fns import LambdaValue
from .parser import parse
from .reference import parse_a1, to_a1
from .spill import to_grid

# Functions that can evaluate to a dynamic array (and therefore spill). A formula
# is a *spill candidate* if it calls any of these; only candidates are re-walked
# during the spill pass, so a sheet with no array formulas pays nothing.
ARRAY_FUNCTIONS = frozenset({
    "UNIQUE", "SORT", "SORTBY", "FILTER", "SEQUENCE", "RANDARRAY", "TRANSPOSE",
    "VSTACK", "HSTACK", "TAKE", "DROP", "CHOOSEROWS", "CHOOSECOLS", "TOROW",
    "TOCOL", "EXPAND", "WRAPROWS", "WRAPCOLS",
    # Array-returning statistics (Wave H) that also spill.
    "FREQUENCY", "MODE.MULT", "TREND", "GROWTH", "LINEST", "LOGEST",
    # Matrix functions that spill.
    "MMULT", "MINVERSE", "MUNIT",
    # Wave I text splitter and the LET/LAMBDA functional helpers — all can
    # return arrays (REDUCE folds to a scalar and LAMBDA is a value, so
    # neither is listed).
    "TEXTSPLIT", "LET", "MAP", "SCAN", "BYROW", "BYCOL", "MAKEARRAY",
})


# A spill-range reference like ``A1#`` / ``$A$1#`` (the '#' follows a row digit,
# which never happens in an error literal such as ``#NAME?``).
_SPILL_REF_RE = re.compile(r"[0-9]#")

# A range that is an operand of an operator broadcasts to an array (e.g.
# ``A1:A3*2``, ``2+A1:A3``, ``A1:A3>9``) — but not a bare ``SUM(A1:A3)``, where the
# range sits between a paren/comma and is not adjacent to an operator.
_RANGE = r"\$?[A-Za-z]+\$?[0-9]+:\$?[A-Za-z]+\$?[0-9]+"
_ARROP = r"[-+*/^&%<>=]"
_BROADCAST_RE = re.compile(rf"{_ARROP}\s*{_RANGE}|{_RANGE}\s*{_ARROP}")


def _is_array_candidate(formula_upper: str) -> bool:
    """Cheap test: could an upper-cased formula body evaluate to an array — i.e.
    does it call an array function, use a spill (``A1#``) reference, an inline
    array constant (``{...}``), or apply an operator to a range (broadcasting)?"""
    if "{" in formula_upper:
        return True
    if _SPILL_REF_RE.search(formula_upper) or _BROADCAST_RE.search(formula_upper):
        return True
    return any(fn + "(" in formula_upper for fn in ARRAY_FUNCTIONS)


class Sheet:
    def __init__(self, name: str = "Sheet1") -> None:
        self.name = name
        # Set by the owning Workbook so cross-sheet refs (Sheet2!A1) resolve.
        self.workbook = None
        # Conditional-formatting rules (core.condformat.CondRule); applied by the
        # GUI/TUI when rendering, persisted in the workbook envelope.
        self.cond_rules: list = []
        # Per-cell number-format specs (core.cellformat); persisted likewise.
        self.cell_formats: dict[tuple[int, int], str] = {}
        # Per-cell visual styles (core.cellstyle.CellStyle); persisted likewise.
        self.cell_styles: dict[tuple[int, int], Any] = {}
        # Per-cell comments/notes (plain text); metadata only, not formula inputs.
        # Persisted likewise; shown as a marker + tooltip by the GUI.
        self.cell_comments: dict[tuple[int, int], str] = {}
        # Data-validation rules over ranges: list of (r1, c1, r2, c2, ValidationRule).
        self.validations: list = []
        self._cells: dict[tuple[int, int], Cell] = {}
        # Incremental extent of ``_cells`` (excludes spills): adds bump the maxes
        # in O(1); a delete of a boundary cell marks it dirty for a lazy rescan.
        # Keeps used_bounds() — called on every render/export — off the full scan.
        self._cells_max_row = -1
        self._cells_max_col = -1
        self._bounds_dirty = True
        self._ast_cache: dict[tuple[int, int], Any] = {}
        # Name-resolved AST cache: key -> (names_version, resolved_ast). Resolving
        # defined names rewrites the whole tree, so we memoize the result and only
        # redo it when the cell's formula or the name registry actually changes.
        self._rast_cache: dict[tuple[int, int], tuple[int, Any]] = {}
        self._value_cache: dict[tuple[int, int], Any] = {}
        self._computing: set[tuple[int, int]] = set()
        # --- dynamic-array spill state ---
        # Formula cells that may produce an array (maintained on every edit).
        self._anchor_cells: set[tuple[int, int]] = set()
        # Every cell covered by a spill -> its anchor cell (incl. the anchor).
        self._spill_anchor: dict[tuple[int, int], tuple[int, int]] = {}
        # Anchor cell -> the spilled 2-D grid (list of rows).
        self._spill_grid: dict[tuple[int, int], list] = {}
        # Anchor cells whose spill is blocked (render as #SPILL!).
        self._spill_error: set[tuple[int, int]] = set()
        # Recompute the spill map lazily, once per invalidation cycle.
        self._spill_dirty: bool = True
        self._spilling: bool = False  # reentrancy guard for the spill pass

    # --- editing ----------------------------------------------------------

    def set(self, ref: str, raw: str) -> None:
        """Set a cell by A1 reference, e.g. ``sheet.set("B2", "=A1*2")``."""
        row, col = parse_a1(ref)
        self.set_cell(row, col, raw)

    def set_cell(self, row: int, col: int, raw: str) -> None:
        key = (row, col)
        if raw == "":
            if self._cells.pop(key, None) is not None and (
                row == self._cells_max_row or col == self._cells_max_col):
                self._bounds_dirty = True  # a boundary cell went away — rescan
        else:
            self._cells[key] = Cell(raw)
            if row > self._cells_max_row:
                self._cells_max_row = row
            if col > self._cells_max_col:
                self._cells_max_col = col
        self._ast_cache.pop(key, None)
        self._rast_cache.pop(key, None)
        # Track whether this cell is a dynamic-array anchor candidate.
        if raw.startswith("=") and _is_array_candidate(raw.upper()):
            self._anchor_cells.add(key)
        else:
            self._anchor_cells.discard(key)
        self._spill_dirty = True
        self._invalidate_after_edit(row, col)

    def _invalidate_after_edit(self, row: int, col: int) -> None:
        """Clear the value caches an edit at ``(row, col)`` can affect.

        An edit can change any dependent's value, and within a workbook a
        dependent may live on another sheet (cross-sheet refs). The workbook's
        incremental dependency index (:mod:`abax.core.depgraph`) narrows that to
        just the reachable cells; standalone sheets, a disabled flag, or any path
        the index can't prove sound all degrade to the blanket clear.
        """
        wb = self.workbook
        if wb is None:
            self._value_cache.clear()
            return
        if getattr(wb, "calc_mode", "auto") == "manual":
            # Manual calc: defer dependent recalculation until recalculate() (F9).
            # Drop only the edited cell's own memo so it reflects its new content;
            # dependents keep their last-calculated values and the book is dirty.
            self._value_cache.pop((row, col), None)
            wb._calc_dirty = True
            return
        from .depgraph import ABAX_INCREMENTAL

        if not ABAX_INCREMENTAL:
            wb.invalidate_caches()
            return
        try:
            wb.invalidate_dependents(self, row, col)
        except Exception:
            wb.invalidate_caches()

    def set_cells_bulk(self, items) -> None:
        """Set many ``(row, col, raw)`` cells, invalidating caches ONCE at the end.

        For bulk loads (CSV/Parquet/streaming) this avoids re-clearing the value
        cache and popping the AST cache on every single cell — the dominant cost
        when populating a fresh sheet (profiled ~3-5× faster than per-cell setting).
        """
        cells = self._cells
        anchors = self._anchor_cells
        # Detect array-formula anchors inline (same rule as set_cell) rather than
        # rescanning every cell afterwards — the extra scan dominated bulk loads
        # of literal-only data (CSV/Parquet), where no cell is ever a candidate.
        for row, col, raw in items:
            key = (row, col)
            if raw == "":
                cells.pop(key, None)
                anchors.discard(key)
            else:
                cells[key] = Cell(raw)
                if raw[0] == "=" and _is_array_candidate(raw.upper()):
                    anchors.add(key)
                else:
                    anchors.discard(key)
        self._ast_cache.clear()
        self._rast_cache.clear()
        self._spill_dirty = True
        self._bounds_dirty = True  # many cells added/removed — rescan the extent
        if self.workbook is not None:
            self.workbook.invalidate_caches()
            self.workbook._reset_depgraph()  # formulas changed wholesale
        else:
            self._value_cache.clear()

    # --- structure (insert / delete rows & columns) ----------------------

    def insert_rows(self, at: int, count: int = 1) -> None:
        """Insert ``count`` blank rows before row ``at`` (0-based)."""
        self._restructure("row", at, count)

    def delete_rows(self, at: int, count: int = 1) -> None:
        """Delete ``count`` rows starting at row ``at`` (0-based)."""
        self._restructure("row", at, -count)

    def insert_cols(self, at: int, count: int = 1) -> None:
        """Insert ``count`` blank columns before column ``at`` (0-based)."""
        self._restructure("col", at, count)

    def delete_cols(self, at: int, count: int = 1) -> None:
        """Delete ``count`` columns starting at column ``at`` (0-based)."""
        self._restructure("col", at, -count)

    def _restructure(self, axis: str, index: int, delta: int) -> None:
        from .structure import (
            REF_ERROR,
            adjust_formula,
            adjust_range,
            adjust_reference,
            shift_coord,
        )

        if delta == 0:
            return

        def move(key):
            r, c = key
            coord = r if axis == "row" else c
            nc = shift_coord(coord, index, delta)
            if nc is None:
                return None
            return (nc, c) if axis == "row" else (r, nc)

        # Relocate populated cells and per-cell formats (new dict avoids any
        # overwrite collisions during the shift).
        self._cells = {nk: cell for k, cell in self._cells.items()
                       if (nk := move(k)) is not None}
        self.cell_formats = {nk: spec for k, spec in self.cell_formats.items()
                             if (nk := move(k)) is not None}
        self.cell_styles = {nk: st for k, st in self.cell_styles.items()
                            if (nk := move(k)) is not None}
        self.cell_comments = {nk: text for k, text in self.cell_comments.items()
                              if (nk := move(k)) is not None}

        # Shift conditional-format rule ranges; drop any fully deleted.
        new_rules = []
        for rule in self.cond_rules:
            fn = adjust_range if ":" in rule.range else adjust_reference
            newr = fn(rule.range, self.name, self.name, axis, index, delta)
            if newr != REF_ERROR:
                rule.range = newr
                new_rules.append(rule)
        self.cond_rules = new_rules

        # Shift sheet-local data-validation ranges; drop any wholly deleted.
        from .reference import parse_range, to_a1

        new_validations = []
        for r1, c1, r2, c2, rule in self.validations:
            newr = adjust_range(f"{to_a1(r1, c1)}:{to_a1(r2, c2)}",
                                self.name, self.name, axis, index, delta)
            if newr != REF_ERROR:
                nr1, nc1, nr2, nc2 = parse_range(newr)
                new_validations.append((nr1, nc1, nr2, nc2, rule))
        self.validations = new_validations

        # Shift workbook-level named ranges whose target resolves to this sheet
        # (qualified targets shift only when the qualifier matches; unqualified
        # ones are treated as this sheet, like an on-sheet formula reference).
        names = getattr(self.workbook, "names", None) if self.workbook is not None else None
        if names is not None:
            for display, target in names.names():
                body = target.rsplit("!", 1)[-1]
                fn = adjust_range if ":" in body else adjust_reference
                newt = fn(target, self.name, self.name, axis, index, delta)
                if newt == target:
                    continue
                names.remove(display) if newt == REF_ERROR else names.define(display, newt)

        # Rewrite formula references everywhere that targets THIS sheet (within
        # the workbook, other sheets may hold ``ThisSheet!A1`` references).
        targets = self.workbook.sheets if self.workbook is not None else [self]
        for sh in targets:
            for key, cell in list(sh._cells.items()):
                if cell.raw.startswith("="):
                    new_raw = adjust_formula(
                        cell.raw, self.name, sh.name, axis, index, delta)
                    if new_raw != cell.raw:
                        sh._cells[key] = Cell(new_raw)
            sh._ast_cache.clear()
            sh._rast_cache.clear()
            sh._value_cache.clear()
            sh._rebuild_anchor_cells()
            sh._bounds_dirty = True  # rows/cols shifted — extent may have changed
        if self.workbook is not None:
            self.workbook._reset_depgraph()  # formulas rewritten by the shift

    # --- reading ----------------------------------------------------------

    def validation_for(self, row: int, col: int):
        """The most-recently-added validation rule covering ``(row, col)``, or None."""
        for r1, c1, r2, c2, rule in reversed(self.validations):
            if r1 <= row <= r2 and c1 <= col <= c2:
                return rule
        return None

    def set_comment(self, row: int, col: int, text: str) -> None:
        """Attach a comment/note to a cell. Empty (or whitespace-only) text
        removes it. Comments are metadata — they do not affect cell values."""
        key = (row, col)
        if text and text.strip():
            self.cell_comments[key] = text
        else:
            self.cell_comments.pop(key, None)

    def get_comment(self, row: int, col: int) -> str | None:
        """The comment attached to ``(row, col)``, or None if there is none."""
        return self.cell_comments.get((row, col))

    def get_cell(self, row: int, col: int) -> Cell | None:
        return self._cells.get((row, col))

    def get_raw(self, row: int, col: int) -> str:
        cell = self._cells.get((row, col))
        return cell.raw if cell else ""

    def get(self, ref: str) -> Any:
        row, col = parse_a1(ref)
        return self.get_value(row, col)

    def get_value(self, row: int, col: int) -> Any:
        key = (row, col)
        if self._spill_dirty:
            self._sync_spills()
        if key in self._value_cache:
            return self._value_cache[key]
        cell = self._cells.get(key)
        if cell is None:
            # Empty cell — but a neighbouring array may have spilled onto it.
            anchor = self._spill_anchor.get(key)
            if anchor is not None and anchor != key:
                val = self._spill_element(anchor, key)
                self._value_cache[key] = val
                return val
            return None
        if not cell.is_formula:
            val = cell.literal()
            self._value_cache[key] = val
            return val
        # Formula cell. If it's a spill anchor, its value is the top-left of the
        # spilled grid (or #SPILL! when the spill is blocked).
        if key in self._spill_error:
            val = CellError(CellError.SPILL)
            self._value_cache[key] = val
            return val
        grid = self._spill_grid.get(key)
        if grid is not None:
            val = grid[0][0]
            self._value_cache[key] = val
            return val
        # Scalar result (the common case).
        raw = self._compute_formula(row, col, cell)
        if isinstance(raw, list):
            # An array from a formula the candidate test missed: register it for
            # the next pass and, for now, surface its top-left value.
            self._anchor_cells.add(key)
            self._spill_dirty = True
            g = to_grid(raw)
            val = g[0][0] if g else CellError(CellError.CALC)
        else:
            val = raw
        self._value_cache[key] = val
        return val

    def _compute_formula(self, row: int, col: int, cell: Cell) -> Any:
        """Evaluate a formula cell to its raw result (a scalar, an error, or —
        for a dynamic-array formula — a Python ``list``). No spill handling and
        no value caching; :meth:`get_value` and the spill pass layer those on."""
        key = (row, col)
        if key in self._computing:
            return CellError(CellError.CIRC)
        self._computing.add(key)
        try:
            ast = self._ast_cache.get(key)
            if ast is None:
                ast = parse(cell.formula)
                self._ast_cache[key] = ast
            names = getattr(self.workbook, "names", None)
            if names:  # O(1) — empty/absent registry skips name resolution
                # Name resolution rewrites the whole AST; memoize the result and
                # only redo it when the formula or the name registry changes.
                ver = names.version
                cached = self._rast_cache.get(key)
                if cached is not None and cached[0] == ver:
                    ast = cached[1]
                else:
                    ast = _resolve_names(ast, names)
                    self._rast_cache[key] = (ver, ast)
            val = evaluate(ast, self._resolve,
                           EvalContext(self._resolve, row, col, self._resolve_spill,
                                       self._resolve_source, self._sheet_info))
        except FormulaError:
            val = CellError(CellError.NAME)
        except RecursionError:
            val = CellError(CellError.CIRC)
        finally:
            self._computing.discard(key)
        if isinstance(val, LambdaValue):
            # A LAMBDA that was never applied can't be shown in a cell.
            val = CellError(CellError.CALC)
        return val

    def _resolve_spill(self, sheet_name: str, row: int, col: int) -> "list | None":
        """Spill-range lookup for the ``A1#`` operator: the spilled grid anchored
        at ``(row, col)`` on ``sheet_name`` (this sheet if empty), or None."""
        target = self
        if sheet_name:
            target = self.workbook.get_sheet(sheet_name) if self.workbook is not None else None
            if target is None:
                return None
        if target._spill_dirty:
            target._sync_spills()
        return target._spill_grid.get((row, col))

    def _resolve_source(self, sheet_name: str, row: int, col: int) -> "str | None":
        """Raw cell-source lookup for ISFORMULA / FORMULATEXT / CELL: the cell's
        input text on ``sheet_name`` (this sheet if empty), or None for an
        unknown sheet."""
        target = self
        if sheet_name:
            target = self.workbook.get_sheet(sheet_name) if self.workbook is not None else None
            if target is None:
                return None
        return target.get_raw(row, col)

    def _sheet_info(self, sheet_name: str = "") -> "tuple[int, int] | None":
        """(1-based sheet index, sheet count) for SHEET / SHEETS. Empty name =
        this sheet; an unknown name returns None (-> #N/A)."""
        if self.workbook is None:
            if not sheet_name or sheet_name.lower() == self.name.lower():
                return (1, 1)
            return None
        sheets = self.workbook.sheets
        if not sheet_name:
            for i, sh in enumerate(sheets):
                if sh is self:
                    return (i + 1, len(sheets))
            return (1, len(sheets))
        for i, sh in enumerate(sheets):
            if sh.name.lower() == sheet_name.lower():
                return (i + 1, len(sheets))
        return None

    # --- dynamic-array spill ---------------------------------------------

    def _rebuild_anchor_cells(self) -> None:
        """Rescan every cell for array-formula anchors (bulk load / restructure)."""
        self._anchor_cells = {
            (r, c) for (r, c), cell in self._cells.items()
            if cell.raw.startswith("=") and _is_array_candidate(cell.raw.upper())
        }
        self._spill_dirty = True

    def _sync_spills(self) -> None:
        """Recompute the spill map if it is dirty (memoized per invalidation)."""
        if self._spilling:
            return
        self._spill_dirty = False
        self._spill_anchor = {}
        self._spill_grid = {}
        self._spill_error = set()
        if not self._anchor_cells:
            return
        self._spilling = True
        try:
            # Row-major order so an upper-left anchor claims contested cells first.
            for key in sorted(self._anchor_cells):
                cell = self._cells.get(key)
                if cell is None or not cell.is_formula:
                    continue
                raw = self._compute_formula(key[0], key[1], cell)
                if not isinstance(raw, list):
                    continue
                if not raw:  # empty array (e.g. FILTER with no matches) -> #CALC!
                    self._spill_grid[key] = [[CellError(CellError.CALC)]]
                    self._spill_anchor[key] = key
                    continue
                grid = to_grid(raw)
                if grid is not None:
                    self._register_spill(key[0], key[1], grid)
        finally:
            self._spilling = False

    def _register_spill(self, r0: int, c0: int, grid: list) -> None:
        nr = len(grid)
        nc = len(grid[0]) if grid else 0
        anchor = (r0, c0)
        if nr <= 1 and nc <= 1:  # a 1x1 array is just a value; no region to claim
            self._spill_grid[anchor] = grid
            self._spill_anchor[anchor] = anchor
            return
        # Collision: any target cell already holding real content or claimed by
        # an earlier spill blocks this one entirely (Excel's #SPILL!).
        for r in range(r0, r0 + nr):
            for c in range(c0, c0 + nc):
                if (r, c) == anchor:
                    continue
                if self._cells.get((r, c)) is not None or (r, c) in self._spill_anchor:
                    self._spill_error.add(anchor)
                    return
        self._spill_grid[anchor] = grid
        for i in range(nr):
            for j in range(nc):
                self._spill_anchor[(r0 + i, c0 + j)] = anchor

    def _spill_element(self, anchor: tuple[int, int], key: tuple[int, int]) -> Any:
        grid = self._spill_grid.get(anchor)
        if grid is None:
            return None
        i, j = key[0] - anchor[0], key[1] - anchor[1]
        if 0 <= i < len(grid) and 0 <= j < len(grid[i]):
            return grid[i][j]
        return None

    def is_spill_anchor(self, row: int, col: int) -> bool:
        """True if ``(row, col)`` is the anchor of a multi-cell spill."""
        if self._spill_dirty:
            self._sync_spills()
        grid = self._spill_grid.get((row, col))
        return grid is not None and (len(grid) > 1 or (bool(grid) and len(grid[0]) > 1))

    def is_spilled_into(self, row: int, col: int) -> bool:
        """True if ``(row, col)`` is a non-anchor cell filled by a spill."""
        if self._spill_dirty:
            self._sync_spills()
        anchor = self._spill_anchor.get((row, col))
        return anchor is not None and anchor != (row, col)

    def in_spill(self, row: int, col: int) -> bool:
        """True if ``(row, col)`` belongs to any multi-cell spill (anchor or not)."""
        if self._spill_dirty:
            self._sync_spills()
        anchor = self._spill_anchor.get((row, col))
        if anchor is None:
            return False
        grid = self._spill_grid.get(anchor)
        return grid is not None and (len(grid) > 1 or (bool(grid) and len(grid[0]) > 1))

    def spill_region(self, row: int, col: int) -> "tuple[int, int, int, int] | None":
        """``(r0, c0, r1, c1)`` region for the anchor at ``(row, col)``, or None."""
        if self._spill_dirty:
            self._sync_spills()
        grid = self._spill_grid.get((row, col))
        if grid is None:
            return None
        nr, nc = len(grid), (len(grid[0]) if grid else 0)
        if nr <= 1 and nc <= 1:
            return None
        return (row, col, row + nr - 1, col + nc - 1)

    def spill_edges(self, row: int, col: int) -> frozenset:
        """Which region borders ('top'/'bottom'/'left'/'right') pass through this
        cell — for painting the dashed spill outline. Empty if not in a spill."""
        if self._spill_dirty:
            self._sync_spills()
        anchor = self._spill_anchor.get((row, col))
        if anchor is None:
            return frozenset()
        grid = self._spill_grid.get(anchor)
        if grid is None:
            return frozenset()
        nr, nc = len(grid), (len(grid[0]) if grid else 0)
        if nr <= 1 and nc <= 1:
            return frozenset()
        r0, c0 = anchor
        r1, c1 = r0 + nr - 1, c0 + nc - 1
        edges = set()
        if row == r0:
            edges.add("top")
        if row == r1:
            edges.add("bottom")
        if col == c0:
            edges.add("left")
        if col == c1:
            edges.add("right")
        return frozenset(edges)

    def _resolve(self, sheet_name: str, row: int, col: int) -> Any:
        """Resolver passed to the evaluator. Empty sheet_name = this sheet."""
        if not sheet_name:
            return self.get_value(row, col)
        if self.workbook is None:
            return CellError(CellError.REF)
        target = self.workbook.get_sheet(sheet_name)
        if target is None:
            return CellError(CellError.REF)
        return target.get_value(row, col)

    def display(self, row: int, col: int) -> str:
        """Human-facing text for a cell — formatted value, or error code."""
        val = self.get_value(row, col)
        spec = self.cell_formats.get((row, col))
        if spec:
            from .format.cellformat import format_cell

            return format_cell(val, spec)
        return self.format_value(val)

    @staticmethod
    def format_value(val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, CellError):
            return str(val)
        if isinstance(val, bool):
            return "TRUE" if val else "FALSE"
        if isinstance(val, float):
            if val.is_integer():
                return str(int(val))
            return f"{val:g}"
        return str(val)

    # --- bounds / iteration ----------------------------------------------

    def used_bounds(self) -> tuple[int, int]:
        """``(n_rows, n_cols)`` covering all populated cells (0,0 if empty).

        Spilled array cells count toward the extent so the grid/exports show the
        whole spill, even though only the anchor's source formula is stored.
        """
        if self._anchor_cells and self._spill_dirty:
            self._sync_spills()
        if not self._cells:
            return 0, 0
        # The ``_cells`` extent is tracked incrementally (adds bump the maxes);
        # only a boundary delete / bulk load / restructure forces a full rescan.
        if self._bounds_dirty:
            mr = mc = 0
            for r, c in self._cells:
                if r > mr:
                    mr = r
                if c > mc:
                    mc = c
            self._cells_max_row, self._cells_max_col = mr, mc
            self._bounds_dirty = False
        max_row, max_col = self._cells_max_row, self._cells_max_col
        for (ar, ac), grid in self._spill_grid.items():
            er = ar + len(grid) - 1
            ec = ac + (len(grid[0]) if grid else 1) - 1
            if er > max_row:
                max_row = er
            if ec > max_col:
                max_col = ec
        return max_row + 1, max_col + 1

    def iter_cells(self) -> Iterator[tuple[int, int, Cell]]:
        for (r, c), cell in self._cells.items():
            yield r, c, cell

    def _repr_html_(self) -> str:
        """Rich HTML table — lets a Sheet display as a grid in Jupyter / IPython /
        the abax console's rich display. Bounded so a huge sheet stays printable."""
        import html

        from .reference import index_to_col

        nr, nc = self.used_bounds()
        if nr == 0 or nc == 0:
            return "<i>empty sheet</i>"
        max_r, max_c = min(nr, 200), min(nc, 50)
        head = "".join(f"<th>{index_to_col(c)}</th>" for c in range(max_c))
        body = []
        for r in range(max_r):
            cells = "".join(f"<td>{html.escape(self.display(r, c))}</td>" for c in range(max_c))
            body.append(f"<tr><th style='text-align:right'>{r + 1}</th>{cells}</tr>")
        notes = []
        if nr > max_r:
            notes.append(f"{nr - max_r} more rows")
        if nc > max_c:
            notes.append(f"{nc - max_c} more columns")
        tail = f"<div><i>… {', '.join(notes)}</i></div>" if notes else ""
        return (f"<b>{html.escape(self.name)}</b>"
                "<table border='1' style='border-collapse:collapse'>"
                f"<thead><tr><th></th>{head}</tr></thead><tbody>"
                + "".join(body) + "</tbody></table>" + tail)

    def _repr_markdown_(self) -> str:
        """Compact Markdown table — the plain-text rich rendering used by the abax
        console (and any Markdown-aware frontend). Bounded tighter than the HTML
        view so it stays readable in a terminal."""
        from .reference import index_to_col

        nr, nc = self.used_bounds()
        if nr == 0 or nc == 0:
            return f"**{self.name}** *(empty)*"
        max_r, max_c = min(nr, 20), min(nc, 12)

        def esc(text: str) -> str:
            return text.replace("|", "\\|").replace("\n", " ")

        header = "| | " + " | ".join(index_to_col(c) for c in range(max_c)) + " |"
        rule = "|---" * (max_c + 1) + "|"
        rows = []
        for r in range(max_r):
            cells = " | ".join(esc(self.display(r, c)) for c in range(max_c))
            rows.append(f"| **{r + 1}** | {cells} |")
        notes = []
        if nr > max_r:
            notes.append(f"{nr - max_r} more rows")
        if nc > max_c:
            notes.append(f"{nc - max_c} more columns")
        tail = f"\n\n*… {', '.join(notes)}*" if notes else ""
        return f"**{self.name}**\n\n" + "\n".join([header, rule, *rows]) + tail

    def recalculate(self) -> None:
        """Force a full recompute (clears caches, evaluates every cell)."""
        self._value_cache.clear()
        self._spill_dirty = True
        for r, c in list(self._cells):
            self.get_value(r, c)

    # --- serialization helpers -------------------------------------------

    def to_dict(self) -> dict:
        """JSON-friendly representation: A1 ref -> raw text."""
        return {to_a1(r, c): cell.raw for (r, c), cell in self._cells.items()}

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "Sheet":
        sheet = cls(name)
        # Bulk path: invalidate caches once, not once per cell (the native-format
        # load path — matches the CSV/Excel/etc. loaders).
        sheet.set_cells_bulk((*parse_a1(ref), raw) for ref, raw in data.items())
        return sheet


def _node_for_target(target: str):
    """Turn a named-range target string into a Ref/Range AST node."""
    from . import ast_nodes as A

    sheet = ""
    if "!" in target:
        sheet, target = target.rsplit("!", 1)
    if ":" in target:
        return A.Range(target, sheet)
    return A.Ref(target, sheet)


def _resolve_names(node, registry):
    """Replace ``Name`` nodes matching a defined name with their Ref/Range."""
    from . import ast_nodes as A

    if isinstance(node, A.Name):
        target = registry.lookup(node.text)
        return _node_for_target(target) if target is not None else node
    if isinstance(node, A.Unary):
        return A.Unary(node.op, _resolve_names(node.operand, registry))
    if isinstance(node, A.Binary):
        return A.Binary(node.op,
                        _resolve_names(node.left, registry),
                        _resolve_names(node.right, registry))
    if isinstance(node, A.Func):
        return A.Func(node.name, tuple(_resolve_names(a, registry) for a in node.args))
    return node
