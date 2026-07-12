"""Conditional formatting — map cell values to fill colors.

A :class:`CondRule` describes a predicate over an A1 range and the fill color
to apply where it matches. :func:`evaluate` runs a list of rules against a
:class:`~abax.core.sheet.Sheet` and returns the resulting ``(row, col)`` ->
``'#rrggbb'`` color map, used by the GUI for cell backgrounds and by the TUI
for a nearest-ANSI approximation.

This module is part of the stdlib-only ``core`` package.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from ..errors import CellError, is_error
from ..reference import iter_range, parse_range
from ..sheet import Sheet

_DEFAULT_COLOR = "#a6e3a1"


@dataclass
class CondStyle:
    """The visual attributes a matched rule applies to a cell.

    ``fill``/``text`` are ``'#rrggbb'`` (or ``None`` for "leave as is"); the
    three flags are emphasis. A plain rule yields ``CondStyle(fill=<colour>)``;
    a rule carrying a ``css`` declaration yields whatever it parses to.
    """

    fill: str | None = None
    text: str | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False


@dataclass
class CondRule:
    range: str
    kind: str
    value: object = None
    value2: object = None
    color: str = _DEFAULT_COLOR
    # An optional CSS declaration (e.g. "color: white; background: #c00;
    # font-weight: bold") applied instead of the plain fill when a rule matches.
    css: str = ""

    def to_dict(self) -> dict:
        return {
            "range": self.range,
            "kind": self.kind,
            "value": self.value,
            "value2": self.value2,
            "color": self.color,
            "css": self.css,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CondRule":
        return cls(
            range=d["range"],
            kind=d["kind"],
            value=d.get("value"),
            value2=d.get("value2"),
            color=d.get("color", _DEFAULT_COLOR),
            css=d.get("css", ""),
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


# --- CSS styling ----------------------------------------------------------

# The basic CSS/HTML colour names, normalised to hex so a parsed style stays
# hex-only (the TUI's nearest-ANSI mapping and the colour-scale maths both
# assume `#rrggbb`). Unrecognised names are dropped rather than propagated.
_CSS_COLORS = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000", "lime": "#00ff00",
    "green": "#008000", "blue": "#0000ff", "yellow": "#ffff00", "cyan": "#00ffff",
    "aqua": "#00ffff", "magenta": "#ff00ff", "fuchsia": "#ff00ff", "silver": "#c0c0c0",
    "gray": "#808080", "grey": "#808080", "maroon": "#800000", "olive": "#808000",
    "navy": "#000080", "teal": "#008080", "purple": "#800080", "orange": "#ffa500",
}

_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")
_HEX3_RE = re.compile(r"^#?[0-9a-fA-F]{3}$")


def _css_color(value: str) -> str | None:
    """Normalise a CSS colour token to ``'#rrggbb'``, or None if unrecognised."""
    v = value.strip().lower()
    if _HEX_RE.match(v):
        return "#" + v.lstrip("#")
    if _HEX3_RE.match(v):
        h = v.lstrip("#")
        return "#" + "".join(ch * 2 for ch in h)
    return _CSS_COLORS.get(v)


def parse_css(css: str) -> CondStyle:
    """Parse a small CSS-declaration subset into a :class:`CondStyle`.

    Understood properties: ``color`` (text), ``background`` /
    ``background-color`` (fill), ``font-weight`` (``bold``/``600``+ → bold),
    ``font-style`` (``italic``/``oblique``), and ``text-decoration`` /
    ``text-decoration-line`` (contains ``underline``). Unknown properties and
    unrecognised colours are ignored, so a malformed rule degrades gracefully.
    """
    style = CondStyle()
    for decl in css.split(";"):
        if ":" not in decl:
            continue
        prop, _, raw = decl.partition(":")
        prop = prop.strip().lower()
        raw = raw.strip()
        if prop == "color":
            style.text = _css_color(raw) or style.text
        elif prop in ("background", "background-color"):
            style.fill = _css_color(raw) or style.fill
        elif prop == "font-weight":
            low = raw.lower()
            style.bold = low in ("bold", "bolder") or (low.isdigit() and int(low) >= 600)
        elif prop == "font-style":
            style.italic = raw.lower() in ("italic", "oblique")
        elif prop in ("text-decoration", "text-decoration-line"):
            style.underline = "underline" in raw.lower()
    return style


def _rule_style(rule: "CondRule") -> CondStyle:
    """The :class:`CondStyle` a matched non-scale ``rule`` applies.

    A ``css`` declaration wins; otherwise it's a plain fill in ``rule.color``.
    """
    if rule.css:
        return parse_css(rule.css)
    return CondStyle(fill=rule.color.lower())


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

# Kinds whose match depends on an aggregate over the *whole* range (not just the
# one cell): the min/max for a colour scale, the mean for above/below-average,
# a top/bottom cut-off, or duplicate/unique counts. `scale_context` precomputes
# that once per rule so a virtualized grid never rescans the range per cell.
_RANGE_KINDS = frozenset({
    "colorscale", "colorscale3", "above_avg", "below_avg",
    "top_n", "bottom_n", "top_pct", "bottom_pct", "duplicate", "unique",
})


def _range_numbers(sheet: Sheet, rng: str) -> list[float]:
    """Every real number in ``rng`` (bools/errors/blanks excluded)."""
    return [x for row, col in iter_range(rng)
            if (x := _numeric(sheet.get_value(row, col))) is not None]


def _rule_context(sheet: Sheet, rule: CondRule) -> Any:
    """Precompute the range-aggregate a range-aware ``rule`` needs, or None.

    Returns, by kind: ``(lo, hi)`` bounds (colour scales), the mean (above/below
    average), a numeric cut-off threshold (top/bottom N or %), or a
    ``{value: count}`` map (duplicate/unique). Non-range kinds return None.
    """
    kind = rule.kind
    if kind in ("colorscale", "colorscale3"):
        nums = _range_numbers(sheet, rule.range)
        return (min(nums), max(nums)) if nums else None
    if kind in ("above_avg", "below_avg"):
        nums = _range_numbers(sheet, rule.range)
        return sum(nums) / len(nums) if nums else None
    if kind in ("top_n", "bottom_n", "top_pct", "bottom_pct"):
        nums = _range_numbers(sheet, rule.range)
        n = _coerce_number(rule.value)
        if not nums or n is None:
            return None
        if kind in ("top_pct", "bottom_pct"):
            pct = max(0.0, min(100.0, n))
            count = max(1, math.ceil(len(nums) * pct / 100.0))
        else:
            count = int(n)
        count = max(1, min(count, len(nums)))
        # Threshold = the count-th value from the top (or bottom); ties at the
        # boundary are all included (Excel-style), so the set can exceed `count`.
        ordered = sorted(nums, reverse=kind.startswith("top"))
        return ordered[count - 1]
    if kind in ("duplicate", "unique"):
        counts: dict[str, int] = {}
        for row, col in iter_range(rule.range):
            disp = sheet.display(row, col)
            if disp != "":
                key = disp.casefold()
                counts[key] = counts.get(key, 0) + 1
        return counts
    return None


def _cell_style(
    sheet: Sheet, rule: CondRule, row: int, col: int, ctx: Any,
) -> CondStyle | None:
    """The :class:`CondStyle` *rule* applies to cell ``(row, col)``, or None if it
    doesn't match.

    ``ctx`` is the precomputed range-aggregate for a range-aware kind (see
    :func:`_rule_context`); pass None for the per-cell predicate kinds.
    """
    kind = rule.kind

    if kind in ("colorscale", "colorscale3"):
        bounds = ctx if ctx is not None else _rule_context(sheet, rule)
        if bounds is None:
            return None
        x = _numeric(sheet.get_value(row, col))
        if x is None:
            return None
        lo, hi = bounds
        span = hi - lo
        t = 0.0 if span == 0 else (x - lo) / span
        lo_c = _parse_hex(str(rule.value))
        hi_c = _parse_hex(str(rule.value2))
        if kind == "colorscale":
            return CondStyle(fill=_lerp_color(lo_c, hi_c, t))
        # 3-colour scale: lo -> mid (rule.color) -> hi, mid pinned at the midpoint.
        mid_c = _parse_hex(str(rule.color))
        fill = (_lerp_color(lo_c, mid_c, t * 2) if t <= 0.5
                else _lerp_color(mid_c, hi_c, (t - 0.5) * 2))
        return CondStyle(fill=fill)

    style = _rule_style(rule)
    thresh = _coerce_number(rule.value)
    thresh2 = _coerce_number(rule.value2)
    val = sheet.get_value(row, col)
    disp = sheet.display(row, col)
    is_value = val is not None and not isinstance(val, CellError)

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
            return style

    elif kind in ("==", "!="):
        x = _numeric(val)
        if x is not None and thresh is not None:
            matched = (x == thresh) if kind == "==" else (x != thresh)
        else:
            a = disp.casefold()
            b = str(rule.value).casefold()
            matched = (a == b) if kind == "==" else (a != b)
        if matched:
            return style

    elif kind == "between":
        x = _numeric(val)
        if x is not None and thresh is not None and thresh2 is not None and thresh <= x <= thresh2:
            return style

    elif kind == "contains":
        if is_value and str(rule.value).casefold() in disp.casefold():
            return style

    elif kind == "beginswith":
        if is_value and disp.casefold().startswith(str(rule.value).casefold()):
            return style

    elif kind == "endswith":
        if is_value and disp.casefold().endswith(str(rule.value).casefold()):
            return style

    elif kind == "regex":
        # Match the displayed text against a regular expression. Case-sensitive
        # by default (use an inline `(?i)` flag for case-insensitive). An invalid
        # pattern simply never matches rather than raising.
        if is_value and rule.value:
            try:
                if re.search(str(rule.value), disp):
                    return style
            except re.error:
                return None

    elif kind == "blank":
        if disp == "":
            return style

    elif kind == "notblank":
        if disp != "":
            return style

    elif kind in ("above_avg", "below_avg"):
        x = _numeric(val)
        if x is not None and ctx is not None:
            if (kind == "above_avg" and x > ctx) or (kind == "below_avg" and x < ctx):
                return style

    elif kind in ("top_n", "top_pct", "bottom_n", "bottom_pct"):
        x = _numeric(val)
        if x is not None and ctx is not None:
            if (kind.startswith("top") and x >= ctx) or (kind.startswith("bottom") and x <= ctx):
                return style

    elif kind in ("duplicate", "unique"):
        if ctx and disp != "":
            n = ctx.get(disp.casefold(), 0)
            if (kind == "duplicate" and n > 1) or (kind == "unique" and n == 1):
                return style

    return None


def _cell_color(sheet: Sheet, rule: CondRule, row: int, col: int, ctx: Any) -> str | None:
    """The fill color *rule* gives a cell — the ``.fill`` of its style, or None."""
    st = _cell_style(sheet, rule, row, col, ctx)
    return st.fill if st is not None else None


def _merge_style(base: CondStyle | None, add: CondStyle) -> CondStyle:
    """Layer ``add`` over ``base`` — later non-empty attributes win; flags OR."""
    if base is None:
        return CondStyle(add.fill, add.text, add.bold, add.italic, add.underline)
    return CondStyle(
        fill=add.fill if add.fill is not None else base.fill,
        text=add.text if add.text is not None else base.text,
        bold=base.bold or add.bold,
        italic=base.italic or add.italic,
        underline=base.underline or add.underline,
    )


def scale_context(sheet: Sheet, rules: list[CondRule]) -> dict[int, Any]:
    """Precompute each range-aware rule's aggregate (keyed by ``id(rule)``).

    Pass the result to :func:`color_at` / :func:`style_at` so per-cell lookups
    over a viewport reuse one range scan instead of rescanning per cell. Non-range
    kinds are omitted.
    """
    return {id(r): _rule_context(sheet, r) for r in rules if r.kind in _RANGE_KINDS}


def style_at(
    sheet: Sheet, rules: list[CondRule], row: int, col: int,
    scale_ctx: dict[int, Any] | None = None,
) -> CondStyle | None:
    """The merged :class:`CondStyle` for a single cell under ``rules``, or None.

    Every rule whose range contains the cell and whose predicate matches
    contributes; later rules win per attribute (fill/text) and emphasis flags
    accumulate. This is the rich entry point the GUI uses (fill + text colour +
    bold/italic/underline); :func:`color_at` is the fill-only shorthand.
    """
    merged: CondStyle | None = None
    for rule in rules:
        r1, c1, r2, c2 = parse_range(rule.range)
        if r1 <= row <= r2 and c1 <= col <= c2:
            ctx = scale_ctx.get(id(rule)) if scale_ctx is not None else None
            hit = _cell_style(sheet, rule, row, col, ctx)
            if hit is not None:
                merged = _merge_style(merged, hit)
    return merged


def color_at(
    sheet: Sheet, rules: list[CondRule], row: int, col: int,
    scale_ctx: dict[int, Any] | None = None,
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

    Returns ``{(row, col): '#rrggbb'}`` (fill only — the TUI path). Later rules
    override earlier ones on cells they both color.
    """
    out: dict[tuple[int, int], str] = {}
    for rule in rules:
        ctx = _rule_context(sheet, rule) if rule.kind in _RANGE_KINDS else None
        for row, col in iter_range(rule.range):
            hit = _cell_color(sheet, rule, row, col, ctx)
            if hit is not None:
                out[(row, col)] = hit
    return out
