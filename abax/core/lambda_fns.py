"""LET, LAMBDA and the functional array helpers (MAP / REDUCE / SCAN / BYROW /
BYCOL / MAKEARRAY).

These are *context* functions: they receive the raw argument AST plus the
calling cell's :class:`~abax.core.evaluator.EvalContext`, because they must
evaluate sub-expressions under **name bindings**. A binding lives in the
context's ``env`` (an upper-cased name → value mapping consulted by the
evaluator's ``Name`` branch before it gives up with ``#NAME?``), so nested
LET/LAMBDA scopes are just chained child contexts.

``LAMBDA`` evaluates to a first-class :class:`LambdaValue` that closes over
its defining context. It can be *called* directly with Excel's postfix-call
syntax (``=LAMBDA(x,x+1)(5)`` -> 6; the parser produces an
:class:`~abax.core.ast_nodes.Call` node that the evaluator applies), passed to
one of the functional helpers, or named via LET and called by name. A lambda
that ends up as a cell's final value (uncalled) shows ``#CALC!``, matching
Excel.

Binding names share the identifier lexer, so a LET/LAMBDA name cannot look
like a cell reference (``x`` is fine, ``x1`` lexes as the reference X1) —
the same restriction Excel imposes. Workbook-defined names are substituted
before evaluation, so a LET name that shadows a workbook name loses; pick
distinct names.

Registered by :func:`register` into ``CONTEXT_FUNCTIONS``.
"""

from __future__ import annotations

from typing import Any

# NOTE: this module is imported *by* abax.core.functions during its own
# initialization, and abax.core.evaluator imports abax.core.functions at module
# level — so the evaluator must be imported lazily here to keep the import
# graph acyclic regardless of which module loads first.
from . import ast_nodes as A
from .errors import CellError, is_error
from .spill import as_grid
from .values import RangeValue


class LambdaValue:
    """A first-class LAMBDA: parameter names, a body AST, and the defining
    context (closure). Callable via :meth:`call` with evaluated arguments."""

    __slots__ = ("params", "body", "ctx")

    def __init__(self, params: "tuple[str, ...]", body: Any, ctx: Any) -> None:
        self.params = params
        self.body = body
        self.ctx = ctx

    def call(self, args: list) -> Any:
        from .evaluator import evaluate

        if len(args) != len(self.params):
            return CellError(CellError.VALUE)
        child = _with_env(self.ctx, dict(zip(self.params, args)))
        return evaluate(self.body, child.resolver, child)

    def __repr__(self) -> str:  # shown nowhere user-facing; cells get #CALC!
        return f"LAMBDA({', '.join(self.params)})"


def _with_env(ctx, bindings: dict):
    """A child EvalContext with *bindings* layered over the existing env."""
    from .evaluator import EvalContext

    merged = dict(ctx.env) if getattr(ctx, "env", None) else {}
    merged.update(bindings)
    return EvalContext(ctx.resolver, ctx.row, ctx.col, ctx.spill,
                       ctx.source, ctx.sheet_info, merged)


def _let(nodes, ctx):
    """LET(name1, value1, [name2, value2, ...], calculation) — sequential
    bindings; later values may use earlier names."""
    if len(nodes) < 3 or len(nodes) % 2 == 0:
        return CellError(CellError.VALUE)
    env_ctx = ctx
    for i in range(0, len(nodes) - 1, 2):
        name = nodes[i]
        if not isinstance(name, A.Name):
            return CellError(CellError.VALUE)
        value = env_ctx.eval(nodes[i + 1])
        env_ctx = _with_env(env_ctx, {name.text: value})
    return env_ctx.eval(nodes[-1])


def _lambda(nodes, ctx):
    """LAMBDA(param1, ..., body) — a first-class function value."""
    if not nodes:
        return CellError(CellError.VALUE)
    params = nodes[:-1]
    if not all(isinstance(p, A.Name) for p in params):
        return CellError(CellError.VALUE)
    names = tuple(p.text for p in params)
    if len(set(names)) != len(names):
        return CellError(CellError.VALUE)
    return LambdaValue(names, nodes[-1], ctx)


def _get_lambda(nodes, ctx, i: int) -> "LambdaValue | CellError":
    if i >= len(nodes):
        return CellError(CellError.VALUE)
    v = ctx.eval(nodes[i])
    if is_error(v):
        return v
    if not isinstance(v, LambdaValue):
        return CellError(CellError.VALUE)
    return v


def _grid_of(v: Any) -> "list[list[Any]] | CellError":
    if is_error(v):
        return v
    return as_grid(v)


# --- the functional helpers ---------------------------------------------------


def _map(nodes, ctx):
    """MAP(array1, [array2, ...], lambda) — element-wise application; all
    arrays must share a shape."""
    if len(nodes) < 2:
        return CellError(CellError.VALUE)
    lam = _get_lambda(nodes, ctx, len(nodes) - 1)
    if is_error(lam):
        return lam
    grids = []
    for n in nodes[:-1]:
        g = _grid_of(ctx.eval(n))
        if is_error(g):
            return g
        grids.append(g)
    if len(lam.params) != len(grids):
        return CellError(CellError.VALUE)
    nr, nc = len(grids[0]), len(grids[0][0]) if grids[0] else 0
    for g in grids[1:]:
        if len(g) != nr or (g and len(g[0]) != nc):
            return CellError(CellError.VALUE)
    return [[lam.call([g[i][j] for g in grids]) for j in range(nc)]
            for i in range(nr)]


def _reduce(nodes, ctx):
    """REDUCE(initial, array, lambda(accumulator, value)) — fold row-major."""
    if len(nodes) != 3:
        return CellError(CellError.VALUE)
    lam = _get_lambda(nodes, ctx, 2)
    if is_error(lam):
        return lam
    acc = ctx.eval(nodes[0])
    if is_error(acc):
        return acc
    grid = _grid_of(ctx.eval(nodes[1]))
    if is_error(grid):
        return grid
    for row in grid:
        for v in row:
            acc = lam.call([acc, v])
            if is_error(acc):
                return acc
    return acc


def _scan(nodes, ctx):
    """SCAN(initial, array, lambda) — REDUCE keeping every intermediate."""
    if len(nodes) != 3:
        return CellError(CellError.VALUE)
    lam = _get_lambda(nodes, ctx, 2)
    if is_error(lam):
        return lam
    acc = ctx.eval(nodes[0])
    if is_error(acc):
        return acc
    grid = _grid_of(ctx.eval(nodes[1]))
    if is_error(grid):
        return grid
    out = []
    for row in grid:
        orow = []
        for v in row:
            acc = lam.call([acc, v])
            orow.append(acc)
        out.append(orow)
    return out


def _byrow(nodes, ctx):
    """BYROW(array, lambda(row)) — one result per row (a spilled column)."""
    if len(nodes) != 2:
        return CellError(CellError.VALUE)
    lam = _get_lambda(nodes, ctx, 1)
    if is_error(lam):
        return lam
    grid = _grid_of(ctx.eval(nodes[0]))
    if is_error(grid):
        return grid
    return [[lam.call([RangeValue([list(row)])])] for row in grid]


def _bycol(nodes, ctx):
    """BYCOL(array, lambda(column)) — one result per column (a spilled row)."""
    if len(nodes) != 2:
        return CellError(CellError.VALUE)
    lam = _get_lambda(nodes, ctx, 1)
    if is_error(lam):
        return lam
    grid = _grid_of(ctx.eval(nodes[0]))
    if is_error(grid):
        return grid
    if not grid:
        return CellError(CellError.CALC)
    cols = [[row[j] for row in grid] for j in range(len(grid[0]))]
    return [[lam.call([RangeValue([[v] for v in col])]) for col in cols]]


def _makearray(nodes, ctx):
    """MAKEARRAY(rows, cols, lambda(row, col)) — build a grid (1-based)."""
    if len(nodes) != 3:
        return CellError(CellError.VALUE)
    lam = _get_lambda(nodes, ctx, 2)
    if is_error(lam):
        return lam
    rows = ctx.eval(nodes[0])
    cols = ctx.eval(nodes[1])
    for v in (rows, cols):
        if is_error(v):
            return v
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return CellError(CellError.VALUE)
    rows, cols = int(rows), int(cols)
    if rows < 1 or cols < 1 or rows * cols > 1_000_000:
        return CellError(CellError.NUM)
    return [[lam.call([float(i + 1), float(j + 1)]) for j in range(cols)]
            for i in range(rows)]


SIGNATURES = {
    "LET": "LET(name1, value1, [name2, value2, ...], calculation)",
    "LAMBDA": "LAMBDA(param1, ..., body)",
    "MAP": "MAP(array1, [array2, ...], lambda)",
    "REDUCE": "REDUCE(initial, array, lambda(acc, value))",
    "SCAN": "SCAN(initial, array, lambda(acc, value))",
    "BYROW": "BYROW(array, lambda(row))",
    "BYCOL": "BYCOL(array, lambda(column))",
    "MAKEARRAY": "MAKEARRAY(rows, cols, lambda(row, col))",
}


def register(context_functions: dict) -> None:
    context_functions.update({
        "LET": _let, "LAMBDA": _lambda,
        "MAP": _map, "REDUCE": _reduce, "SCAN": _scan,
        "BYROW": _byrow, "BYCOL": _bycol, "MAKEARRAY": _makearray,
    })
