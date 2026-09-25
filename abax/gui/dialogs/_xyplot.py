"""A small, accessible XY line plot for the radio / circuit dialogs.

One data series drawn as a thin line, with optional labelled reference lines
(vertical markers such as "1τ" or "f0", horizontal thresholds such as an
exposure limit) and labelled points. Linear or log axes.

Accessibility — a chart is a picture, so it always travels with words:

* the canvas is keyboard-focusable and draws a visible focus ring;
* it carries an accessible *name* (what the chart is) and an accessible
  *description* (what it currently shows — the caller writes it from the same
  numbers it plotted), and fires ``DescriptionChanged`` when that changes so a
  screen reader can re-announce it;
* reference lines and points are labelled with text, never by colour alone;
* every dialog that uses it also shows the plotted data as a table.

Colours come from the widget palette, so every abax theme (including the
high-contrast ones) applies unchanged.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

from .._qtcompat import (
    QAccessible,
    QAccessibleEvent,
    QColor,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QPointF,
    QRectF,
    Qt,
    QWidget,
)


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    """Round-numbered linear tick positions covering ``[lo, hi]``."""
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return [lo]
    raw = (hi - lo) / max(1, count)
    mag = 10.0 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    first = math.ceil(lo / step - 1e-9) * step
    ticks = []
    t = first
    while t <= hi + step * 1e-9:
        ticks.append(0.0 if abs(t) < step * 1e-9 else t)
        t += step
    return ticks


def decade_ticks(lo: float, hi: float) -> list[float]:
    """Powers of ten covering ``[lo, hi]`` (both > 0)."""
    if lo <= 0 or hi <= 0:
        return []
    return [10.0 ** e for e in range(math.floor(math.log10(lo)), math.ceil(math.log10(hi)) + 1)
            if lo * (1 - 1e-9) <= 10.0 ** e <= hi * (1 + 1e-9)]


class XYPlot(QWidget):
    """A focusable single-series line chart with labelled reference lines."""

    def __init__(self, name: str, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 220)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(name)
        self._data: list[tuple[float, float]] = []
        self._x_label = ""
        self._y_label = ""
        self._log_x = False
        self._log_y = False
        self._x_range: tuple[float, float] | None = None
        self._y_range: tuple[float, float] | None = None
        self._vlines: list[tuple[float, str]] = []
        self._hlines: list[tuple[float, str]] = []
        self._points: list[tuple[float, float, str]] = []
        self._x_fmt: Callable[[float], str] = lambda v: f"{v:g}"
        self._y_fmt: Callable[[float], str] = lambda v: f"{v:g}"

    # --- configuration --------------------------------------------------------

    def set_axes(self, x_label: str, y_label: str, *, log_x: bool = False,
                 log_y: bool = False, x_range=None, y_range=None,
                 x_fmt: Callable[[float], str] | None = None,
                 y_fmt: Callable[[float], str] | None = None) -> None:
        self._x_label, self._y_label = x_label, y_label
        self._log_x, self._log_y = log_x, log_y
        self._x_range, self._y_range = x_range, y_range
        if x_fmt is not None:
            self._x_fmt = x_fmt
        if y_fmt is not None:
            self._y_fmt = y_fmt
        self.update()

    def set_data(self, data: Sequence[tuple[float, float]], *,
                 vlines: Sequence[tuple[float, str]] = (),
                 hlines: Sequence[tuple[float, str]] = (),
                 points: Sequence[tuple[float, float, str]] = ()) -> None:
        self._data = [(float(x), float(y)) for x, y in data
                      if math.isfinite(x) and math.isfinite(y)]
        self._vlines = list(vlines)
        self._hlines = list(hlines)
        self._points = list(points)
        self.update()

    def set_description(self, text: str) -> None:
        """Set the accessible description (and tooltip) and tell assistive
        technology it changed."""
        if text == self.accessibleDescription():
            return
        self.setAccessibleDescription(text)
        self.setToolTip(text)
        if QAccessible is not None and QAccessibleEvent is not None:
            try:
                QAccessible.updateAccessibility(
                    QAccessibleEvent(self, QAccessible.Event.DescriptionChanged))
            except Exception:  # noqa: BLE001 — never let a11y plumbing break drawing
                pass

    # --- geometry -----------------------------------------------------------

    def _bounds(self) -> tuple[float, float, float, float]:
        xs = [x for x, _ in self._data] + [x for x, _ in self._vlines]
        ys = [y for _, y in self._data] + [y for y, _ in self._hlines]
        if self._log_x:
            xs = [x for x in xs if x > 0]
        if self._log_y:
            ys = [y for y in ys if y > 0]
        x0, x1 = self._x_range or ((min(xs), max(xs)) if xs else (0.0, 1.0))
        y0, y1 = self._y_range or ((min(ys), max(ys)) if ys else (0.0, 1.0))
        if x1 <= x0:
            x1 = x0 + (abs(x0) or 1.0)
        if y1 <= y0:
            y1 = y0 + (abs(y0) or 1.0)
        return x0, x1, y0, y1

    @staticmethod
    def _t(v: float, lo: float, hi: float, log: bool) -> float:
        if log:
            v, lo, hi = math.log10(max(v, 1e-300)), math.log10(lo), math.log10(hi)
        return (v - lo) / (hi - lo)

    # --- painting -----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        ink = pal.windowText().color()
        faint = QColor(ink)
        faint.setAlpha(45)
        muted = QColor(ink)
        muted.setAlpha(170)
        line = pal.highlight().color()
        fm = QFontMetricsF(self.font())
        th = fm.height()

        x0, x1, y0, y1 = self._bounds()
        xt = decade_ticks(x0, x1) if self._log_x else nice_ticks(x0, x1)
        yt = decade_ticks(y0, y1) if self._log_y else nice_ticks(y0, y1)
        ylab_w = max((fm.horizontalAdvance(self._y_fmt(t)) for t in yt), default=20.0)
        left = ylab_w + 12.0
        top = th + 8.0
        right = 16.0
        bottom = 2 * th + 14.0
        plot = QRectF(left, top, max(10.0, self.width() - left - right),
                      max(10.0, self.height() - top - bottom))

        def px(x: float) -> float:
            return plot.left() + self._t(x, x0, x1, self._log_x) * plot.width()

        def py(y: float) -> float:
            return plot.bottom() - self._t(y, y0, y1, self._log_y) * plot.height()

        # recessive solid grid + tick labels (text in ink, never series colour)
        p.setPen(QPen(faint, 1.0))
        for t in xt:
            p.drawLine(QPointF(px(t), plot.top()), QPointF(px(t), plot.bottom()))
        for t in yt:
            p.drawLine(QPointF(plot.left(), py(t)), QPointF(plot.right(), py(t)))
        p.setPen(QPen(muted, 1.0))
        p.drawRect(plot)
        for t in xt:
            s = self._x_fmt(t)
            w = fm.horizontalAdvance(s)
            # keep edge labels inside the widget rather than clipping them
            x = min(max(px(t) - w / 2, 2.0), self.width() - w - 2.0)
            p.drawText(QPointF(x, plot.bottom() + th), s)
        for t in yt:
            s = self._y_fmt(t)
            p.drawText(QPointF(plot.left() - 6 - fm.horizontalAdvance(s), py(t) + th / 3), s)
        p.setPen(QPen(ink, 1.0))
        p.drawText(QPointF(plot.center().x() - fm.horizontalAdvance(self._x_label) / 2,
                           self.height() - 6), self._x_label)
        p.drawText(QPointF(4, th), self._y_label)

        p.save()
        p.setClipRect(plot.adjusted(-1, -1, 1, 1))
        # reference lines: dashed = threshold / marker; labelled with text
        ref = QPen(muted, 1.0)
        ref.setStyle(Qt.PenStyle.DashLine)
        for x, label in self._vlines:
            if self._log_x and x <= 0:
                continue
            p.setPen(ref)
            p.drawLine(QPointF(px(x), plot.top()), QPointF(px(x), plot.bottom()))
            p.setPen(QPen(ink, 1.0))
            p.drawText(QPointF(px(x) + 3, plot.top() + th), label)
        for y, label in self._hlines:
            if self._log_y and y <= 0:
                continue
            p.setPen(ref)
            p.drawLine(QPointF(plot.left(), py(y)), QPointF(plot.right(), py(y)))
            p.setPen(QPen(ink, 1.0))
            s_w = fm.horizontalAdvance(label)
            p.drawText(QPointF(plot.right() - s_w - 4, py(y) - 3), label)

        # the series: one thin line in the theme's highlight colour
        pts = [(x, y) for x, y in self._data
               if (not self._log_x or x > 0) and (not self._log_y or y > 0)]
        if len(pts) > 1:
            path = QPainterPath()
            path.moveTo(QPointF(px(pts[0][0]), py(pts[0][1])))
            for x, y in pts[1:]:
                path.lineTo(QPointF(px(x), py(y)))
            p.setPen(QPen(line, 2.0))
            p.drawPath(path)

        # labelled points: a marker with a surface ring, text in ink
        for x, y, label in self._points:
            if (self._log_x and x <= 0) or (self._log_y and y <= 0):
                continue
            c = QPointF(px(x), py(y))
            p.setPen(QPen(pal.window().color(), 2.0))
            p.setBrush(line)
            p.drawEllipse(c, 4.5, 4.5)
            p.setPen(QPen(ink, 1.0))
            p.drawText(QPointF(c.x() + 7, c.y() - 6), label)
        p.restore()

        if self.hasFocus():
            focus = QPen(pal.highlight().color(), 2.0)
            p.setPen(focus)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(1, 1, self.width() - 2, self.height() - 2))
        p.end()
