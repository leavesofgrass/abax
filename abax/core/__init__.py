"""abax.core — stdlib-only spreadsheet engine.

Invariant: no Qt, no curses, no Textual, no third-party imports. Everything
here is testable headlessly. This is the bottom of the three-layer seam
(core -> engine -> gui/tui).
"""

from .cells import Cell
from .errors import CellError, FormulaError
from .evaluator import evaluate
from .reference import (
    col_to_index,
    index_to_col,
    iter_range,
    parse_a1,
    parse_range,
    to_a1,
)
from .sheet import Sheet

__all__ = [
    "col_to_index",
    "index_to_col",
    "parse_a1",
    "to_a1",
    "parse_range",
    "iter_range",
    "Cell",
    "Sheet",
    "CellError",
    "FormulaError",
    "evaluate",
]
