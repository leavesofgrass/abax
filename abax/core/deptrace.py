"""Recursive formula dependency tracer with an ASCII tree renderer.

Two directions of the same question — "what does this cell depend on?" and
"what depends on this cell?" — expanded transitively into a tree and drawn as a
box-drawing diagram for a TUI ``:trace`` command or a GUI overlay.

* :func:`trace_precedents` walks *downstream* of a formula: it reuses
  :func:`abax.core.precedents.precedent_cells` to get a cell's direct inputs and
  recurses into each. This is "show me the whole calculation chain feeding A1".
* :func:`trace_dependents` walks *upstream*: it scans the sheet once to build a
  reverse map (cell -> the cells whose formulas reference it) and recurses that.
  This is "if I change A1, what recalculates?".

Both stop at ``max_depth`` and mark a node ``cyclic`` when a cell reappears on
the path currently being expanded — so a self-reference (``A1 =A1``) or a
mutual cycle renders as a finite tree annotated ``(cycle)`` instead of blowing
the recursion stack.

Each :class:`DepNode` captures a short snippet of its cell's raw formula at
build time, so :func:`render_ascii` needs only the tree (not the sheet) to draw
a self-describing diagram.

Stdlib-only (``abax.core`` invariant): no numpy/pandas/Qt. Defensive by design —
a blank cell, a non-formula literal, a malformed formula, a self-reference, and
a cycle must all trace and render without raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .precedents import PrecedentError, precedent_cells
from .reference import to_a1

# Longest raw-formula snippet shown beside a cell's A1 label. Longer formulas
# are elided so a deep tree stays inside a terminal column.
_SNIPPET_LEN = 40


@dataclass
class DepNode:
    """One cell in a dependency tree.

    ``cell`` is the 0-based ``(row, col)``; ``a1`` its A1 label; ``raw`` a
    trimmed snippet of the cell's source text (empty for a blank cell);
    ``children`` the nodes it expands into (precedents *or* dependents, depending
    on which tracer built the tree); ``cyclic`` marks a cell that reappeared on
    the current path and was therefore not recursed into (its children stay
    empty).
    """

    cell: tuple[int, int]
    a1: str
    raw: str = ""
    children: list["DepNode"] = field(default_factory=list)
    cyclic: bool = False


def _snippet(sheet, row: int, col: int) -> str:
    """A one-line, length-capped snippet of a cell's raw text.

    Internal whitespace/newlines are collapsed so a multi-line formula stays on a
    single tree row; over-long text is elided with ``…``.
    """
    raw = " ".join(sheet.get_raw(row, col).split())
    if len(raw) > _SNIPPET_LEN:
        raw = raw[: _SNIPPET_LEN - 1] + "…"
    return raw


def _direct_precedents(sheet, row: int, col: int) -> list[tuple[int, int]]:
    """Direct precedent cells of ``(row, col)``, sorted row-major.

    Reuses :func:`precedent_cells` on the cell's raw text. A blank cell or a
    non-formula yields none; a malformed formula degrades to none rather than
    propagating :class:`PrecedentError` — a trace must not crash on one bad cell
    buried deep in the chain.
    """
    try:
        cells = precedent_cells(sheet.get_raw(row, col))
    except PrecedentError:
        return []
    return sorted(cells)


def _trace(
    sheet,
    cell: tuple[int, int],
    neighbors,
    path: frozenset[tuple[int, int]],
    depth: int,
    max_depth: int,
) -> DepNode:
    """Build a :class:`DepNode` for ``cell`` by recursing through ``neighbors``.

    ``neighbors(row, col)`` returns the cells to expand into (precedents or
    dependents). ``path`` is the set of cells on the branch above this one; a
    neighbor already in ``path`` closes a cycle — we emit a leaf flagged
    ``cyclic`` and stop. Recursion also halts at ``max_depth`` so an unexpectedly
    wide/deep graph can't run away.
    """
    row, col = cell
    node = DepNode(cell=cell, a1=to_a1(row, col), raw=_snippet(sheet, row, col))
    if depth >= max_depth:
        return node
    child_path = path | {cell}
    for nb in neighbors(row, col):
        nb_row, nb_col = nb
        if nb in child_path:
            # Revisiting a cell already on this branch closes a cycle. Record it
            # as a flagged leaf (no recursion) so rendering terminates.
            node.children.append(
                DepNode(
                    cell=nb,
                    a1=to_a1(nb_row, nb_col),
                    raw=_snippet(sheet, nb_row, nb_col),
                    cyclic=True,
                )
            )
            continue
        node.children.append(
            _trace(sheet, nb, neighbors, child_path, depth + 1, max_depth)
        )
    return node


def trace_precedents(sheet, row: int, col: int, *, max_depth: int = 8) -> DepNode:
    """Trace the precedents of ``(row, col)`` into a tree, recursing downstream.

    Each node's children are the cells its formula references; those expand in
    turn until a literal (no precedents), ``max_depth``, or a cycle is hit. A
    cell may legitimately appear under more than one branch (a shared input) —
    that is preserved, since each occurrence sits on its own distinct path.
    """

    def neighbors(r: int, c: int):
        return _direct_precedents(sheet, r, c)

    return _trace(sheet, (row, col), neighbors, frozenset(), 0, max_depth)


def _build_reverse_map(sheet) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Map each cell to the cells whose formulas reference it (its dependents).

    Built by scanning the used bounds once and, for every formula cell, adding a
    reverse edge from each of its precedents back to it — the transpose of the
    precedent relation. Malformed formulas are skipped rather than aborting the
    whole scan.
    """
    reverse: dict[tuple[int, int], list[tuple[int, int]]] = {}
    n_rows, n_cols = sheet.used_bounds()
    for r in range(n_rows):
        for c in range(n_cols):
            raw = sheet.get_raw(r, c)
            if not raw.startswith("="):
                continue
            try:
                inputs = precedent_cells(raw)
            except PrecedentError:
                continue
            for src in inputs:
                reverse.setdefault(src, []).append((r, c))
    # Sort each dependent list row-major for deterministic tree order.
    for src in reverse:
        reverse[src].sort()
    return reverse


def trace_dependents(sheet, row: int, col: int, *, max_depth: int = 8) -> DepNode:
    """Trace the dependents of ``(row, col)`` into a tree, recursing upstream.

    The reverse dependency map is built once (a single sheet scan) and shared
    across the whole recursion. Each node's children are the cells that reference
    it; the same depth/cycle guards as :func:`trace_precedents` apply.
    """
    reverse = _build_reverse_map(sheet)

    def neighbors(r: int, c: int):
        return reverse.get((r, c), [])

    return _trace(sheet, (row, col), neighbors, frozenset(), 0, max_depth)


def _label(node: DepNode) -> str:
    """One-line label for a node: A1, its raw snippet, and a ``(cycle)`` tag.

    ``A1 =B1+C1`` for a formula cell, ``B1 5`` for a literal, ``A1`` for a blank
    cell, ``A1 =A1 (cycle)`` for a cycle-closing node.
    """
    label = f"{node.a1} {node.raw}" if node.raw else node.a1
    return f"{label} (cycle)" if node.cyclic else label


def _render(node: DepNode, prefix: str, is_last: bool, is_root: bool) -> list[str]:
    """Recursively render ``node`` and its subtree into indented text lines.

    ``prefix`` is the accumulated indentation for this node's descendants;
    ``is_last`` picks ``└─`` (last child) vs ``├─``; the root draws without a
    connector. Children inherit ``│`` where the branch above them continues and
    blank space where it has ended.
    """
    if is_root:
        lines = [_label(node)]
        child_prefix = ""
    else:
        connector = "└─ " if is_last else "├─ "
        lines = [f"{prefix}{connector}{_label(node)}"]
        child_prefix = prefix + ("   " if is_last else "│  ")
    for i, child in enumerate(node.children):
        last_child = i == len(node.children) - 1
        lines.extend(_render(child, child_prefix, last_child, is_root=False))
    return lines


def render_ascii(node: DepNode) -> str:
    """Render a :class:`DepNode` tree as a box-drawing ASCII diagram.

    The root sits flush-left with its A1 + formula snippet; each descendant is
    drawn beneath its parent with ``├─``/``└─`` connectors and ``│`` guide lines,
    cyclic nodes annotated ``(cycle)``. Operates purely on the tree — the raw
    snippets were captured at build time — so no :class:`Sheet` is needed here.

    Example::

        A1 =B1+C1
        ├─ B1 5
        └─ C1 =B1*2
           └─ B1 5
    """
    return "\n".join(_render(node, "", True, True))
