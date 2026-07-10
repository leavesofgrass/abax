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
class StructRef:
    """A structured (table) reference, e.g. ``Table1[Col]`` or ``[@Col]``.

    Carried verbatim from the tokenizer; the Sheet rewrites it to a ``Ref`` /
    ``Range`` against the workbook's :class:`~abax.core.tables.TableRegistry`
    just before evaluation (like defined names). One that survives to the
    evaluator (no registry / unknown table) yields ``#NAME?``.
    """

    text: str  # the raw structured-reference text, brackets included


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
class SpillRef:
    """A spill-range reference, e.g. ``A1#`` — the whole array that spilled from
    the anchor cell ``A1`` (Excel's dynamic-array ``#`` operator)."""

    text: str  # the anchor A1 text (without the trailing '#')
    sheet: str = ""


@dataclass(frozen=True, slots=True)
class ArrayLiteral:
    """An inline array constant, e.g. ``{1,2,3}`` (a row) or ``{1,2;3,4}`` (a
    2-D block). ``rows`` is a tuple of tuples of constant AST nodes."""

    rows: tuple  # tuple[tuple[node, ...], ...]


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


@dataclass(frozen=True, slots=True)
class Call:
    """A postfix *application* of an already-evaluated value, e.g. the direct
    LAMBDA call ``LAMBDA(x, x*x)(5)``. ``callee`` is any expression that yields
    a value (a ``Func`` like ``LAMBDA(...)``, a parenthesized expression, a
    ``Name``, or another ``Call`` for chaining ``f(a)(b)``); ``args`` are the
    call arguments. Distinct from ``Func``: an ordinary ``SUM(A1:A3)`` is a
    ``Func`` because a bare name directly followed by ``(`` is a function call;
    only a ``(`` following a *value* produces a ``Call``.
    """

    callee: Any
    args: tuple
