"""Keyboard-navigation helpers.

Pure functions for spreadsheet keyboard navigation: Go-To target parsing,
Excel-style Ctrl+Arrow data-edge jumps, and current-region (contiguous block)
detection. All coordinates are zero-based ``(row, col)``. No state.
"""

from __future__ import annotations

from collections import deque

from .errors import FormulaError
from .reference import parse_a1, parse_range


class NavError(Exception):
    """Raised when a Go-To target cannot be parsed."""


def parse_target(text: str) -> tuple:
    """Parse a Go-To target.

    A single cell (``"A1"``, ``"$A$1"``) yields a ``(row, col)`` 2-tuple; a
    range (``"A1:C3"``) yields a normalised ``(r1, c1, r2, c2)`` 4-tuple with
    ``r1<=r2`` and ``c1<=c2``. Case-insensitive; surrounding spaces are ignored.
    Raises :class:`NavError` on anything unparseable.
    """
    if text is None:
        raise NavError("empty go-to target")
    s = text.strip()
    if not s:
        raise NavError("empty go-to target")
    try:
        if ":" in s:
            return parse_range(s)
        return parse_a1(s)
    except FormulaError as exc:
        raise NavError(f"bad go-to target: {text!r}") from exc


def jump_edge(
    populated: set[tuple[int, int]],
    row: int,
    col: int,
    dr: int,
    dc: int,
    max_row: int,
    max_col: int,
) -> tuple[int, int]:
    """Excel-style Ctrl+Arrow jump from ``(row, col)`` in direction ``(dr, dc)``.

    ``(dr, dc)`` is one of ``(-1, 0)``, ``(1, 0)``, ``(0, -1)``, ``(0, 1)``.
    ``populated`` is the set of populated ``(row, col)`` cells. Rules:

    * Current cell populated and the immediate next cell populated: travel to
      the last populated cell before the next blank (end of the run).
    * Current cell populated and the next cell blank (or off-grid): travel to
      the next populated cell after the gap; if none, go to the grid edge.
    * Current cell blank: travel to the next populated cell in that direction;
      if none, go to the grid edge.

    The result is always clamped to ``[0, max_row] x [0, max_col]``.
    """

    def in_grid(r: int, c: int) -> bool:
        return 0 <= r <= max_row and 0 <= c <= max_col

    def is_pop(r: int, c: int) -> bool:
        return in_grid(r, c) and (r, c) in populated

    cur_pop = is_pop(row, col)
    next_pop = is_pop(row + dr, col + dc)

    r, c = row, col

    if cur_pop and next_pop:
        # Travel to the last populated cell before the next blank.
        while is_pop(r + dr, c + dc):
            r += dr
            c += dc
        return r, c

    # Either current cell is blank, or next cell is blank: find the next
    # populated cell across the gap.
    while True:
        nr, nc = r + dr, c + dc
        if not in_grid(nr, nc):
            # Hit the edge without finding a populated cell; clamp.
            return max(0, min(r, max_row)), max(0, min(c, max_col))
        r, c = nr, nc
        if (r, c) in populated:
            return r, c


def current_region(
    populated: set[tuple[int, int]],
    row: int,
    col: int,
) -> tuple[int, int, int, int]:
    """Bounding rectangle of the populated block connected to ``(row, col)``.

    Flood-fills the populated set over 4-neighbours starting at the seed and
    returns ``(r1, c1, r2, c2)`` of the connected component's bounding box. If
    ``(row, col)`` is blank (or isolated), returns ``(row, col, row, col)``.
    """
    if (row, col) not in populated:
        return row, col, row, col

    seen: set[tuple[int, int]] = {(row, col)}
    queue: deque[tuple[int, int]] = deque([(row, col)])
    while queue:
        r, c = queue.popleft()
        for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if (nr, nc) in populated and (nr, nc) not in seen:
                seen.add((nr, nc))
                queue.append((nr, nc))

    rows = [p[0] for p in seen]
    cols = [p[1] for p in seen]
    return min(rows), min(cols), max(rows), max(cols)
