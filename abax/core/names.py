"""Workbook-level named ranges.

A defined name (``Sales`` -> ``A1:A10``) is a workbook-scoped label that may be
used in formulas in place of a cell or range reference. This module provides
:class:`NameRegistry`, a case-insensitive store that preserves the original
display case of each name, plus validation helpers.

Pure stdlib; depends only on :mod:`abax.core.reference` and
:mod:`abax.core.errors`.
"""

from __future__ import annotations

import re

from . import reference
from .errors import FormulaError

# A defined name: starts with a letter or underscore, then letters/digits/_/.
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
# Shaped like a cell reference (e.g. "A1", "$B$2") -- forbidden as a name.
_CELLISH_RE = re.compile(r"^\$?[A-Za-z]+\$?[0-9]+$")
# Reserved words (case-insensitive) that cannot be names.
_RESERVED = frozenset({"TRUE", "FALSE", "R", "C"})


class NameError(Exception):
    """Raised when a name or target is invalid for the registry."""


def is_valid_name(name: str) -> bool:
    """Return ``True`` if *name* is a legal defined name.

    A name must match ``^[A-Za-z_][A-Za-z0-9_.]*$``, be 1..255 chars, not be
    shaped like a cell reference (``A1``/``$B$2``), and not be a reserved word
    (``TRUE``, ``FALSE``, ``R``, ``C``; case-insensitive).
    """
    if not isinstance(name, str):
        return False
    if not (1 <= len(name) <= 255):
        return False
    if not _NAME_RE.match(name):
        return False
    if _CELLISH_RE.match(name):
        return False
    if name.upper() in _RESERVED:
        return False
    return True


def normalize_target(target: str) -> str:
    """Validate and trim a name's *target*.

    The target is one of:

    * a single cell (``B2``, ``$B$2``, ``Sheet1!B2``),
    * a range (``A1:C3``, ``Sheet1!A1:C3``), or
    * a **formula** — any ``=``-prefixed expression, including a ``LAMBDA``
      (``=LAMBDA(x, x*x)``) or a constant (``=2*PI()``). A formula name is
      spliced into referencing formulas at resolve time (see
      ``abax.core.sheet._resolve_names``); a ``LAMBDA``-valued name is callable
      (``=SQ(A1)``).

    A leading ``Sheet!`` qualifier on a ref target is kept in the returned value.
    Raises :class:`NameError` if the target parses as none of the above.
    """
    if not isinstance(target, str):
        raise NameError(f"target must be a string: {target!r}")
    trimmed = target.strip()
    if not trimmed:
        raise NameError("empty target")

    # A formula-valued name: validate that its body parses.
    if trimmed.startswith("="):
        from .parser import parse

        try:
            parse(trimmed[1:])
        except FormulaError as exc:
            raise NameError(f"invalid formula target: {target!r}") from exc
        return trimmed

    # Strip a leading sheet qualifier ("Sheet1!...") before validating the ref.
    ref_part = trimmed
    if "!" in trimmed:
        _sheet, _, ref_part = trimmed.rpartition("!")

    try:
        if ":" in ref_part:
            reference.parse_range(ref_part)
        else:
            reference.parse_a1(ref_part)
    except FormulaError as exc:
        raise NameError(f"invalid target: {target!r}") from exc
    return trimmed


class NameRegistry:
    """A case-insensitive registry of defined names.

    Internally keyed on the upper-cased name; each entry stores the original
    display case alongside its target.
    """

    def __init__(self) -> None:
        # upper(name) -> (display_name, target)
        self._by_upper: dict[str, tuple[str, str]] = {}
        # Bumped on every mutation, so callers that cache name-resolved formulas
        # (see Sheet.get_value) can invalidate cheaply instead of re-resolving on
        # every evaluation.
        self._version = 0

    @property
    def version(self) -> int:
        """A counter bumped on every mutation (define/rename/remove)."""
        return self._version

    def __len__(self) -> int:
        return len(self._by_upper)

    def define(self, name: str, target: str) -> None:
        """Define (or overwrite) *name* with *target*.

        Raises :class:`NameError` if the name or target is invalid.
        """
        if not is_valid_name(name):
            raise NameError(f"invalid name: {name!r}")
        normalized = normalize_target(target)
        self._by_upper[name.upper()] = (name, normalized)
        self._version += 1

    def lookup(self, name: str) -> str | None:
        """Return the target for *name* (case-insensitive), or ``None``."""
        entry = self._by_upper.get(name.upper())
        return entry[1] if entry is not None else None

    def has(self, name: str) -> bool:
        """Return ``True`` if *name* is defined (case-insensitive)."""
        return name.upper() in self._by_upper

    def rename(self, old: str, new: str) -> None:
        """Rename *old* to *new*, keeping its target.

        Raises :class:`NameError` if *old* is missing, *new* is invalid, or
        *new* is already taken by a different name.
        """
        old_key = old.upper()
        if old_key not in self._by_upper:
            raise NameError(f"name not defined: {old!r}")
        if not is_valid_name(new):
            raise NameError(f"invalid name: {new!r}")
        new_key = new.upper()
        if new_key != old_key and new_key in self._by_upper:
            raise NameError(f"name already defined: {new!r}")
        _display, target = self._by_upper.pop(old_key)
        self._by_upper[new_key] = (new, target)
        self._version += 1

    def remove(self, name: str) -> None:
        """Remove *name*. Raises :class:`NameError` if it is missing."""
        key = name.upper()
        if key not in self._by_upper:
            raise NameError(f"name not defined: {name!r}")
        del self._by_upper[key]
        self._version += 1

    def names(self) -> list[tuple[str, str]]:
        """Return ``[(display_name, target)]`` sorted by name (case-insensitive)."""
        return sorted(self._by_upper.values(), key=lambda pair: pair[0].upper())

    def to_dict(self) -> dict:
        """Return a ``{display_name: target}`` mapping."""
        return {display: target for display, target in self._by_upper.values()}

    @classmethod
    def from_dict(cls, d: dict) -> NameRegistry:
        """Build a registry from a mapping, skipping entries that fail validation."""
        reg = cls()
        for name, target in d.items():
            try:
                reg.define(name, target)
            except NameError:
                continue
        return reg
