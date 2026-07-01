"""Formula-precedent extraction — the inputs a formula depends on.

Given a raw cell string (e.g. ``"=SUM(A1:A3)+B7"``), discover every single-cell
and range reference it points at. This is the engine behind a "highlight a
formula's input cells" inspector.

The work is done by tokenizing and parsing the formula with the core
tokenizer/parser, then walking the resulting AST and collecting each
:class:`~abax.core.ast_nodes.Ref` (a single cell) and
:class:`~abax.core.ast_nodes.Range` (a rectangular block). References are
de-duplicated in first-seen order. ``$``-absolute markers are ignored, so
``B7`` and ``$B$7`` are the same precedent.

Stdlib-only (``abax.core`` invariant). A malformed formula surfaces as
:class:`PrecedentError`, never as a raw tokenizer/parser crash.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import ast_nodes as A
from .errors import FormulaError
from .parser import parse
from .reference import parse_a1, parse_range

# Guard against pathological ranges (e.g. a typo spanning millions of cells)
# exhausting memory when we expand them. Beyond this we refuse the work.
_MAX_RANGE_CELLS = 100_000


class PrecedentError(Exception):
    """Raised when a formula's precedents cannot be determined."""


@dataclass(frozen=True)
class Precedent:
    """A single cell or a range that a formula references.

    ``kind`` is ``"cell"`` or ``"range"``; ``a1`` is its canonical A1 text
    (``"B7"`` or ``"A1:C3"``, ``$`` markers stripped); ``cells`` is every
    ``(row, col)`` it covers, 0-based, row-major.
    """

    kind: str
    a1: str
    cells: tuple[tuple[int, int], ...]


def _strip_dollars(text: str) -> str:
    """Drop ``$`` absolute markers: ``"$B$7"`` -> ``"B7"``."""
    return text.replace("$", "")


def _expand_range(r1: int, c1: int, r2: int, c2: int) -> tuple[tuple[int, int], ...]:
    """Every ``(row, col)`` in the inclusive rectangle, row-major."""
    count = (r2 - r1 + 1) * (c2 - c1 + 1)
    if count > _MAX_RANGE_CELLS:
        raise PrecedentError(
            f"range too large to expand: {count} cells (cap {_MAX_RANGE_CELLS})"
        )
    return tuple(
        (r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)
    )


def _walk(node: object, seen: dict[tuple[str, str], Precedent]) -> None:
    """Recursively visit ``node``, recording any Ref/Range precedents.

    ``seen`` maps ``(kind, canonical-a1)`` to its :class:`Precedent`, preserving
    first-seen insertion order and de-duplicating repeats.
    """
    if isinstance(node, A.Ref):
        a1 = _strip_dollars(node.text)
        key = ("cell", a1)
        if key not in seen:
            row, col = parse_a1(a1)
            seen[key] = Precedent("cell", a1, ((row, col),))
        return
    if isinstance(node, A.Range):
        a1 = _strip_dollars(node.text)
        key = ("range", a1)
        if key not in seen:
            r1, c1, r2, c2 = parse_range(a1)
            cells = _expand_range(r1, c1, r2, c2)
            seen[key] = Precedent("range", a1, cells)
        return
    # Composite nodes: recurse into their child node(s). Leaf literals
    # (Number/String/Error/Name) carry no references.
    if isinstance(node, A.Unary):
        _walk(node.operand, seen)
    elif isinstance(node, A.Binary):
        _walk(node.left, seen)
        _walk(node.right, seen)
    elif isinstance(node, A.Func):
        for arg in node.args:
            _walk(arg, seen)


def precedents(raw: str) -> list[Precedent]:
    """Find every cell/range a formula references, de-duplicated in order.

    If ``raw`` is not a formula (doesn't start with ``"="``) the result is an
    empty list. A malformed formula raises :class:`PrecedentError`.
    """
    if not isinstance(raw, str) or not raw.startswith("="):
        return []
    body = raw[1:]
    try:
        ast = parse(body)
    except FormulaError as exc:
        raise PrecedentError(str(exc)) from exc
    seen: dict[tuple[str, str], Precedent] = {}
    _walk(ast, seen)
    return list(seen.values())


def precedent_cells(raw: str) -> set[tuple[int, int]]:
    """Flat set of every ``(row, col)`` a formula depends on (ranges expanded).

    A non-formula yields the empty set; a malformed formula raises
    :class:`PrecedentError`.
    """
    out: set[tuple[int, int]] = set()
    for prec in precedents(raw):
        out.update(prec.cells)
    return out
