"""Per-cell visual style — bold/italic/underline, alignment, text + fill colours.

A :class:`CellStyle` is an immutable description of how a single cell should be
painted: font emphasis, horizontal alignment, and text/background colours. The
GUI stores a ``dict[(row, col)] -> CellStyle`` on the sheet, serializes it in the
workbook envelope, and applies it when painting. Only non-default fields are
emitted by :meth:`CellStyle.to_dict`, so an unstyled cell serializes to ``{}``.

This module is the data model only (no Qt) and is part of the stdlib-only
``core`` package.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, replace

ALIGNMENTS = ("", "left", "center", "right")

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_BOOL_FIELDS = ("bold", "italic", "underline")


def _validate_align(value: str) -> None:
    if value not in ALIGNMENTS:
        raise ValueError(f"invalid align: {value!r} (expected one of {ALIGNMENTS})")


def _validate_color(name: str, value: str) -> None:
    if value != "" and not _HEX_RE.match(value):
        raise ValueError(f"invalid {name}: {value!r} (expected '' or '#rrggbb')")


@dataclass(frozen=True)
class CellStyle:
    bold: bool = False
    italic: bool = False
    underline: bool = False
    align: str = ""  # "" = default; else one of ALIGNMENTS
    text_color: str = ""  # "" = default; else "#rrggbb"
    bg_color: str = ""  # "" = default; else "#rrggbb"

    def is_empty(self) -> bool:
        """True when every field equals its default (an unstyled cell)."""
        return self == CellStyle()

    def with_changes(self, **kw: object) -> "CellStyle":
        """Return a copy with ``kw`` overrides applied.

        Raises :class:`ValueError` on an unknown field name, a bad ``align``
        value, or a colour that is neither ``""`` nor ``"#rrggbb"``.
        """
        valid = {f.name for f in fields(self)}
        for key in kw:
            if key not in valid:
                raise ValueError(f"unknown field: {key!r}")
        if "align" in kw:
            _validate_align(str(kw["align"]))
        if "text_color" in kw:
            _validate_color("text_color", str(kw["text_color"]))
        if "bg_color" in kw:
            _validate_color("bg_color", str(kw["bg_color"]))
        return replace(self, **kw)

    def to_dict(self) -> dict:
        """Emit only non-default fields (compact JSON for the envelope)."""
        default = CellStyle()
        out: dict = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value != getattr(default, f.name):
                out[f.name] = value
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "CellStyle":
        """Build from a dict, ignoring unknown keys; missing -> default."""
        default = cls()
        return cls(
            bold=bool(d.get("bold", default.bold)),
            italic=bool(d.get("italic", default.italic)),
            underline=bool(d.get("underline", default.underline)),
            align=d.get("align", default.align),
            text_color=d.get("text_color", default.text_color),
            bg_color=d.get("bg_color", default.bg_color),
        )


def merge(base: "CellStyle", **changes: object) -> "CellStyle":
    """``base.with_changes(**changes)`` — a copy of ``base`` with overrides."""
    return base.with_changes(**changes)


def toggle(style: "CellStyle", field: str) -> "CellStyle":
    """Flip a boolean field (``bold``/``italic``/``underline``)."""
    if field not in _BOOL_FIELDS:
        raise ValueError(
            f"not a boolean field: {field!r} (expected one of {_BOOL_FIELDS})"
        )
    return style.with_changes(**{field: not getattr(style, field)})
