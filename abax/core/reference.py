"""A1-notation reference handling.

Pure functions converting between A1 strings (``"B7"``, ``"$A$1"``, ranges
``"A1:C3"``) and zero-based ``(row, col)`` integer coordinates. No state.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterator

from .errors import FormulaError

# Matches an optional-absolute cell ref like A1, $A$1, B$10. Column letters,
# then row digits. Anchored variants are produced by the callers.
_CELL_RE = re.compile(r"^\$?([A-Za-z]+)\$?([0-9]+)$")
_RANGE_RE = re.compile(r"^(.+?):(.+)$")


def col_to_index(col: str) -> int:
    """``"A"`` -> 0, ``"Z"`` -> 25, ``"AA"`` -> 26."""
    col = col.upper()
    if not col or not col.isalpha():
        raise FormulaError(f"bad column: {col!r}")
    idx = 0
    for ch in col:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def index_to_col(idx: int) -> str:
    """0 -> ``"A"``, 26 -> ``"AA"``."""
    if idx < 0:
        raise FormulaError(f"negative column index: {idx}")
    out = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


@lru_cache(maxsize=65536)
def parse_a1(ref: str) -> tuple[int, int]:
    """``"B3"`` -> ``(2, 1)`` as ``(row, col)``, zero-based. Ignores ``$``.

    Memoized: the evaluator re-resolves the same A1 strings thousands of times per
    recalc, and this is a pure string→coords map, so caching kills the repeated regex.
    """
    m = _CELL_RE.match(ref.strip())
    if not m:
        raise FormulaError(f"bad cell reference: {ref!r}")
    col = col_to_index(m.group(1))
    row = int(m.group(2)) - 1
    if row < 0:
        raise FormulaError(f"bad row in reference: {ref!r}")
    return row, col


def to_a1(row: int, col: int) -> str:
    """``(2, 1)`` -> ``"B3"``."""
    return f"{index_to_col(col)}{row + 1}"


@lru_cache(maxsize=65536)
def parse_range(rng: str) -> tuple[int, int, int, int]:
    """``"A1:C3"`` -> ``(r1, c1, r2, c2)`` normalized so r1<=r2, c1<=c2.

    A bare cell ``"A1"`` is treated as a 1x1 range. Memoized (pure string→coords).
    """
    rng = rng.strip()
    m = _RANGE_RE.match(rng)
    if not m:
        r, c = parse_a1(rng)
        return r, c, r, c
    r1, c1 = parse_a1(m.group(1))
    r2, c2 = parse_a1(m.group(2))
    return min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)


def iter_range(rng: str) -> Iterator[tuple[int, int]]:
    """Yield every ``(row, col)`` in a range, row-major."""
    r1, c1, r2, c2 = parse_range(rng)
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            yield r, c
