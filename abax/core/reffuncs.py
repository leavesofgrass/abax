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


def _ref_target(node) -> "tuple[str, int, int] | None":
    """(sheet, row, col) of a reference node's top-left cell, else None."""
    if isinstance(node, (A.Ref, A.SpillRef)):
        r, c = parse_a1(node.text)
        return node.sheet, r, c
    if isinstance(node, A.Range):
        r1, c1, _r2, _c2 = parse_range(node.text)
        return node.sheet, r1, c1
    return None


def _is_ref_node(node) -> bool:
    return isinstance(node, (A.Ref, A.Range, A.SpillRef))


def _isref(args, ctx):
    """ISREF(value) — TRUE when the argument is a reference (not its value)."""
    if not args:
        return CellError(CellError.VALUE)
    return _is_ref_node(args[0])


def _cell_source(args, ctx):
    """The raw source text of the cell referenced by ``args[0]`` (or an error)."""
    if not args:
        return CellError(CellError.VALUE)
    tgt = _ref_target(args[0])
    if tgt is None:
        return CellError(CellError.VALUE)  # Excel wants a reference here
    if ctx.source is None:
        return CellError(CellError.NA)     # bare evaluator: no sheet behind us
    raw = ctx.source(*tgt)
    if raw is None:
        return CellError(CellError.REF)    # unknown sheet
    return raw


def _isformula(args, ctx):
    """ISFORMULA(reference) — TRUE when the referenced cell holds a formula."""
    raw = _cell_source(args, ctx)
    if is_error(raw):
        return raw
    return raw.startswith("=")


def _formulatext(args, ctx):
    """FORMULATEXT(reference) — the referenced cell's formula text, or #N/A."""
    raw = _cell_source(args, ctx)
    if is_error(raw):
        return raw
    return raw if raw.startswith("=") else CellError(CellError.NA)


def _sheet_fn(args, ctx):
    """SHEET([value]) — 1-based index of the calling sheet, of a reference's
    sheet, or of a sheet named by a string value."""
    if ctx.sheet_info is None:
        return CellError(CellError.NA)
    name = ""
    if args:
        if _is_ref_node(args[0]):
            name = args[0].sheet  # "" -> the calling sheet
        else:
            v = ctx.eval(args[0])
            if is_error(v):
                return v
            name = _text(v)
    info = ctx.sheet_info(name)
    return float(info[0]) if info else CellError(CellError.NA)


def _sheets_fn(args, ctx):
    """SHEETS([reference]) — the workbook's sheet count (a plain reference
    spans one sheet)."""
    if ctx.sheet_info is None:
        return CellError(CellError.NA)
    if args:
        return 1.0 if _is_ref_node(args[0]) else CellError(CellError.VALUE)
    info = ctx.sheet_info("")
    return float(info[1]) if info else CellError(CellError.NA)


def _cell_fn(args, ctx):
    """CELL(info_type, [reference]) — the common info types: address, row,
    col, contents, type, filename (always "" — no file path in core)."""
    if not args:
        return CellError(CellError.VALUE)
    v = ctx.eval(args[0])
    if is_error(v):
        return v
    info = _text(v).strip().lower()
    if len(args) > 1:
        tgt = _ref_target(args[1])
        if tgt is None:
            return CellError(CellError.VALUE)
        sheet, r, c = tgt
    else:
        sheet, r, c = "", ctx.row, ctx.col
    if info == "address":
        addr = f"${index_to_col(c)}${r + 1}"
        return f"{sheet}!{addr}" if sheet else addr
    if info == "row":
        return float(r + 1)
    if info == "col":
        return float(c + 1)
    if info == "contents":
        val = ctx.resolver(sheet, r, c)
        return 0.0 if val is None or val == "" else val
    if info == "type":
        val = ctx.resolver(sheet, r, c)
        if val is None or val == "":
            return "b"
        return "l" if isinstance(val, str) else "v"
    if info == "filename":
        return ""
    return CellError(CellError.VALUE)


SIGNATURES = {
    "ROW": "ROW([reference])",
    "COLUMN": "COLUMN([reference])",
    "ROWS": "ROWS(range)",
    "COLUMNS": "COLUMNS(range)",
    "OFFSET": "OFFSET(reference, rows, cols, [height], [width])",
    "INDIRECT": "INDIRECT(ref_text, [a1=TRUE])",
    "ADDRESS": "ADDRESS(row, column, [abs_num=1], [a1=TRUE], [sheet])",
    "ISREF": "ISREF(value)",
    "ISFORMULA": "ISFORMULA(reference)",
    "FORMULATEXT": "FORMULATEXT(reference)",
    "SHEET": "SHEET([value])",
    "SHEETS": "SHEETS([reference])",
    "CELL": "CELL(info_type, [reference])",
}


def _coerce_num(v):
    """A pivot writes cells as text; recover a number where the text is one."""
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return v
    return v


def _getpivotdata(args, ctx):
    """GETPIVOTDATA(data_field, pivot_range, [field, item]…).

    abax pivots are plain cell blocks, so *pivot_range* is the whole written
    pivot (header row + body, top-left is the index field). *data_field* names a
    column by its header; a ``[field, item]`` pair whose *field* matches the
    index-field header picks the body row by its *item* label. With no pair the
    grand-total row (labelled ``Total``, present when the pivot was built with
    margins) is used. Returns ``#REF!`` when the field/row can't be located.
    """
    if len(args) < 2:
        return CellError(CellError.VALUE)
    data_field = _text(ctx.eval(args[0]))
    if is_error(data_field):
        return data_field
    bounds = _ref_bounds(args[1])
    if bounds is None:
        return CellError(CellError.REF)
    r1, c1, r2, c2 = bounds
    grid = [[ctx.resolver("", r, c) for c in range(c1, c2 + 1)]
            for r in range(r1, r2 + 1)]
    if len(grid) < 2 or not grid[0]:
        return CellError(CellError.REF)
    header = [_text(v) for v in grid[0]]
    try:
        col = header.index(data_field)
    except ValueError:
        return CellError(CellError.REF)

    rest = args[2:]
    pairs = [(_text(ctx.eval(rest[k])), _text(ctx.eval(rest[k + 1])))
             for k in range(0, len(rest) - 1, 2)]
    target = next((it for f, it in pairs if f == header[0]), "Total")
    for row in grid[1:]:
        if _text(row[0]) == target:
            return _coerce_num(row[col])
    return CellError(CellError.REF)


def register(context_functions: dict) -> None:
    context_functions.update({
        "ROW": _row, "COLUMN": _column, "ROWS": _rows, "COLUMNS": _columns,
        "OFFSET": _offset, "INDIRECT": _indirect, "ADDRESS": _address,
        "ISREF": _isref, "ISFORMULA": _isformula, "FORMULATEXT": _formulatext,
        "SHEET": _sheet_fn, "SHEETS": _sheets_fn, "CELL": _cell_fn,
        "GETPIVOTDATA": _getpivotdata,
    })
