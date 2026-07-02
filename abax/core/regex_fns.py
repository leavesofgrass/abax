"""Regular-expression text functions (Excel 2024 REGEX family) — pure stdlib.

Excel 2024 shipped three ``REGEX*`` functions backed by a regex engine; abax
mirrors their surface with Python's :mod:`re`:

* ``REGEXTEST(text, pattern, [case_sensitivity])`` -> ``bool`` — does the
  pattern match anywhere in ``text``?
* ``REGEXEXTRACT(text, pattern, [return_mode], [case_sensitivity])`` — pull
  matches out of ``text``. ``return_mode`` 0 = first whole match (default),
  1 = every whole match (a Python list, so the result *spills*), 2 = the
  capture groups of the first match (a list).
* ``REGEXREPLACE(text, pattern, replacement, [case_sensitivity])`` — replace
  every match globally.

The ``case_sensitivity`` argument follows Excel: ``0`` (default) is
case-sensitive, ``1`` is case-insensitive.

A bad pattern or bad argument maps to :data:`CellError.VALUE`; a ``REGEXEXTRACT``
mode-0 call with no match maps to :data:`CellError.NA`. Compiled patterns are
cached with :func:`functools.lru_cache` (the case flag is part of the key).
Registered by :func:`register` alongside the other function packs.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Callable

from .errors import CellError


def _arg(args: list, i: int, default: Any = None) -> Any:
    return args[i] if i < len(args) else default


def _as_text(v: Any) -> "str | None":
    """Coerce a scalar argument to text the way Excel does for text functions.

    Returns ``None`` for values that have no sensible text form here (an error,
    ``None``/blank, or a container) so the caller can raise ``#VALUE!``.
    """
    if isinstance(v, CellError) or v is None:
        return None
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        # Render whole floats without a trailing ".0" (matches abax text coercion).
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)
    return None


def _flag(case_sensitivity: Any) -> "int | None":
    """Map the ``case_sensitivity`` argument to an ``re`` flag (or ``None`` on
    a bad value). ``0`` -> case-sensitive (no flag), ``1`` -> IGNORECASE."""
    if case_sensitivity is None:
        return 0
    if isinstance(case_sensitivity, bool):
        # Excel treats the arg numerically; TRUE == 1 == case-insensitive.
        return re.IGNORECASE if case_sensitivity else 0
    if isinstance(case_sensitivity, (int, float)):
        n = int(case_sensitivity)
        if n == 0:
            return 0
        if n == 1:
            return re.IGNORECASE
        return None
    return None


@lru_cache(maxsize=256)
def _compile(pattern: str, flags: int) -> "re.Pattern | None":
    """Compile ``pattern`` with ``flags``; ``None`` if the pattern is invalid.

    Cached so a formula filled down a column compiles each distinct pattern
    once. ``flags`` is part of the key, so the case-sensitive and
    case-insensitive forms are cached separately.
    """
    try:
        return re.compile(pattern, flags)
    except re.error:
        return None


def _prepare(text: Any, pattern: Any, case_sensitivity: Any):
    """Shared front door: coerce/validate args, returning either a
    ``(compiled, subject)`` pair or a ``CellError``."""
    subject = _as_text(text)
    pat = _as_text(pattern)
    if subject is None or pat is None:
        return CellError(CellError.VALUE)
    flags = _flag(case_sensitivity)
    if flags is None:
        return CellError(CellError.VALUE)
    compiled = _compile(pat, flags)
    if compiled is None:
        return CellError(CellError.VALUE)
    return compiled, subject


def _regextest(args: list) -> Any:
    """REGEXTEST(text, pattern, [case_sensitivity]) -> TRUE if the pattern
    matches anywhere in ``text``."""
    got = _prepare(_arg(args, 0), _arg(args, 1), _arg(args, 2))
    if isinstance(got, CellError):
        return got
    compiled, subject = got
    return compiled.search(subject) is not None


def _regexextract(args: list) -> Any:
    """REGEXEXTRACT(text, pattern, [return_mode], [case_sensitivity]) — pull
    matches from ``text`` (mode 0 first match, 1 all matches, 2 capture groups)."""
    mode_raw = _arg(args, 2, 0)
    got = _prepare(_arg(args, 0), _arg(args, 1), _arg(args, 3))
    if isinstance(got, CellError):
        return got
    compiled, subject = got
    if isinstance(mode_raw, bool) or not isinstance(mode_raw, (int, float)):
        return CellError(CellError.VALUE)
    mode = int(mode_raw)
    if mode == 0:  # first whole match
        m = compiled.search(subject)
        if m is None:
            return CellError(CellError.NA)
        return m.group(0)
    if mode == 1:  # every whole match -> spills
        matches = [m.group(0) for m in compiled.finditer(subject)]
        if not matches:
            return CellError(CellError.NA)
        return matches
    if mode == 2:  # capture groups of the first match -> spills
        m = compiled.search(subject)
        if m is None:
            return CellError(CellError.NA)
        groups = m.groups()
        # No capture groups -> fall back to the whole match (Excel behaviour).
        return [g if g is not None else "" for g in groups] if groups else [m.group(0)]
    return CellError(CellError.VALUE)


def _regexreplace(args: list) -> Any:
    """REGEXREPLACE(text, pattern, replacement, [case_sensitivity]) — replace
    every match of ``pattern`` in ``text`` with ``replacement`` (global)."""
    got = _prepare(_arg(args, 0), _arg(args, 1), _arg(args, 3))
    if isinstance(got, CellError):
        return got
    compiled, subject = got
    replacement = _as_text(_arg(args, 2))
    if replacement is None:
        return CellError(CellError.VALUE)
    try:
        return compiled.sub(replacement, subject)
    except re.error:
        # A bad backreference in the replacement template (e.g. "\9").
        return CellError(CellError.VALUE)


_REGISTRY: dict[str, Callable[[list], Any]] = {
    "REGEXTEST": _regextest,
    "REGEXEXTRACT": _regexextract,
    "REGEXREPLACE": _regexreplace,
}

SIGNATURES = {
    "REGEXTEST": "REGEXTEST(text, pattern, [case_sensitivity])",
    "REGEXEXTRACT": "REGEXEXTRACT(text, pattern, [return_mode], [case_sensitivity])",
    "REGEXREPLACE": "REGEXREPLACE(text, pattern, replacement, [case_sensitivity])",
}


def register(functions: dict) -> None:
    """Merge the REGEX text functions into the engine's function table."""
    functions.update(_REGISTRY)
