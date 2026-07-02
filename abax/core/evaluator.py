"""Evaluate an AST against a cell-value resolver.

The resolver is any callable ``resolver(row, col) -> value`` returning the
already-computed value of a cell (the :class:`~abax.core.sheet.Sheet`
provides one). The evaluator handles operator semantics, error propagation,
and lazy evaluation of ``IF``; everything else dispatches to
:data:`abax.core.functions.FUNCTIONS`.
"""

from __future__ import annotations

from typing import Any, Callable

from . import ast_nodes as A
from .errors import CellError, FormulaError, is_error
from .functions import CONTEXT_FUNCTIONS, FUNCTIONS, LAZY_FUNCTIONS
from .reference import parse_a1, parse_range
from .tokenizer import Token  # noqa: F401  (re-export convenience)
from .values import RangeValue

Resolver = Callable[[str, int, int], Any]  # (sheet_name, row, col) -> value


class EvalContext:
    """The calling cell's context, passed to reference/context functions (ROW,
    COLUMN, OFFSET, INDIRECT, ...). ``row``/``col`` are 0-based; ``resolver`` is the
    same ``(sheet, r, c) -> value`` the evaluator uses; ``eval(node)`` evaluates an
    argument node on demand (carrying this context onward)."""

    __slots__ = ("resolver", "row", "col", "spill", "source", "sheet_info", "env")

    def __init__(self, resolver: Resolver, row: int, col: int, spill: Any = None,
                 source: Any = None, sheet_info: Any = None,
                 env: "dict | None" = None) -> None:
        self.resolver = resolver
        self.row = row
        self.col = col
        # Optional ``(sheet, row, col) -> grid | None`` lookup for the spill
        # range anchored at a cell (backs the ``A1#`` operator). None outside a
        # Sheet (e.g. bare-evaluator unit tests) -> ``A1#`` yields #REF!.
        self.spill = spill
        # Optional ``(sheet, row, col) -> str | None`` lookup for a cell's raw
        # source text (backs ISFORMULA / FORMULATEXT / CELL). None outside a
        # Sheet -> those functions yield #N/A.
        self.source = source
        # Optional ``(sheet_name) -> (index, count) | None`` lookup — the
        # 1-based index of the named sheet ("" = the calling sheet) and the
        # workbook's sheet count. Backs SHEET / SHEETS; None outside a Sheet.
        self.sheet_info = sheet_info
        # Optional LET/LAMBDA name bindings (upper-cased name -> value),
        # consulted by the ``Name`` branch before it errors with #NAME?.
        # Nested scopes are chained child contexts (see core.lambda_fns).
        self.env = env

    def eval(self, node: Any) -> Any:
        return evaluate(node, self.resolver, self)


def _num(v: Any) -> float | CellError:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return CellError(CellError.VALUE)


def _compare(op: str, a: Any, b: Any) -> Any:
    # Numeric compare when both look numeric; else string compare (Excel-ish).
    an, bn = _num(a), _num(b)
    if not is_error(an) and not is_error(bn) and not isinstance(a, str) and not isinstance(b, str):
        left, right = an, bn
    else:
        left = a if isinstance(a, str) else _text_for_cmp(a)
        right = b if isinstance(b, str) else _text_for_cmp(b)
        if isinstance(left, str) and isinstance(right, str):
            left, right = left.lower(), right.lower()
    try:
        if op == "=":
            return left == right
        if op == "<>":
            return left != right
        if op == "<":
            return left < right
        if op == ">":
            return left > right
        if op == "<=":
            return left <= right
        if op == ">=":
            return left >= right
    except TypeError:
        return CellError(CellError.VALUE)
    return CellError(CellError.VALUE)


def _text_for_cmp(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def evaluate(node: Any, resolver: Resolver, ctx: "EvalContext | None" = None) -> Any:
    # Ordered by frequency in real recalc (Ref/Number/Binary/Func dominate), so
    # the common cases short-circuit early. A type->handler dict was measured
    # *slower* here: isinstance on a short chain is cheap C-level work, while
    # per-node handler functions add Python call overhead that dominates.
    if isinstance(node, A.Ref):
        row, col = parse_a1(node.text)
        return resolver(node.sheet, row, col)
    if isinstance(node, A.Number):
        return node.value
    if isinstance(node, A.Binary):
        return _eval_binary(node, resolver, ctx)
    if isinstance(node, A.Func):
        return _eval_func(node, resolver, ctx)
    if isinstance(node, A.Call):
        return _eval_call(node, resolver, ctx)
    if isinstance(node, A.String):
        return node.value
    if isinstance(node, A.Range):
        r1, c1, r2, c2 = parse_range(node.text)
        grid = [
            [resolver(node.sheet, r, c) for c in range(c1, c2 + 1)] for r in range(r1, r2 + 1)
        ]
        return RangeValue(grid)
    if isinstance(node, A.SpillRef):
        # ``A1#`` — the array that spilled from anchor A1. Resolve via the
        # context's spill lookup; return a fresh list-of-lists so it composes in
        # aggregates and *re-spills* when it is a cell's top-level result.
        if ctx is None or ctx.spill is None:
            return CellError(CellError.REF)
        row, col = parse_a1(node.text)
        grid = ctx.spill(node.sheet, row, col)
        if not grid:
            return CellError(CellError.REF)
        return [list(r) for r in grid]
    if isinstance(node, A.Name):
        if ctx is not None and ctx.env is not None and node.text in ctx.env:
            return ctx.env[node.text]
        if node.text == "TRUE":
            return True
        if node.text == "FALSE":
            return False
        return CellError(CellError.NAME, node.text)
    if isinstance(node, A.Unary):
        if node.op == "@":
            return _implicit_intersection(node.operand, resolver, ctx)
        val = evaluate(node.operand, resolver, ctx)
        if isinstance(val, (list, RangeValue)):
            # Unary +/- broadcasts element-wise over an array.
            from .spill import as_grid
            sign = -1.0 if node.op == "-" else 1.0
            return [[_unary_num(v, sign) for v in row] for row in as_grid(val)]
        if is_error(val):
            return val
        n = _num(val)
        if is_error(n):
            return n
        return -n if node.op == "-" else n
    if isinstance(node, A.Error):
        return CellError(node.code)
    if isinstance(node, A.ArrayLiteral):
        # An inline array constant -> a 2-D list (spills / composes).
        return [[evaluate(cell, resolver, ctx) for cell in row] for row in node.rows]
    raise FormulaError(f"cannot evaluate node: {node!r}")


def _implicit_intersection(operand: Any, resolver: Resolver, ctx: "EvalContext | None") -> Any:
    """The ``@`` operator: reduce an array/range to the single value that lines up
    with the calling cell. For a range it uses the caller's row/column (Excel's
    implicit intersection); for any other array it takes the first element; a
    scalar is returned unchanged."""
    if isinstance(operand, A.Range) and ctx is not None:
        r1, c1, r2, c2 = parse_range(operand.text)
        row, col = ctx.row, ctx.col
        if c1 == c2:  # a single column — align on the caller's row
            return (resolver(operand.sheet, row, c1) if r1 <= row <= r2
                    else CellError(CellError.VALUE))
        if r1 == r2:  # a single row — align on the caller's column
            return (resolver(operand.sheet, r1, col) if c1 <= col <= c2
                    else CellError(CellError.VALUE))
        if r1 <= row <= r2 and c1 <= col <= c2:  # 2-D — intersect on both axes
            return resolver(operand.sheet, row, col)
        return CellError(CellError.VALUE)
    val = evaluate(operand, resolver, ctx)
    if isinstance(val, RangeValue):
        return val.grid[0][0] if val.grid and val.grid[0] else CellError(CellError.VALUE)
    if isinstance(val, list):
        from .spill import to_grid
        grid = to_grid(val)
        return grid[0][0] if grid else CellError(CellError.VALUE)
    return val


def _unary_num(v: Any, sign: float) -> Any:
    if is_error(v):
        return v
    n = _num(v)
    return n if is_error(n) else sign * n


def _eval_binary(node: A.Binary, resolver: Resolver, ctx: "EvalContext | None" = None) -> Any:
    op = node.op
    left = evaluate(node.left, resolver, ctx)
    right = evaluate(node.right, resolver, ctx)
    # A range or array operand broadcasts element-wise (Excel dynamic arrays):
    # the result is a 2-D grid that spills / composes.
    if isinstance(left, (list, RangeValue)) or isinstance(right, (list, RangeValue)):
        return _broadcast_binary(op, left, right)
    return _binary_scalar(op, left, right)


def _binary_scalar(op: str, left: Any, right: Any) -> Any:
    if is_error(left):
        return left
    if is_error(right):
        return right
    if op == "&":
        return _text_for_cmp(left) + _text_for_cmp(right)
    if op in ("=", "<>", "<", ">", "<=", ">="):
        return _compare(op, left, right)
    a, b = _num(left), _num(right)
    if is_error(a):
        return a
    if is_error(b):
        return b
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return CellError(CellError.DIV0) if b == 0 else a / b
    if op == "%":
        return CellError(CellError.DIV0) if b == 0 else a % b
    if op == "^":
        try:
            return float(a) ** float(b)
        except (ValueError, OverflowError):
            return CellError(CellError.NUM)
    raise FormulaError(f"unknown operator: {op}")


def _broadcast_binary(op: str, left: Any, right: Any) -> Any:
    """Apply a binary operator element-wise across array operands, broadcasting a
    row/column/scalar against the other operand (numpy-style: a dimension must be
    equal on both sides or 1). Returns a 2-D list (spills / composes) or #VALUE!
    when the shapes are not broadcastable."""
    from .spill import as_grid

    lg, rg = as_grid(left), as_grid(right)
    lr, lc = len(lg), (len(lg[0]) if lg else 0)
    rr, rc = len(rg), (len(rg[0]) if rg else 0)
    if lc == 0 or rc == 0:
        return CellError(CellError.VALUE)
    if not ((lr == rr or lr == 1 or rr == 1) and (lc == rc or lc == 1 or rc == 1)):
        return CellError(CellError.VALUE)
    nr, nc = max(lr, rr), max(lc, rc)
    out = []
    for i in range(nr):
        li, ri = (i if lr != 1 else 0), (i if rr != 1 else 0)
        row = []
        for j in range(nc):
            lj, rj = (j if lc != 1 else 0), (j if rc != 1 else 0)
            row.append(_binary_scalar(op, lg[li][lj], rg[ri][rj]))
        out.append(row)
    return out


def _eval_func(node: A.Func, resolver: Resolver, ctx: "EvalContext | None" = None) -> Any:
    name = node.name
    # Lazy functions (IF, IFERROR, IFS, SWITCH, CHOOSE) receive unevaluated AST
    # nodes plus an on-demand evaluator, so untaken branches never run.
    lazy = LAZY_FUNCTIONS.get(name)
    if lazy is not None:
        return lazy(node.args, lambda n: evaluate(n, resolver, ctx))

    # Context/reference functions (ROW, COLUMN, OFFSET, INDIRECT, ...) need the raw
    # argument AST (a reference, not its value) plus the calling cell.
    ctxfn = CONTEXT_FUNCTIONS.get(name)
    if ctxfn is not None:
        if ctx is None:
            ctx = EvalContext(resolver, 0, 0)
        try:
            return ctxfn(node.args, ctx)
        except (ValueError, TypeError, ZeroDivisionError, IndexError, OverflowError):
            return CellError(CellError.VALUE)

    fn = FUNCTIONS.get(name)
    if fn is None:
        # A LET/LAMBDA-bound name used with call syntax — =LET(F,LAMBDA(x,x*x),F(5))
        # — invokes the bound lambda with the evaluated arguments.
        if ctx is not None and ctx.env is not None and name in ctx.env:
            from .lambda_fns import LambdaValue

            bound = ctx.env[name]
            if isinstance(bound, LambdaValue):
                return bound.call([evaluate(a, resolver, ctx) for a in node.args])
        return CellError(CellError.NAME, name)
    args = [evaluate(a, resolver, ctx) for a in node.args]
    try:
        return fn(args)
    except (ValueError, TypeError, ZeroDivisionError, IndexError, OverflowError):
        return CellError(CellError.VALUE)


def _eval_call(node: A.Call, resolver: Resolver, ctx: "EvalContext | None" = None) -> Any:
    """Direct application ``callee(args...)`` — the LAMBDA-call seam. The callee
    must evaluate to a :class:`~abax.core.lambda_fns.LambdaValue`; anything else
    is #VALUE! (a propagated error passes through unchanged). Arity checking and
    parameter binding are delegated to ``LambdaValue.call`` — the same path used
    by MAP/REDUCE and LET-bound lambda calls — so an arity mismatch yields the
    existing LAMBDA arity error and no logic is duplicated here."""
    from .lambda_fns import LambdaValue

    callee = evaluate(node.callee, resolver, ctx)
    if is_error(callee):
        return callee
    if not isinstance(callee, LambdaValue):
        return CellError(CellError.VALUE)
    args = [evaluate(a, resolver, ctx) for a in node.args]
    return callee.call(args)
