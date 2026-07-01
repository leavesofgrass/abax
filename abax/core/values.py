"""Runtime value types shared by the evaluator and functions.

`RangeValue` is a rectangular block of already-evaluated cell values (a list of
rows). Aggregate functions flatten it; lookup functions (VLOOKUP/INDEX/MATCH)
use its 2-D shape. It is deliberately *not* a ``list`` subclass so the
evaluator can block ranges from being used as scalar arithmetic operands.
"""

from __future__ import annotations

from typing import Any, Iterator


class RangeValue:
    __slots__ = ("grid", "_flat")

    def __init__(self, grid: list[list[Any]]) -> None:
        self.grid = grid
        self._flat = None

    @property
    def nrows(self) -> int:
        return len(self.grid)

    @property
    def ncols(self) -> int:
        return len(self.grid[0]) if self.grid else 0

    def flat(self) -> list[Any]:
        # A RangeValue is immutable once built, and several functions flatten the
        # same range more than once (SUMPRODUCT, AND/OR over one range, COUNTIF…),
        # so memoize the single materialization.
        if self._flat is None:
            self._flat = [v for row in self.grid for v in row]
        return self._flat

    def row(self, i: int) -> list[Any]:
        return list(self.grid[i])

    def col(self, j: int) -> list[Any]:
        return [r[j] for r in self.grid]

    def cell(self, i: int, j: int) -> Any:
        return self.grid[i][j]

    def __iter__(self) -> Iterator[Any]:
        return iter(self.flat())

    def __len__(self) -> int:
        return self.nrows * self.ncols

    def __repr__(self) -> str:
        return f"RangeValue({self.nrows}x{self.ncols})"
