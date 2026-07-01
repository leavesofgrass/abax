"""Spreadsheet error values and exceptions.

`CellError` is a *value* — it propagates through a formula the way Excel's
`#DIV/0!` does. `FormulaError` is an *exception* raised while parsing.
"""

from __future__ import annotations


class FormulaError(Exception):
    """Raised when a formula cannot be tokenized or parsed."""


class CellError:
    """An Excel-style error value (e.g. ``#DIV/0!``).

    Behaves as a truthy sentinel that knows its own display text. Error values
    are first-class results: any function receiving one should propagate it.
    """

    __slots__ = ("code", "detail")

    # Canonical Excel error codes.
    DIV0 = "#DIV/0!"
    NAME = "#NAME?"
    VALUE = "#VALUE!"
    REF = "#REF!"
    NUM = "#NUM!"
    NA = "#N/A"
    CIRC = "#CIRC!"  # abax extension: circular reference

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail

    def __repr__(self) -> str:
        return f"CellError({self.code!r})"

    def __str__(self) -> str:
        return self.code

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CellError):
            return self.code == other.code
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.code)


def is_error(value: object) -> bool:
    return isinstance(value, CellError)
