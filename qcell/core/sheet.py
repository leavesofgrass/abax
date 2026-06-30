"""The `Sheet` — a sparse grid of cells with lazy, memoized recalculation.

Cells are stored sparsely in a dict keyed by ``(row, col)``. Values are
computed on demand and cached; any edit clears the value cache so dependents
recompute. Circular references are detected during evaluation and surface as
``#CIRC!`` rather than a Python ``RecursionError``.

This module is the public face of the core engine for the engine/GUI/TUI
layers above it.
"""

from __future__ import annotations

from typing import Any, Iterator

from .cells import Cell
from .errors import CellError, FormulaError
from .evaluator import evaluate
from .parser import parse
from .reference import parse_a1, to_a1


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
        # Data-validation rules over ranges: list of (r1, c1, r2, c2, ValidationRule).
        self.validations: list = []
        self._cells: dict[tuple[int, int], Cell] = {}
        self._ast_cache: dict[tuple[int, int], Any] = {}
        self._value_cache: dict[tuple[int, int], Any] = {}
        self._computing: set[tuple[int, int]] = set()

    # --- editing ----------------------------------------------------------

    def set(self, ref: str, raw: str) -> None:
        """Set a cell by A1 reference, e.g. ``sheet.set("B2", "=A1*2")``."""
        row, col = parse_a1(ref)
        self.set_cell(row, col, raw)

    def set_cell(self, row: int, col: int, raw: str) -> None:
        key = (row, col)
        if raw == "":
            self._cells.pop(key, None)
        else:
            self._cells[key] = Cell(raw)
        self._ast_cache.pop(key, None)
        # An edit can change any dependent's value. Within a workbook, dependents
        # may live on *other* sheets (cross-sheet refs), so clear every sheet's
        # cache; standalone sheets just clear their own.
        if self.workbook is not None:
            self.workbook.invalidate_caches()
        else:
            self._value_cache.clear()

    def set_cells_bulk(self, items) -> None:
        """Set many ``(row, col, raw)`` cells, invalidating caches ONCE at the end.

        For bulk loads (CSV/Parquet/streaming) this avoids re-clearing the value
        cache and popping the AST cache on every single cell — the dominant cost
        when populating a fresh sheet (profiled ~3-5× faster than per-cell setting).
        """
        cells = self._cells
        for row, col, raw in items:
            if raw == "":
                cells.pop((row, col), None)
            else:
                cells[(row, col)] = Cell(raw)
        self._ast_cache.clear()
        if self.workbook is not None:
            self.workbook.invalidate_caches()
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
            sh._value_cache.clear()

    # --- reading ----------------------------------------------------------

    def validation_for(self, row: int, col: int):
        """The most-recently-added validation rule covering ``(row, col)``, or None."""
        for r1, c1, r2, c2, rule in reversed(self.validations):
            if r1 <= row <= r2 and c1 <= col <= c2:
                return rule
        return None

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
        if key in self._value_cache:
            return self._value_cache[key]
        if key in self._computing:
            return CellError(CellError.CIRC)
        cell = self._cells.get(key)
        if cell is None:
            return None
        if not cell.is_formula:
            val = cell.literal()
            self._value_cache[key] = val
            return val
        self._computing.add(key)
        try:
            ast = self._ast_cache.get(key)
            if ast is None:
                ast = parse(cell.formula)
                self._ast_cache[key] = ast
            names = getattr(self.workbook, "names", None)
            if names is not None and names.names():
                ast = _resolve_names(ast, names)
            val = evaluate(ast, self._resolve)
        except FormulaError:
            val = CellError(CellError.NAME)
        except RecursionError:
            val = CellError(CellError.CIRC)
        finally:
            self._computing.discard(key)
        self._value_cache[key] = val
        return val

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
        """``(n_rows, n_cols)`` covering all populated cells (0,0 if empty)."""
        if not self._cells:
            return 0, 0
        max_row = max(r for r, _ in self._cells)
        max_col = max(c for _, c in self._cells)
        return max_row + 1, max_col + 1

    def iter_cells(self) -> Iterator[tuple[int, int, Cell]]:
        for (r, c), cell in self._cells.items():
            yield r, c, cell

    def _repr_html_(self) -> str:
        """Rich HTML table — lets a Sheet display as a grid in Jupyter / IPython /
        the qcell console's rich display. Bounded so a huge sheet stays printable."""
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

    def recalculate(self) -> None:
        """Force a full recompute (clears caches, evaluates every cell)."""
        self._value_cache.clear()
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
