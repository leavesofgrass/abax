"""The `Cell` value object.

A cell holds raw user input (``raw``) and a cached computed ``value``. If the
raw text starts with ``=`` it is a formula; otherwise it is parsed as a literal
(number, bool, or text). ``__slots__`` keeps memory low across large sheets.
"""

from __future__ import annotations

from typing import Any


class Cell:
    __slots__ = ("raw", "value", "_dirty")

    def __init__(self, raw: str = "") -> None:
        self.raw: str = raw
        self.value: Any = None
        self._dirty: bool = True

    @property
    def is_formula(self) -> bool:
        return isinstance(self.raw, str) and self.raw.startswith("=")

    @property
    def formula(self) -> str:
        """Formula body without the leading ``=`` (empty if not a formula)."""
        return self.raw[1:] if self.is_formula else ""

    def literal(self) -> Any:
        """Parse non-formula raw text into a Python value (number/bool/str)."""
        raw = self.raw
        if raw == "":
            return None
        low = raw.strip().lower()
        if low == "true":
            return True
        if low == "false":
            return False
        try:
            iv = int(raw)
            return iv
        except ValueError:
            pass
        try:
            return float(raw)
        except ValueError:
            return raw

    def __repr__(self) -> str:
        return f"Cell({self.raw!r})"
