"""In-cell sparklines — the ``SPARKLINE`` formula and its :class:`Sparkline` value.

A sparkline is a tiny, word-sized chart that lives inside a single cell. This
module keeps it *dual-surface* so it renders everywhere abax runs:

* **Text everywhere.** :class:`Sparkline.__str__` returns a unicode sparkline
  built from the block ramp ``▁▂▃▄▅▆▇█`` (line/bar) or win/loss glyphs
  ``▀``/``▄``/``·``. Because :meth:`abax.core.sheet.Sheet.format_value` falls
  through to ``str(val)`` for unknown value types, a ``Sparkline`` shows as this
  text in the TUI and as the GUI's default display string — no GUI code needed
  for a usable fallback.
* **Crisp vector in the GUI.** :meth:`Sparkline.to_svg` returns a self-contained
  ``<svg>`` the grid delegate can paint with ``QSvgRenderer`` for a sharp inline
  chart, degrading to the unicode text when SVG rendering is unavailable.

The value is produced by the ``SPARKLINE(range, [type], [color])`` formula
(:func:`_sparkline`); :func:`register` merges it into the engine's function
table the way every other core pack does. Pure stdlib — no numpy/Qt here; the
GUI merely consumes :meth:`to_svg`.
"""

from __future__ import annotations

import math
from typing import Any

from .errors import CellError, is_error
from .functions.helpers import _arg, _numbers_checked, _text

# The eight-step block ramp used for "line"/"bar" text sparklines: lowest value
# maps to ``▁`` (index 0) and highest to ``█`` (index 7).
_RAMP = "▁▂▃▄▅▆▇█"

# Win/loss glyphs: a value above zero rides the top half, below zero the bottom
# half, and exactly zero is a small centred dot.
_WIN, _LOSS, _ZERO = "▀", "▄", "·"

# Default chart colours (shared hex vocabulary with core.science.chartsvg).
_LINE_COLOR = "#1565c0"
_MARKER_COLOR = "#c62828"
_UP_COLOR = "#2e7d32"
_DOWN_COLOR = "#c62828"
_ZERO_COLOR = "#9e9e9e"

# Accepted ``type`` spellings -> canonical kind. "column" is Excel's name for a
# vertical-bar sparkline; we treat it as an alias of "bar".
_KINDS = {
    "line": "line",
    "bar": "bar",
    "column": "bar",
    "winloss": "winloss",
    "win-loss": "winloss",
    "win/loss": "winloss",
}


def _ramp_text(values: list[float]) -> str:
    """Block-ramp sparkline of ``values`` scaled across their own min..max.

    Each value picks a rung of :data:`_RAMP` by its position in the min..max
    span, so the smallest value is ``▁`` and the largest ``█``. A flat series
    (all equal) sits on the mid rung rather than collapsing to the floor.
    """
    lo = min(values)
    hi = max(values)
    span = hi - lo
    top = len(_RAMP) - 1
    out = []
    for v in values:
        if span == 0:
            idx = top // 2
        else:
            idx = int(round((v - lo) / span * top))
            idx = 0 if idx < 0 else top if idx > top else idx
        out.append(_RAMP[idx])
    return "".join(out)


def _winloss_text(values: list[float]) -> str:
    """Win/loss sparkline: ``▀`` for positive, ``▄`` for negative, ``·`` for zero."""
    out = []
    for v in values:
        if v > 0:
            out.append(_WIN)
        elif v < 0:
            out.append(_LOSS)
        else:
            out.append(_ZERO)
    return "".join(out)


class Sparkline:
    """A word-sized chart value: numbers plus a chart ``kind`` and options.

    Instances are produced by :func:`_sparkline`. They are immutable in practice
    (the engine never mutates a computed value) and render two ways:
    :meth:`__str__` for the universal text fallback and :meth:`to_svg` for the
    GUI's vector paint.

    Attributes:
        values: the numeric series, left to right (blanks/text already dropped).
        kind: ``"line"``, ``"bar"`` or ``"winloss"``.
        color: optional hex/CSS colour override for the line/bar fill (the
            winloss chart keeps its up/down colours). ``None`` uses the default.
    """

    __slots__ = ("values", "kind", "color")

    def __init__(self, values: list[float], kind: str = "line",
                 color: str | None = None) -> None:
        self.values = [float(v) for v in values]
        self.kind = kind if kind in ("line", "bar", "winloss") else "line"
        self.color = color

    def __str__(self) -> str:
        """Unicode sparkline — the text shown in the TUI and as the GUI fallback."""
        if not self.values:
            return ""
        if self.kind == "winloss":
            return _winloss_text(self.values)
        return _ramp_text(self.values)

    def __repr__(self) -> str:
        return f"Sparkline({self.kind!r}, n={len(self.values)})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Sparkline):
            return (self.values == other.values and self.kind == other.kind
                    and self.color == other.color)
        return NotImplemented

    def __hash__(self) -> int:
        return hash((tuple(self.values), self.kind, self.color))

    # --- SVG rendering -----------------------------------------------------

    def to_svg(self, width: int = 120, height: int = 24) -> str:
        """A self-contained ``<svg>`` string for the GUI to paint at cell size.

        ``"line"`` delegates to :func:`abax.core.science.chartsvg.sparkline_svg`
        (a min/max-normalised trend line with a last-point marker); ``"bar"`` and
        ``"winloss"`` are rendered here as small ``<rect>`` charts with a zero
        baseline.
        """
        if self.kind == "bar":
            return _bar_svg(self.values, width, height, self.color or _LINE_COLOR)
        if self.kind == "winloss":
            return _winloss_svg(self.values, width, height)
        # "line" — reuse the existing standalone sparkline generator.
        from .science.chartsvg import sparkline_svg

        return sparkline_svg(self.values, width=width, height=height)


def _svg_open(width: int, height: int) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">')


def _bar_svg(values: list[float], width: int, height: int, color: str) -> str:
    """Vertical-bar sparkline over a zero baseline (negatives drop below it)."""
    parts = [_svg_open(width, height)]
    vals = [float(v) for v in values if math.isfinite(v)]
    n = len(vals)
    if n == 0:
        parts.append("</svg>")
        return "\n".join(parts)

    pad = 2.0
    lo = min(0.0, min(vals))
    hi = max(0.0, max(vals))
    span = (hi - lo) or 1.0
    ph = height - 2.0 * pad
    pw = width - 2.0 * pad
    slot = pw / n
    bw = slot * 0.7

    def y(v: float) -> float:
        return pad + ph * (1.0 - (v - lo) / span)

    y_zero = y(0.0)
    for i, v in enumerate(vals):
        cx = pad + slot * (i + 0.5)
        yv = y(v)
        top = min(yv, y_zero)
        bh = abs(yv - y_zero)
        if bh < 0.75:  # keep a near-zero bar faintly visible
            bh = 0.75
        parts.append(f'<rect x="{cx - bw / 2.0:.2f}" y="{top:.2f}" '
                     f'width="{bw:.2f}" height="{bh:.2f}" fill="{color}"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def _winloss_svg(values: list[float], width: int, height: int) -> str:
    """Win/loss sparkline: equal-size up (green) / down (red) blocks about a mid line."""
    parts = [_svg_open(width, height)]
    vals = [float(v) for v in values if math.isfinite(v)]
    n = len(vals)
    if n == 0:
        parts.append("</svg>")
        return "\n".join(parts)

    pad = 2.0
    mid = height / 2.0
    pw = width - 2.0 * pad
    slot = pw / n
    bw = slot * 0.7
    bar_h = (height - 2.0 * pad) * 0.4  # fixed block height, up or down

    for i, v in enumerate(vals):
        cx = pad + slot * (i + 0.5)
        x = cx - bw / 2.0
        if v > 0:
            parts.append(f'<rect x="{x:.2f}" y="{mid - bar_h:.2f}" '
                         f'width="{bw:.2f}" height="{bar_h:.2f}" fill="{_UP_COLOR}"/>')
        elif v < 0:
            parts.append(f'<rect x="{x:.2f}" y="{mid:.2f}" '
                         f'width="{bw:.2f}" height="{bar_h:.2f}" fill="{_DOWN_COLOR}"/>')
        else:
            parts.append(f'<rect x="{x:.2f}" y="{mid - 0.75:.2f}" '
                         f'width="{bw:.2f}" height="1.5" fill="{_ZERO_COLOR}"/>')
    parts.append("</svg>")
    return "\n".join(parts)


# --- formula ---------------------------------------------------------------


def _sparkline(args: list) -> Any:
    """``SPARKLINE(range, [type], [color])`` -> a :class:`Sparkline` value.

    The first argument (a range/array/scalar) is flattened and reduced to its
    numeric values (blanks and text are skipped, Excel SUM/AVERAGE-style); an
    error anywhere in it propagates. ``type`` is one of ``line`` (default),
    ``bar``/``column`` or ``winloss``; ``color`` is an optional CSS colour for
    the line/bar. An empty numeric series or an unknown ``type`` yields
    ``#VALUE!``.
    """
    first = _arg(args, 0)
    if is_error(first):
        return first
    type_arg = _arg(args, 1)
    if is_error(type_arg):
        return type_arg
    color_arg = _arg(args, 2)
    if is_error(color_arg):
        return color_arg

    err, nums = _numbers_checked([first])
    if err is not None:
        return err
    if not nums:
        return CellError(CellError.VALUE)

    kind_key = _text(type_arg).strip().lower()
    kind = "line" if not kind_key else _KINDS.get(kind_key)
    if kind is None:
        return CellError(CellError.VALUE)

    color = _text(color_arg).strip() or None
    return Sparkline(nums, kind, color)


_REGISTRY = {"SPARKLINE": _sparkline}


def register(functions: dict) -> None:
    """Merge the ``SPARKLINE`` formula into the engine's function table."""
    functions.update(_REGISTRY)
