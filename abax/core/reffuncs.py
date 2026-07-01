"""Reference / context spreadsheet functions (ROW, COLUMN, ROWS, COLUMNS, OFFSET,
INDIRECT, ADDRESS).

Unlike ordinary functions, these need the *calling cell* and often the raw
argument **reference** (ROW(A1) wants "1", not A1's value). So they use the
context-calling convention: each receives ``(arg_nodes, ctx)`` where ``arg_nodes``
are the un-evaluated AST nodes and ``ctx`` (an :class:`~abax.core.evaluator.EvalContext`)
exposes the 0-based calling ``row``/``col``, the ``resolver`` (``(sheet, r, c) ->
value``) and ``eval(node)`` to evaluate an argument on demand.

Pure stdlib.
"""

from __future__ import annotations

from . import ast_nodes as A
from .errors import CellError, is_error
from .functions.helpers import _as_number, _text
from .reference import index_to_col, parse_a1, parse_range
from .values import RangeValue


def _ref_bounds(node) -> tuple[int, int, int, int] | None:
    """(r1, c1, r2, c2) 0-based for a Ref/Range argument node, else None."""
    if isinstance(node, A.Ref):
        r, c = parse_a1(node.text)
        return r, c, r, c
    if isinstance(node, A.Range):
        return parse_range(node.text)
    return None


def _num(ctx, node, default=None):
    if node is None:
        return default
    v = ctx.eval(node)
    if is_error(v):
        raise _Propagate(v)
    try:
        return _as_number(v)
    except (TypeError, ValueError) as exc:
        raise _Propagate(CellError(CellError.VALUE)) from exc


class _Propagate(Exception):
    def __init__(self, err):
        self.err = err


def _row(args, ctx):
    if not args:
        return float(ctx.row + 1)
    b = _ref_bounds(args[0])
    return float(b[0] + 1) if b else CellError(CellError.VALUE)


def _column(args, ctx):
    if not args:
        return float(ctx.col + 1)
    b = _ref_bounds(args[0])
    return float(b[1] + 1) if b else CellError(CellError.VALUE)


def _rows(args, ctx):
    if not args:
        return CellError(CellError.VALUE)
    b = _ref_bounds(args[0])
    if b:
        return float(b[2] - b[0] + 1)
    v = ctx.eval(args[0])
    return float(v.nrows) if isinstance(v, RangeValue) else 1.0


def _columns(args, ctx):
    if not args:
        return CellError(CellError.VALUE)
    b = _ref_bounds(args[0])
    if b:
        return float(b[3] - b[1] + 1)
    v = ctx.eval(args[0])
    return float(v.ncols) if isinstance(v, RangeValue) else 1.0


def _offset(args, ctx):
    if len(args) < 3:
        return CellError(CellError.VALUE)
    b = _ref_bounds(args[0])
    if b is None:
        return CellError(CellError.REF)
    try:
        dr = int(_num(ctx, args[1]))
        dc = int(_num(ctx, args[2]))
        height = int(_num(ctx, args[3], b[2] - b[0] + 1)) if len(args) > 3 else b[2] - b[0] + 1
        width = int(_num(ctx, args[4], b[3] - b[1] + 1)) if len(args) > 4 else b[3] - b[1] + 1
    except _Propagate as p:
        return p.err
    if height < 1 or width < 1:
        return CellError(CellError.REF)
    nr, nc = b[0] + dr, b[1] + dc
    if nr < 0 or nc < 0:
        return CellError(CellError.REF)
    if height == 1 and width == 1:
        return ctx.resolver("", nr, nc)
    grid = [[ctx.resolver("", nr + i, nc + j) for j in range(width)]
            for i in range(height)]
    return RangeValue(grid)


def _indirect(args, ctx):
    if not args:
        return CellError(CellError.REF)
    text = _text(ctx.eval(args[0])).strip()
    sheet, ref = "", text
    if "!" in text:
        sheet, _, ref = text.rpartition("!")
    try:
        if ":" in ref:
            r1, c1, r2, c2 = parse_range(ref)
            grid = [[ctx.resolver(sheet, r, c) for c in range(c1, c2 + 1)]
                    for r in range(r1, r2 + 1)]
            return RangeValue(grid)
        r, c = parse_a1(ref)
        return ctx.resolver(sheet, r, c)
    except Exception:  # noqa: BLE001 — any bad reference text is #REF!
        return CellError(CellError.REF)


def _address(args, ctx):
    if len(args) < 2:
        return CellError(CellError.VALUE)
    try:
        r = int(_num(ctx, args[0]))
        c = int(_num(ctx, args[1]))
        abs_num = int(_num(ctx, args[2], 1)) if len(args) > 2 else 1
    except _Propagate as p:
        return p.err
    if r < 1 or c < 1 or abs_num not in (1, 2, 3, 4):
        return CellError(CellError.VALUE)
    col = index_to_col(c - 1)
    col_p = "$" if abs_num in (1, 3) else ""
    row_p = "$" if abs_num in (1, 2) else ""
    addr = f"{col_p}{col}{row_p}{r}"
    if len(args) > 4:
        sheet = _text(ctx.eval(args[4]))
        if sheet:
            addr = f"{sheet}!{addr}"
    return addr


SIGNATURES = {
    "ROW": "ROW([reference])",
    "COLUMN": "COLUMN([reference])",
    "ROWS": "ROWS(range)",
    "COLUMNS": "COLUMNS(range)",
    "OFFSET": "OFFSET(reference, rows, cols, [height], [width])",
    "INDIRECT": "INDIRECT(ref_text, [a1=TRUE])",
    "ADDRESS": "ADDRESS(row, column, [abs_num=1], [a1=TRUE], [sheet])",
}


def register(context_functions: dict) -> None:
    context_functions.update({
        "ROW": _row, "COLUMN": _column, "ROWS": _rows, "COLUMNS": _columns,
        "OFFSET": _offset, "INDIRECT": _indirect, "ADDRESS": _address,
    })
