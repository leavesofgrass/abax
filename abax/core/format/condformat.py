"""Conditional formatting — map cell values to fill colors.

A :class:`CondRule` describes a predicate over an A1 range and the fill color
to apply where it matches. :func:`evaluate` runs a list of rules against a
:class:`~abax.core.sheet.Sheet` and returns the resulting ``(row, col)`` ->
``'#rrggbb'`` color map, used by the GUI for cell backgrounds and by the TUI
for a nearest-ANSI approximation.

This module is part of the stdlib-only ``core`` package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..errors import CellError, is_error
from ..reference import iter_range, parse_range
from ..sheet import Sheet

_DEFAULT_COLOR = "#a6e3a1"


@dataclass
class CondRule:
    range: str
    kind: str
    value: object = None
    value2: object = None
    color: str = _DEFAULT_COLOR

    def to_dict(self) -> dict:
        return {
            "range": self.range,
            "kind": self.kind,
            "value": self.value,
            "value2": self.value2,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CondRule":
        return cls(
            range=d["range"],
            kind=d["kind"],
            value=d.get("value"),
            value2=d.get("value2"),
            color=d.get("color", _DEFAULT_COLOR),
        )


# --- color helpers --------------------------------------------------------


def _parse_hex(s: str) -> tuple[int, int, int]:
    """``'#rrggbb'`` (or ``'rrggbb'``) -> ``(r, g, b)`` ints in 0..255."""
    s = s.strip().lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _lerp_color(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> str:
    """Linear interpolation between two RGB colors at ``t`` in 0..1."""
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    r = round(a[0] + (b[0] - a[0]) * t)
    g = round(a[1] + (b[1] - a[1]) * t)
    bl = round(a[2] + (b[2] - a[2]) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


# --- value helpers --------------------------------------------------------


def _numeric(v: Any) -> float | None:
    """Return ``v`` as a float when it is a real number, else ``None``.

    Booleans and :class:`CellError` are *not* numbers here.
    """
    if isinstance(v, bool):
        return None
    if is_error(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _coerce_number(v: object) -> float | None:
    """Coerce a rule's threshold to a float, else ``None``."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


# --- evaluation -----------------------------------------------------------


def _scale_bounds(sheet: Sheet, rule: CondRule) -> tuple[float, float] | None:
    """``(lo, hi)`` over the numeric cells in a colorscale rule's range, or None."""
    vals = [x for row, col in iter_range(rule.range)
            if (x := _numeric(sheet.get_value(row, col))) is not None]
    return (min(vals), max(vals)) if vals else None


def _cell_color(
    sheet: Sheet, rule: CondRule, row: int, col: int,
    scale: tuple[float, float] | None,
) -> str | None:
    """The fill color *rule* gives cell ``(row, col)``, or None if it doesn't match.

    ``scale`` is the precomputed ``(lo, hi)`` for a colorscale rule (range-
    aggregate); pass None for the per-cell predicate kinds.
    """
    kind = rule.kind

    if kind == "colorscale":
        if scale is None:
            scale = _scale_bounds(sheet, rule)
        if scale is None:
            return None
        x = _numeric(sheet.get_value(row, col))
        if x is None:
            return None
        lo, hi = scale
        span = hi - lo
        t = 0.0 if span == 0 else (x - lo) / span
        return _lerp_color(_parse_hex(str(rule.value)), _parse_hex(str(rule.value2)), t)

    color = rule.color.lower()
    thresh = _coerce_number(rule.value)
    thresh2 = _coerce_number(rule.value2)
    val = sheet.get_value(row, col)
    disp = sheet.display(row, col)

    if kind in (">", "<", ">=", "<="):
        x = _numeric(val)
        if x is None or thresh is None:
            return None
        if (
            (kind == ">" and x > thresh)
            or (kind == "<" and x < thresh)
            or (kind == ">=" and x >= thresh)
            or (kind == "<=" and x <= thresh)
        ):
            return color

    elif kind in ("==", "!="):
        x = _numeric(val)
        if x is not None and thresh is not None:
            matched = (x == thresh) if kind == "==" else (x != thresh)
        else:
            a = disp.casefold()
            b = str(rule.value).casefold()
            matched = (a == b) if kind == "==" else (a != b)
        if matched:
            return color

    elif kind == "between":
        x = _numeric(val)
        if x is not None and thresh is not None and thresh2 is not None and thresh <= x <= thresh2:
            return color

    elif kind == "contains":
        if val is not None and not isinstance(val, CellError) \
                and str(rule.value).casefold() in disp.casefold():
            return color

    elif kind == "blank":
        if disp == "":
            return color

    elif kind == "notblank":
        if disp != "":
            return color

    return None


def scale_context(sheet: Sheet, rules: list[CondRule]) -> dict[int, tuple[float, float] | None]:
    """Precompute the ``(lo, hi)`` bounds for each colorscale rule (keyed by id).

    Pass the result to :func:`color_at` so per-cell lookups over a viewport reuse
    one range scan instead of rescanning per cell.
    """
    return {id(r): _scale_bounds(sheet, r) for r in rules if r.kind == "colorscale"}


def color_at(
    sheet: Sheet, rules: list[CondRule], row: int, col: int,
    scale_ctx: dict[int, tuple[float, float] | None] | None = None,
) -> str | None:
    """The fill color for a single cell under ``rules`` (later rules win), or None.

    O(#rules) — checks range membership by bounds, never iterates a rule's range
    (except the one-time colorscale scan, which ``scale_ctx`` caches). This lets a
    virtualized grid color only the cells it paints.
    """
    result = None
    for rule in rules:
        r1, c1, r2, c2 = parse_range(rule.range)
        if r1 <= row <= r2 and c1 <= col <= c2:
            scale = scale_ctx.get(id(rule)) if scale_ctx is not None else None
            hit = _cell_color(sheet, rule, row, col, scale)
            if hit is not None:
                result = hit
    return result


def evaluate(sheet: Sheet, rules: list[CondRule]) -> dict[tuple[int, int], str]:
    """Color every cell matched by ``rules``.

    Returns ``{(row, col): '#rrggbb'}``. Later rules override earlier ones on
    cells they both color.
    """
    out: dict[tuple[int, int], str] = {}
    for rule in rules:
        scale = _scale_bounds(sheet, rule) if rule.kind == "colorscale" else None
        for row, col in iter_range(rule.range):
            hit = _cell_color(sheet, rule, row, col, scale)
            if hit is not None:
                out[(row, col)] = hit
    return out
