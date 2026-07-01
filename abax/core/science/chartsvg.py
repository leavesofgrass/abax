"""Standalone Cartesian SVG chart generators — pure stdlib.

Each public function is a pure function that returns a complete ``<svg …>…</svg>``
string: a bordered plot area, X and Y axes with tick marks plus numeric tick
labels, an optional title, and (for :func:`line_svg`) a legend. Colours are hex,
all inserted text is escaped. Companion to :mod:`abax.core.science.antenna`'s
``polar_svg`` — same standalone, exportable style, but Cartesian.
"""

from __future__ import annotations

import math

# A small, distinct palette cycled for overlaid line series.
_PALETTE = (
    "#1565c0", "#c62828", "#2e7d32", "#f9a825",
    "#6a1b9a", "#00838f", "#ef6c00", "#4e342e",
)
_TICKS = 5


def _svg_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt(v: float) -> str:
    """Compact numeric label (drops a trailing ``.0``)."""
    if v == 0:
        return "0"
    if abs(v) >= 1000 or abs(v) < 1e-3:
        s = f"{v:.3g}"
    else:
        s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s


def _nice_range(lo: float, hi: float) -> tuple[float, float]:
    """Pad a degenerate range so axes always have extent."""
    if not math.isfinite(lo) or not math.isfinite(hi):
        return 0.0, 1.0
    if lo == hi:
        pad = abs(lo) * 0.5 or 1.0
        return lo - pad, hi + pad
    return lo, hi


def _ticks(lo: float, hi: float, n: int = _TICKS) -> list:
    if n < 2:
        n = 2
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def _frame(width, height, margin_l, margin_r, margin_t, margin_b, title):
    """Return (parts, plot geometry) with background, border and title drawn."""
    px0 = margin_l
    py0 = margin_t
    pw = width - margin_l - margin_r
    ph = height - margin_t - margin_b
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<rect x="{px0:.1f}" y="{py0:.1f}" width="{pw:.1f}" height="{ph:.1f}" '
        'fill="none" stroke="#333333" stroke-width="1"/>',
    ]
    if title:
        parts.append(
            f'<text x="{width / 2.0:.1f}" y="16" text-anchor="middle" '
            f'font-family="sans-serif" font-size="13" '
            f'font-weight="bold">{_svg_escape(title)}</text>')
    return parts, (px0, py0, pw, ph)


def _axes(parts, geom, xlo, xhi, ylo, yhi, x_labels=None):
    """Draw X and Y axis tick marks plus numeric labels.

    ``x_labels`` (optional) overrides the numeric X tick labels with category
    strings placed at evenly-spaced positions across the plot.
    """
    px0, py0, pw, ph = geom
    py1 = py0 + ph
    px1 = px0 + pw

    # Y axis: horizontal ticks with numeric labels on the left.
    for ty in _ticks(ylo, yhi):
        frac = 0.0 if yhi == ylo else (ty - ylo) / (yhi - ylo)
        y = py1 - frac * ph
        parts.append(f'<line x1="{px0 - 4:.1f}" y1="{y:.1f}" x2="{px0:.1f}" '
                     f'y2="{y:.1f}" stroke="#333333" stroke-width="1"/>')
        parts.append(
            f'<text x="{px0 - 6:.1f}" y="{y + 3:.1f}" text-anchor="end" '
            f'font-family="sans-serif" font-size="10" '
            f'fill="#333333">{_svg_escape(_fmt(ty))}</text>')

    # X axis: vertical ticks with labels underneath.
    if x_labels is not None:
        n = len(x_labels)
        for i, lab in enumerate(x_labels):
            x = px0 + pw * (i + 0.5) / n if n else px0
            parts.append(f'<line x1="{x:.1f}" y1="{py1:.1f}" x2="{x:.1f}" '
                         f'y2="{py1 + 4:.1f}" stroke="#333333" stroke-width="1"/>')
            parts.append(
                f'<text x="{x:.1f}" y="{py1 + 15:.1f}" text-anchor="middle" '
                f'font-family="sans-serif" font-size="10" '
                f'fill="#333333">{_svg_escape(str(lab))}</text>')
    else:
        for tx in _ticks(xlo, xhi):
            frac = 0.0 if xhi == xlo else (tx - xlo) / (xhi - xlo)
            x = px0 + frac * pw
            parts.append(f'<line x1="{x:.1f}" y1="{py1:.1f}" x2="{x:.1f}" '
                         f'y2="{py1 + 4:.1f}" stroke="#333333" stroke-width="1"/>')
            parts.append(
                f'<text x="{x:.1f}" y="{py1 + 15:.1f}" text-anchor="middle" '
                f'font-family="sans-serif" font-size="10" '
                f'fill="#333333">{_svg_escape(_fmt(tx))}</text>')
    return px0, py0, pw, ph, px1, py1


def _legend(parts, geom, entries):
    """Draw a small legend (swatch + name) in the top-right of the plot area."""
    px0, py0, pw, ph = geom
    x = px0 + pw - 8
    y = py0 + 12
    for name, colour in entries:
        # Right-anchored text with a swatch to its left.
        parts.append(
            f'<text x="{x:.1f}" y="{y + 3:.1f}" text-anchor="end" '
            f'font-family="sans-serif" font-size="10" '
            f'fill="#333333">{_svg_escape(str(name))}</text>')
        parts.append(f'<rect x="{x - 8 - 60:.1f}" y="{y - 4:.1f}" width="10" '
                     f'height="8" fill="{colour}"/>')
        y += 14
    return parts


def line_svg(series, *, title: str = "", width: int = 480, height: int = 320) -> str:
    """Overlaid line chart of one or more named series (pure stdlib SVG).

    ``series`` is ``[(name, points)]`` where ``points`` is ``[(x, y), …]``. Each
    series is drawn in a distinct colour with a matching legend entry.
    """
    margin_l, margin_r, margin_t, margin_b = 46, 16, 26, 30
    parts, geom = _frame(width, height, margin_l, margin_r, margin_t, margin_b, title)

    xs = [x for _n, pts in series for x, _y in pts]
    ys = [y for _n, pts in series for _x, y in pts]
    if xs and ys:
        xlo, xhi = _nice_range(min(xs), max(xs))
        ylo, yhi = _nice_range(min(ys), max(ys))
    else:
        xlo, xhi, ylo, yhi = 0.0, 1.0, 0.0, 1.0
    _axes(parts, geom, xlo, xhi, ylo, yhi)

    px0, py0, pw, ph = geom
    py1 = py0 + ph

    def sx(x):
        return px0 if xhi == xlo else px0 + (x - xlo) / (xhi - xlo) * pw

    def sy(y):
        return py1 if yhi == ylo else py1 - (y - ylo) / (yhi - ylo) * ph

    legend_entries = []
    for i, (name, pts) in enumerate(series):
        colour = _PALETTE[i % len(_PALETTE)]
        legend_entries.append((name, colour))
        if pts:
            d = []
            for j, (x, y) in enumerate(pts):
                d.append(f'{"M" if j == 0 else "L"}{sx(x):.2f} {sy(y):.2f}')
            parts.append(f'<path d="{" ".join(d)}" fill="none" stroke="{colour}" '
                         'stroke-width="2"/>')
    if legend_entries:
        _legend(parts, geom, legend_entries)

    parts.append("</svg>")
    return "\n".join(parts)


def bar_svg(categories, values, *, title: str = "", width: int = 480,
            height: int = 320) -> str:
    """Vertical bar chart; ``categories`` label the X axis, ``values`` the bar heights."""
    margin_l, margin_r, margin_t, margin_b = 46, 16, 26, 32
    parts, geom = _frame(width, height, margin_l, margin_r, margin_t, margin_b, title)

    n = len(categories)
    vals = list(values)
    if vals:
        ylo = min(0.0, min(vals))
        yhi = max(0.0, max(vals))
        ylo, yhi = _nice_range(ylo, yhi)
    else:
        ylo, yhi = 0.0, 1.0
    _axes(parts, geom, 0.0, max(1, n), ylo, yhi, x_labels=categories)

    px0, py0, pw, ph = geom
    py1 = py0 + ph

    def sy(y):
        return py1 if yhi == ylo else py1 - (y - ylo) / (yhi - ylo) * ph

    y_zero = sy(0.0)
    if n:
        slot = pw / n
        bw = slot * 0.6
        for i, v in enumerate(vals):
            cx = px0 + slot * (i + 0.5)
            yv = sy(v)
            top = min(yv, y_zero)
            bh = abs(yv - y_zero)
            parts.append(f'<rect x="{cx - bw / 2.0:.2f}" y="{top:.2f}" '
                         f'width="{bw:.2f}" height="{bh:.2f}" '
                         f'fill="{_PALETTE[0]}" stroke="#0d3c78" stroke-width="1"/>')

    parts.append("</svg>")
    return "\n".join(parts)


def scatter_svg(points, *, title: str = "", width: int = 480,
                height: int = 320) -> str:
    """Scatter plot of ``[(x, y), …]`` drawn as small circles."""
    margin_l, margin_r, margin_t, margin_b = 46, 16, 26, 30
    parts, geom = _frame(width, height, margin_l, margin_r, margin_t, margin_b, title)

    xs = [x for x, _y in points]
    ys = [y for _x, y in points]
    if xs and ys:
        xlo, xhi = _nice_range(min(xs), max(xs))
        ylo, yhi = _nice_range(min(ys), max(ys))
    else:
        xlo, xhi, ylo, yhi = 0.0, 1.0, 0.0, 1.0
    _axes(parts, geom, xlo, xhi, ylo, yhi)

    px0, py0, pw, ph = geom
    py1 = py0 + ph

    def sx(x):
        return px0 if xhi == xlo else px0 + (x - xlo) / (xhi - xlo) * pw

    def sy(y):
        return py1 if yhi == ylo else py1 - (y - ylo) / (yhi - ylo) * ph

    for x, y in points:
        parts.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="3" '
                     f'fill="{_PALETTE[0]}" fill-opacity="0.75" '
                     'stroke="#0d3c78" stroke-width="0.5"/>')

    parts.append("</svg>")
    return "\n".join(parts)


def histogram_svg(values, *, bins: int = 10, title: str = "", width: int = 480,
                  height: int = 320) -> str:
    """Bin ``values`` into ``bins`` equal-width bins and draw the counts as bars."""
    margin_l, margin_r, margin_t, margin_b = 46, 16, 26, 30
    parts, geom = _frame(width, height, margin_l, margin_r, margin_t, margin_b, title)

    if bins < 1:
        bins = 1
    vals = [v for v in values if math.isfinite(v)]
    counts = [0] * bins
    if vals:
        vlo, vhi = min(vals), max(vals)
        if vlo == vhi:
            span = abs(vlo) * 0.5 or 1.0
            vlo, vhi = vlo - span, vhi + span
        span = vhi - vlo
        for v in vals:
            idx = int((v - vlo) / span * bins)
            if idx >= bins:
                idx = bins - 1
            elif idx < 0:
                idx = 0
            counts[idx] += 1
        xlo, xhi = vlo, vhi
    else:
        xlo, xhi = 0.0, 1.0

    ymax = max(counts) if counts else 0
    ylo, yhi = 0.0, float(ymax) if ymax > 0 else 1.0
    _axes(parts, geom, xlo, xhi, ylo, yhi)

    px0, py0, pw, ph = geom
    py1 = py0 + ph

    def sy(y):
        return py1 if yhi == ylo else py1 - (y - ylo) / (yhi - ylo) * ph

    slot = pw / bins
    for i, c in enumerate(counts if vals else []):
        x = px0 + slot * i
        yv = sy(c)
        parts.append(f'<rect x="{x + 0.5:.2f}" y="{yv:.2f}" '
                     f'width="{slot - 1.0:.2f}" height="{py1 - yv:.2f}" '
                     f'fill="{_PALETTE[0]}" stroke="#0d3c78" stroke-width="1"/>')

    parts.append("</svg>")
    return "\n".join(parts)
