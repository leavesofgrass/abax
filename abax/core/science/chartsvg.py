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


def box_svg(series, *, title: str = "", width: int = 480, height: int = 320) -> str:
    """Box-and-whisker plot of one or more named series (pure stdlib SVG).

    ``series`` is ``[(name, values)]``. For each series a box spans Q1..Q3 with a
    median line; whiskers reach the most extreme values within 1.5*IQR of the box,
    and points beyond the whiskers are drawn as outlier dots.
    """
    from .stats import iqr, quantile

    margin_l, margin_r, margin_t, margin_b = 46, 16, 26, 32
    parts, geom = _frame(width, height, margin_l, margin_r, margin_t, margin_b, title)

    # Compute per-series summaries; skip series with no finite values.
    summaries = []
    all_y = []
    for name, values in series:
        vals = sorted(v for v in values if math.isfinite(v))
        if not vals:
            summaries.append(None)
            continue
        q1 = quantile(vals, 0.25)
        med = quantile(vals, 0.5)
        q3 = quantile(vals, 0.75)
        spread = iqr(vals)
        lo_fence = q1 - 1.5 * spread
        hi_fence = q3 + 1.5 * spread
        inliers = [v for v in vals if lo_fence <= v <= hi_fence]
        w_lo = min(inliers) if inliers else vals[0]
        w_hi = max(inliers) if inliers else vals[-1]
        outliers = [v for v in vals if v < lo_fence or v > hi_fence]
        summaries.append((q1, med, q3, w_lo, w_hi, outliers))
        all_y.extend(vals)

    n = len(series)
    if all_y:
        ylo, yhi = _nice_range(min(all_y), max(all_y))
    else:
        ylo, yhi = 0.0, 1.0
    labels = [name for name, _v in series]
    _axes(parts, geom, 0.0, max(1, n), ylo, yhi, x_labels=labels)

    px0, py0, pw, ph = geom
    py1 = py0 + ph

    def sy(y):
        return py1 if yhi == ylo else py1 - (y - ylo) / (yhi - ylo) * ph

    if n:
        slot = pw / n
        bw = slot * 0.5
        for i, summ in enumerate(summaries):
            if summ is None:
                continue
            q1, med, q3, w_lo, w_hi, outliers = summ
            cx = px0 + slot * (i + 0.5)
            colour = _PALETTE[i % len(_PALETTE)]
            top = sy(q3)
            bot = sy(q1)
            # Box (Q1..Q3).
            parts.append(f'<rect x="{cx - bw / 2.0:.2f}" y="{top:.2f}" '
                         f'width="{bw:.2f}" height="{abs(bot - top):.2f}" '
                         f'fill="{colour}" fill-opacity="0.35" '
                         f'stroke="{colour}" stroke-width="1.5"/>')
            # Median line.
            parts.append(f'<line x1="{cx - bw / 2.0:.2f}" y1="{sy(med):.2f}" '
                         f'x2="{cx + bw / 2.0:.2f}" y2="{sy(med):.2f}" '
                         f'stroke="{colour}" stroke-width="2"/>')
            # Whiskers (vertical stem + caps).
            parts.append(f'<line x1="{cx:.2f}" y1="{top:.2f}" x2="{cx:.2f}" '
                         f'y2="{sy(w_hi):.2f}" stroke="{colour}" stroke-width="1"/>')
            parts.append(f'<line x1="{cx:.2f}" y1="{bot:.2f}" x2="{cx:.2f}" '
                         f'y2="{sy(w_lo):.2f}" stroke="{colour}" stroke-width="1"/>')
            for wy in (w_lo, w_hi):
                parts.append(f'<line x1="{cx - bw / 4.0:.2f}" y1="{sy(wy):.2f}" '
                             f'x2="{cx + bw / 4.0:.2f}" y2="{sy(wy):.2f}" '
                             f'stroke="{colour}" stroke-width="1"/>')
            # Outlier dots.
            for ov in outliers:
                parts.append(f'<circle cx="{cx:.2f}" cy="{sy(ov):.2f}" r="2.5" '
                             f'fill="none" stroke="{colour}" stroke-width="1"/>')

    parts.append("</svg>")
    return "\n".join(parts)


def _kde(vals, grid, bandwidth):
    """Gaussian KDE density evaluated at each point of ``grid`` (pure stdlib)."""
    n = len(vals)
    if n == 0 or bandwidth <= 0:
        return [0.0] * len(grid)
    inv = 1.0 / (bandwidth * math.sqrt(2.0 * math.pi))
    out = []
    for g in grid:
        acc = 0.0
        for v in vals:
            u = (g - v) / bandwidth
            acc += math.exp(-0.5 * u * u)
        out.append(inv * acc / n)
    return out


def violin_svg(series, *, title: str = "", width: int = 480, height: int = 320,
               points: int = 48) -> str:
    """Violin plot: a mirrored Gaussian-KDE density silhouette per named series.

    ``series`` is ``[(name, values)]``. Each series gets a symmetric density
    outline (a small stdlib KDE with a Silverman-rule bandwidth) drawn about its
    slot centre, with the median marked.
    """
    from .stats import quantile

    margin_l, margin_r, margin_t, margin_b = 46, 16, 26, 32
    parts, geom = _frame(width, height, margin_l, margin_r, margin_t, margin_b, title)

    prepared = []
    all_y = []
    for name, values in series:
        vals = [v for v in values if math.isfinite(v)]
        prepared.append(vals)
        all_y.extend(vals)

    n = len(series)
    if all_y:
        ylo, yhi = _nice_range(min(all_y), max(all_y))
    else:
        ylo, yhi = 0.0, 1.0
    labels = [name for name, _v in series]
    _axes(parts, geom, 0.0, max(1, n), ylo, yhi, x_labels=labels)

    px0, py0, pw, ph = geom
    py1 = py0 + ph

    def sy(y):
        return py1 if yhi == ylo else py1 - (y - ylo) / (yhi - ylo) * ph

    if points < 2:
        points = 2
    if n:
        slot = pw / n
        half = slot * 0.42
        for i, vals in enumerate(prepared):
            if not vals:
                continue
            cx = px0 + slot * (i + 0.5)
            colour = _PALETTE[i % len(_PALETTE)]
            m = math.fsum(vals) / len(vals)
            sd = math.sqrt(math.fsum((v - m) ** 2 for v in vals) / len(vals))
            # Silverman's rule-of-thumb bandwidth; guard degenerate spread.
            bw = 1.06 * sd * len(vals) ** (-0.2) if sd > 0 else (yhi - ylo) * 0.05
            if bw <= 0:
                bw = (yhi - ylo) * 0.05 or 1.0
            grid = [ylo + (yhi - ylo) * k / (points - 1) for k in range(points)]
            dens = _kde(vals, grid, bw)
            dmax = max(dens) or 1.0
            # Right edge going up, then left edge coming back down -> closed shape.
            pts = [(cx + half * d / dmax, sy(g)) for g, d in zip(grid, dens)]
            pts += [(cx - half * d / dmax, sy(g))
                    for g, d in zip(reversed(grid), reversed(dens))]
            d = " ".join(f'{"M" if j == 0 else "L"}{x:.2f} {y:.2f}'
                         for j, (x, y) in enumerate(pts))
            parts.append(f'<path d="{d} Z" fill="{colour}" fill-opacity="0.35" '
                         f'stroke="{colour}" stroke-width="1.5"/>')
            med = quantile(vals, 0.5)
            parts.append(f'<line x1="{cx - half * 0.4:.2f}" y1="{sy(med):.2f}" '
                         f'x2="{cx + half * 0.4:.2f}" y2="{sy(med):.2f}" '
                         f'stroke="{colour}" stroke-width="2"/>')

    parts.append("</svg>")
    return "\n".join(parts)


def qq_svg(values, *, title: str = "", width: int = 480, height: int = 320) -> str:
    """Normal Q-Q plot: sample quantiles vs theoretical normal quantiles.

    Points are ``(theoretical, sample)`` using the Blom plotting position
    ``(i - 0.5) / n`` mapped through :func:`stats.normal_ppf`. A reference line
    (mean + z*stdev of the sample) is drawn for a visual normality check.
    """
    from .stats import normal_ppf

    margin_l, margin_r, margin_t, margin_b = 46, 16, 26, 30
    parts, geom = _frame(width, height, margin_l, margin_r, margin_t, margin_b, title)

    vals = sorted(v for v in values if math.isfinite(v))
    n = len(vals)
    pts = []
    if n >= 1:
        m = math.fsum(vals) / n
        sd = math.sqrt(math.fsum((v - m) ** 2 for v in vals) / n) if n > 1 else 0.0
        for i, v in enumerate(vals):
            p = (i + 0.5) / n
            theo = normal_ppf(p)
            pts.append((theo, v))
    else:
        m, sd = 0.0, 0.0

    if pts:
        xs = [t for t, _s in pts]
        ys = [s for _t, s in pts]
        xlo, xhi = _nice_range(min(xs), max(xs))
        ylo, yhi = _nice_range(min(ys), max(ys))
    else:
        xlo, xhi, ylo, yhi = -1.0, 1.0, 0.0, 1.0
    _axes(parts, geom, xlo, xhi, ylo, yhi)

    px0, py0, pw, ph = geom
    py1 = py0 + ph

    def sx(x):
        return px0 if xhi == xlo else px0 + (x - xlo) / (xhi - xlo) * pw

    def sy(y):
        return py1 if yhi == ylo else py1 - (y - ylo) / (yhi - ylo) * ph

    # Reference line: sample value == mean + z * sd across the theoretical range.
    parts.append(f'<line x1="{sx(xlo):.2f}" y1="{sy(m + sd * xlo):.2f}" '
                 f'x2="{sx(xhi):.2f}" y2="{sy(m + sd * xhi):.2f}" '
                 'stroke="#c62828" stroke-width="1.5" stroke-dasharray="5,3"/>')
    for theo, v in pts:
        parts.append(f'<circle cx="{sx(theo):.2f}" cy="{sy(v):.2f}" r="3" '
                     f'fill="{_PALETTE[0]}" fill-opacity="0.75" '
                     'stroke="#0d3c78" stroke-width="0.5"/>')

    parts.append("</svg>")
    return "\n".join(parts)


def ecdf_svg(series, *, title: str = "", width: int = 480, height: int = 320) -> str:
    """Empirical CDF (step function) of one or more named series.

    ``series`` is ``[(name, values)]``. Each series is drawn as a right-continuous
    step curve rising from 0 to 1, in a distinct colour with a legend entry.
    """
    margin_l, margin_r, margin_t, margin_b = 46, 16, 26, 30
    parts, geom = _frame(width, height, margin_l, margin_r, margin_t, margin_b, title)

    prepared = []
    all_x = []
    for name, values in series:
        vals = sorted(v for v in values if math.isfinite(v))
        prepared.append((name, vals))
        all_x.extend(vals)

    if all_x:
        xlo, xhi = _nice_range(min(all_x), max(all_x))
    else:
        xlo, xhi = 0.0, 1.0
    ylo, yhi = 0.0, 1.0
    _axes(parts, geom, xlo, xhi, ylo, yhi)

    px0, py0, pw, ph = geom
    py1 = py0 + ph

    def sx(x):
        return px0 if xhi == xlo else px0 + (x - xlo) / (xhi - xlo) * pw

    def sy(y):
        return py1 if yhi == ylo else py1 - (y - ylo) / (yhi - ylo) * ph

    legend_entries = []
    for i, (name, vals) in enumerate(prepared):
        colour = _PALETTE[i % len(_PALETTE)]
        legend_entries.append((name, colour))
        if not vals:
            continue
        n = len(vals)
        # Build the staircase: start at y=0 on the left, step up at each value.
        d = [f'M{sx(xlo):.2f} {sy(0.0):.2f}']
        prev_y = 0.0
        for j, v in enumerate(vals):
            x = sx(v)
            d.append(f'L{x:.2f} {sy(prev_y):.2f}')
            y = (j + 1) / n
            d.append(f'L{x:.2f} {sy(y):.2f}')
            prev_y = y
        d.append(f'L{sx(xhi):.2f} {sy(prev_y):.2f}')
        parts.append(f'<path d="{" ".join(d)}" fill="none" stroke="{colour}" '
                     'stroke-width="2"/>')
    if legend_entries:
        _legend(parts, geom, legend_entries)

    parts.append("</svg>")
    return "\n".join(parts)


def heatmap_svg(matrix, labels=None, *, title: str = "", width: int = 480,
                height: int = 320) -> str:
    """Heatmap of a 2-D ``matrix`` coloured with the viridis colormap.

    ``matrix`` is a list of equal-length rows. ``labels`` (optional) name the
    rows/columns (a square correlation-style matrix); they are drawn along the
    left and bottom. A value scale (colour gradient with min/max) sits at the right.
    """
    from ..format.colormap import colorize

    rows = [list(r) for r in matrix]
    nrows = len(rows)
    ncols = len(rows[0]) if rows else 0
    flat = [v for r in rows for v in r if math.isfinite(v)]

    margin_l = 60 if labels else 30
    margin_r = 56  # room for the value scale
    margin_t = 26
    margin_b = 40 if labels else 24
    parts, geom = _frame(width, height, margin_l, margin_r, margin_t, margin_b, title)
    px0, py0, pw, ph = geom

    if not flat or ncols == 0:
        parts.append("</svg>")
        return "\n".join(parts)

    vmin, vmax = min(flat), max(flat)
    cw = pw / ncols
    chh = ph / nrows
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            if not math.isfinite(val):
                continue
            r, g, b = colorize(val, vmin, vmax, "viridis")
            x = px0 + ci * cw
            y = py0 + ri * chh
            parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" '
                         f'width="{cw + 0.5:.2f}" height="{chh + 0.5:.2f}" '
                         f'fill="rgb({r},{g},{b})"/>')

    # Optional axis labels (row labels at left, column labels at bottom).
    if labels:
        for i, lab in enumerate(labels[:nrows]):
            y = py0 + (i + 0.5) * chh
            parts.append(
                f'<text x="{px0 - 6:.1f}" y="{y + 3:.1f}" text-anchor="end" '
                f'font-family="sans-serif" font-size="10" '
                f'fill="#333333">{_svg_escape(str(lab))}</text>')
        for i, lab in enumerate(labels[:ncols]):
            x = px0 + (i + 0.5) * cw
            parts.append(
                f'<text x="{x:.1f}" y="{py0 + ph + 14:.1f}" text-anchor="middle" '
                f'font-family="sans-serif" font-size="10" '
                f'fill="#333333">{_svg_escape(str(lab))}</text>')

    # Value scale: a vertical gradient bar with min/max labels, right of the grid.
    bar_x = px0 + pw + 12
    bar_w = 12
    steps = 32
    for s in range(steps):
        frac = s / (steps - 1) if steps > 1 else 0.0
        val = vmin + (vmax - vmin) * frac
        r, g, b = colorize(val, vmin, vmax, "viridis")
        seg_h = ph / steps
        # Top of the bar is the max value.
        y = py0 + ph - (s + 1) * seg_h
        parts.append(f'<rect x="{bar_x:.1f}" y="{y:.2f}" width="{bar_w}" '
                     f'height="{seg_h + 0.5:.2f}" fill="rgb({r},{g},{b})"/>')
    parts.append(f'<rect x="{bar_x:.1f}" y="{py0:.1f}" width="{bar_w}" '
                 f'height="{ph:.1f}" fill="none" stroke="#333333" stroke-width="0.5"/>')
    parts.append(
        f'<text x="{bar_x + bar_w + 3:.1f}" y="{py0 + 4:.1f}" text-anchor="start" '
        f'font-family="sans-serif" font-size="9" '
        f'fill="#333333">{_svg_escape(_fmt(vmax))}</text>')
    parts.append(
        f'<text x="{bar_x + bar_w + 3:.1f}" y="{py0 + ph:.1f}" text-anchor="start" '
        f'font-family="sans-serif" font-size="9" '
        f'fill="#333333">{_svg_escape(_fmt(vmin))}</text>')

    parts.append("</svg>")
    return "\n".join(parts)
