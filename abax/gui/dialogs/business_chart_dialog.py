"""Business chart dialog — the grid selection as a Waterfall / Sunburst /
Treemap / Sparkline chart, rendered to standalone SVG with a live preview.

Pick a chart type, *Refresh* to rebuild from the current selection, and *Save
SVG…* to write the picture to disk. The selection is read as ``(label, value)``
rows: with two or more selected columns the first column labels each row and the
next column supplies the number; with a single column the row index labels it and
the column itself is the value. Non-numeric cells are skipped, so a header row or
a stray note never breaks the chart.

The number-crunching lives in :mod:`abax.core.science.chartsvg` (the
``waterfall_svg`` / ``sunburst_svg`` / ``treemap_svg`` / ``sparkline_svg``
renderers); this file only maps the selection onto them and shows the result. The
mapping is a pure, Qt-free method (:meth:`chart_svg`) so it can be unit-tested
without a running preview. The preview uses ``QSvgWidget`` when the Qt build ships
QtSvgWidgets; otherwise the dialog stays fully usable through *Save SVG…*.
"""

from __future__ import annotations

from pathlib import Path

from .._qtcompat import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)
from ...core.science import chartsvg

# QtSvgWidgets is optional: some Qt builds omit it. When absent the preview is
# skipped and the dialog notes that Save SVG still works.
try:  # pragma: no cover - presence depends on the installed Qt build
    from .._qtcompat import QSvgWidget  # type: ignore
except ImportError:  # pragma: no cover
    QSvgWidget = None  # type: ignore

_KINDS = ["Waterfall", "Sunburst", "Treemap", "Sparkline"]
_EMPTY_NOTE = "Select a column (or label+value columns) of numbers, then Refresh."


def _svg_escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _as_float(value) -> float | None:
    """Coerce a cell value to ``float`` or return ``None`` if it is not numeric."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Fallback SVG renderers.
#
# The canonical renderers live in :mod:`chartsvg`; when a given one is present
# there it is preferred (see :meth:`BusinessChartDialog.chart_svg`). These local
# implementations keep the dialog self-contained and testable on any build.
# --------------------------------------------------------------------------- #

def _placeholder_svg(message: str, *, width: int = 480, height: int = 300) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="white"/>'
        f'<text x="{width / 2:.1f}" y="{height / 2:.1f}" text-anchor="middle" '
        f'font-family="sans-serif" font-size="13" fill="#666666">'
        f'{_svg_escape(message)}</text></svg>'
    )


def _waterfall_svg(labels, deltas, *, total=True, title="", width=480, height=300):
    margin_l, margin_r, margin_t, margin_b = 46, 16, 26, 40
    pw = width - margin_l - margin_r
    ph = height - margin_t - margin_b
    px0, py0 = margin_l, margin_t

    steps = list(zip(labels, deltas))
    cum = 0.0
    running = []
    for lab, d in steps:
        running.append((lab, cum, cum + d, d))
        cum += d
    if total:
        running.append(("Total", 0.0, cum, cum))

    tops = [t for _l, _s, t, _d in running] + [s for _l, s, _t, _d in running] + [0.0]
    ylo, yhi = min(tops), max(tops)
    if ylo == yhi:
        yhi = ylo + 1.0

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<rect x="{px0}" y="{py0}" width="{pw}" height="{ph}" fill="none" '
        f'stroke="#333333" stroke-width="1"/>',
    ]
    if title:
        parts.append(
            f'<text x="{width / 2:.1f}" y="16" text-anchor="middle" '
            f'font-family="sans-serif" font-size="13" font-weight="bold">'
            f'{_svg_escape(title)}</text>')

    def sy(v):
        return py0 + ph - (v - ylo) / (yhi - ylo) * ph

    n = len(running) or 1
    slot = pw / n
    bw = slot * 0.6
    for i, (lab, start, end, d) in enumerate(running):
        cx = px0 + slot * (i + 0.5)
        y_top = sy(max(start, end))
        y_bot = sy(min(start, end))
        colour = "#1565c0" if i == len(running) - 1 and total else (
            "#2e7d32" if d >= 0 else "#c62828")
        parts.append(
            f'<rect x="{cx - bw / 2:.2f}" y="{y_top:.2f}" width="{bw:.2f}" '
            f'height="{max(1.0, y_bot - y_top):.2f}" fill="{colour}" '
            f'stroke="#0d3c78" stroke-width="0.5"/>')
        parts.append(
            f'<text x="{cx:.2f}" y="{py0 + ph + 14:.1f}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="10" fill="#333333">'
            f'{_svg_escape(lab)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _treemap_svg(items, *, title="", width=480, height=300):
    margin_t = 26 if title else 6
    px0, py0 = 6, margin_t
    pw = width - 12
    ph = height - margin_t - 6
    pairs = [(n, abs(_as_float(v) or 0.0)) for n, v in items]
    pairs = [(n, v) for n, v in pairs if v > 0]
    total = sum(v for _n, v in pairs)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
    ]
    if title:
        parts.append(
            f'<text x="{width / 2:.1f}" y="16" text-anchor="middle" '
            f'font-family="sans-serif" font-size="13" font-weight="bold">'
            f'{_svg_escape(title)}</text>')

    palette = ("#1565c0", "#c62828", "#2e7d32", "#f9a825",
               "#6a1b9a", "#00838f", "#ef6c00", "#4e342e")
    if total > 0:
        # Slice-and-dice: at each step split the remaining box along its longer
        # side, giving this item its share of the value still to be placed.
        x, y, w, h = px0, py0, pw, ph
        for i, (name, v) in enumerate(pairs):
            last = i == len(pairs) - 1
            share = 1.0 if last else v / _remaining(pairs, i, total)
            if w >= h:
                cw = w * share
                rect = (x, y, cw, h)
                x += cw
                w -= cw
            else:
                chh = h * share
                rect = (x, y, w, chh)
                y += chh
                h -= chh
            rx, ry, rw, rh = rect
            colour = palette[i % len(palette)]
            parts.append(
                f'<rect x="{rx:.2f}" y="{ry:.2f}" width="{max(0.0, rw):.2f}" '
                f'height="{max(0.0, rh):.2f}" fill="{colour}" fill-opacity="0.85" '
                f'stroke="white" stroke-width="1.5"/>')
            if rw > 34 and rh > 16:
                parts.append(
                    f'<text x="{rx + 4:.2f}" y="{ry + 14:.2f}" '
                    f'font-family="sans-serif" font-size="10" fill="white">'
                    f'{_svg_escape(name)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _remaining(pairs, i, total):
    """Value still to be laid out from index ``i`` onward (guards divide-by-zero)."""
    rem = sum(v for _n, v in pairs[i:])
    return rem if rem > 0 else 1.0


def _sunburst_svg(tree, *, title="", width=480, height=300):
    import math

    cx, cy = width / 2.0, height / 2.0 + (10 if title else 0)
    r_inner = 26.0
    r_outer = min(width, height) * 0.42
    children = list(tree.get("children", []))
    total = sum(abs(_as_float(c.get("value")) or 0.0) for c in children)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
    ]
    if title:
        parts.append(
            f'<text x="{width / 2:.1f}" y="16" text-anchor="middle" '
            f'font-family="sans-serif" font-size="13" font-weight="bold">'
            f'{_svg_escape(title)}</text>')

    palette = ("#1565c0", "#c62828", "#2e7d32", "#f9a825",
               "#6a1b9a", "#00838f", "#ef6c00", "#4e342e")
    parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r_inner:.2f}" '
                 f'fill="#eeeeee" stroke="#333333" stroke-width="0.5"/>')
    if total > 0:
        a0 = -math.pi / 2.0
        for i, c in enumerate(children):
            v = abs(_as_float(c.get("value")) or 0.0)
            if v <= 0:
                continue
            a1 = a0 + 2.0 * math.pi * v / total
            large = 1 if (a1 - a0) > math.pi else 0
            x0i, y0i = cx + r_inner * math.cos(a0), cy + r_inner * math.sin(a0)
            x0o, y0o = cx + r_outer * math.cos(a0), cy + r_outer * math.sin(a0)
            x1o, y1o = cx + r_outer * math.cos(a1), cy + r_outer * math.sin(a1)
            x1i, y1i = cx + r_inner * math.cos(a1), cy + r_inner * math.sin(a1)
            colour = palette[i % len(palette)]
            d = (f'M{x0i:.2f} {y0i:.2f} L{x0o:.2f} {y0o:.2f} '
                 f'A{r_outer:.2f} {r_outer:.2f} 0 {large} 1 {x1o:.2f} {y1o:.2f} '
                 f'L{x1i:.2f} {y1i:.2f} '
                 f'A{r_inner:.2f} {r_inner:.2f} 0 {large} 0 {x0i:.2f} {y0i:.2f} Z')
            parts.append(f'<path d="{d}" fill="{colour}" fill-opacity="0.85" '
                         f'stroke="white" stroke-width="1"/>')
            am = (a0 + a1) / 2.0
            rl = (r_inner + r_outer) / 2.0
            lx, ly = cx + rl * math.cos(am), cy + rl * math.sin(am)
            parts.append(
                f'<text x="{lx:.2f}" y="{ly:.2f}" text-anchor="middle" '
                f'font-family="sans-serif" font-size="9" fill="white">'
                f'{_svg_escape(c.get("name", ""))}</text>')
            a0 = a1
    parts.append("</svg>")
    return "\n".join(parts)


def _sparkline_svg(values, *, title="", width=480, height=120):
    vals = [_as_float(v) for v in values]
    vals = [v for v in vals if v is not None]
    pad = 6
    pw = width - 2 * pad
    ph = height - 2 * pad
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
    ]
    if len(vals) >= 1:
        lo, hi = min(vals), max(vals)
        if lo == hi:
            hi = lo + 1.0
        n = len(vals)

        def sx(i):
            return pad if n <= 1 else pad + pw * i / (n - 1)

        def sy(v):
            return pad + ph - (v - lo) / (hi - lo) * ph

        d = " ".join(f'{"M" if i == 0 else "L"}{sx(i):.2f} {sy(v):.2f}'
                     for i, v in enumerate(vals))
        parts.append(f'<path d="{d}" fill="none" stroke="#1565c0" stroke-width="1.5"/>')
        parts.append(f'<circle cx="{sx(n - 1):.2f}" cy="{sy(vals[-1]):.2f}" r="2.5" '
                     f'fill="#c62828"/>')
    parts.append("</svg>")
    return "\n".join(parts)


class BusinessChartDialog(QDialog):
    """Turn the current grid selection into a business SVG chart with preview."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Business chart")
        self.resize(560, 460)
        self._svg: str | None = None
        self._build()
        self.refresh()

    # --- construction ------------------------------------------------------ #

    def _build(self) -> None:
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Chart:", self))
        self._kind = QComboBox(self)
        self._kind.addItems(_KINDS)
        self._kind.currentIndexChanged.connect(self.refresh)
        top.addWidget(self._kind)
        top.addStretch(1)
        root.addLayout(top)

        if QSvgWidget is not None:
            self._preview = QSvgWidget(self)
            self._preview.setMinimumSize(480, 300)
            root.addWidget(self._preview, 1)
        else:
            self._preview = None
            note = QLabel("Preview unavailable (QtSvgWidgets not installed); "
                          "use Save SVG.", self)
            note.setWordWrap(True)
            root.addWidget(note, 1)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        bar = QHBoxLayout()
        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(refresh_btn)
        save_btn = QPushButton("Save SVG…", self)
        save_btn.clicked.connect(self._save_svg)
        bar.addWidget(save_btn)
        bar.addStretch(1)
        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.accept)
        bar.addWidget(close_btn)
        root.addLayout(bar)

    # --- selection -> data (pure) ------------------------------------------ #

    def _read_rows(self) -> list[tuple[str, float]]:
        """Read the selection into ``[(label, value)]``; skip non-numeric values.

        Two or more selected columns: the first column labels each row and the
        next column is the value. A single column: the row index labels the row
        and the column itself is the value.
        """
        try:
            r1, c1, r2, c2 = self._win._selected_bounds()
            sheet = self._win._doc.workbook.sheet
        except Exception:
            return []
        multi = c2 > c1
        value_col = c1 + 1 if multi else c1
        rows: list[tuple[str, float]] = []
        for r in range(r1, r2 + 1):
            num = _as_float(sheet.get_value(r, value_col))
            if num is None:
                continue
            if multi:
                label = (sheet.get_raw(r, c1) or "").strip() or str(r + 1)
            else:
                label = str(r + 1)
            rows.append((label, num))
        return rows

    def chart_svg(self, kind: str, rows: list[tuple[str, float]]) -> str:
        """Render ``rows`` as SVG for ``kind`` (pure, Qt-free — unit-testable).

        Prefers the matching renderer in :mod:`abax.core.science.chartsvg` and
        falls back to a self-contained local renderer when that build of the
        module does not ship it.
        """
        if not rows:
            return _placeholder_svg(_EMPTY_NOTE)
        title = f"{kind} of selection"
        labels = [str(n) for n, _v in rows]
        values = [float(v) for _n, v in rows]
        if kind == "Waterfall":
            fn = getattr(chartsvg, "waterfall_svg", None)
            if fn is not None:
                return fn(labels, values, total=True, title=title)
            return _waterfall_svg(labels, values, total=True, title=title)
        if kind == "Treemap":
            items = list(zip(labels, values))
            fn = getattr(chartsvg, "treemap_svg", None)
            if fn is not None:
                return fn(items, title=title)
            return _treemap_svg(items, title=title)
        if kind == "Sparkline":
            fn = getattr(chartsvg, "sparkline_svg", None)
            if fn is not None:
                return fn(values)          # sparkline is frameless — no title arg
            return _sparkline_svg(values, title=title)
        # Sunburst (default): one level, children = selection rows.
        tree = {
            "name": title,
            "children": [{"name": n, "value": v} for n, v in zip(labels, values)],
        }
        fn = getattr(chartsvg, "sunburst_svg", None)
        if fn is not None:
            return fn(tree, title=title)
        return _sunburst_svg(tree, title=title)

    # --- actions ----------------------------------------------------------- #

    def refresh(self) -> None:
        rows = self._read_rows()
        kind = self._kind.currentText()
        self._svg = self.chart_svg(kind, rows)
        if not rows:
            self._status.setText(_EMPTY_NOTE)
        else:
            self._status.setText(f"{len(rows)} value(s) — {kind}")
        if self._preview is not None and self._svg:
            try:
                self._preview.load(bytearray(self._svg, "utf-8"))
            except Exception:
                pass

    def _save_svg(self) -> None:
        if not self._svg:
            self._status.setText("Nothing to save yet — Refresh first.")
            return
        path, _flt = QFileDialog.getSaveFileName(
            self, "Save chart SVG", "chart.svg", "SVG image (*.svg)")
        if not path:
            return
        if not path.lower().endswith(".svg"):
            path += ".svg"
        Path(path).write_text(self._svg, encoding="utf-8")
        self._status.setText(f"Saved SVG -> {path}")
        if hasattr(self._win, "_set_status"):
            self._win._set_status(f"business chart -> {path}")
