"""AST node types produced by the parser and consumed by the evaluator.

All nodes are tiny immutable data carriers. Keeping them separate from the
evaluator lets tests inspect parse trees without evaluating them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Number:
    value: float


@dataclass(frozen=True, slots=True)
class String:
    value: str


@dataclass(frozen=True, slots=True)
class Error:
    """A literal error value, e.g. ``#REF!`` (e.g. from reference shifting)."""

    code: str


@dataclass(frozen=True, slots=True)
class Name:
    """A bare identifier, e.g. ``TRUE`` / ``FALSE`` or a named constant."""

    text: str  # upper-cased


@dataclass(frozen=True, slots=True)
class Ref:
    """A single-cell reference, e.g. ``B3`` or ``Sheet2!B3``."""

    text: str  # A1 text (without the sheet qualifier)
    sheet: str = ""  # sheet name, or "" for the current sheet


@dataclass(frozen=True, slots=True)
class Range:
    """A rectangular reference, e.g. ``A1:C3`` or ``Sheet2!A1:C3``."""

    text: str
    sheet: str = ""


@dataclass(frozen=True, slots=True)
class Unary:
    op: str
    operand: Any


@dataclass(frozen=True, slots=True)
class Binary:
    op: str
    left: Any
    right: Any


@dataclass(frozen=True, slots=True)
class Func:
    name: str  # upper-cased
    args: tuple
