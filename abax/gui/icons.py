"""Hand-drawn vector toolbar/menu icons (QPainter, theme-tinted, no asset files).

``make_icon(name)`` returns a crisp monochrome ``QIcon`` drawn from primitives in
a 22-px box, tinted with the application's text colour so it reads on any theme.
Keeps abax asset-free — no PNG/SVG files to bundle. Unknown names yield a small
neutral dot so the toolbar never breaks.
"""

from __future__ import annotations

from ._qtcompat import (
    QApplication,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPointF,
    QRectF,
    Qt,
)

_SIZE = 22
_M = 4  # margin -> content area ~[4, 18]


def _icon_color() -> QColor:
    app = QApplication.instance()
    if app is not None:
        return app.palette().windowText().color()
    return QColor("#c8d0da")


def _accent() -> QColor:
    c = _icon_color()
    # a faintly tinted fill for "highlighted" bands in grid icons
    return QColor(c.red(), c.green(), c.blue(), 60)


# --- individual glyphs (painter is set up with a rounded 1.6px pen) ----------

def _new(p):
    p.drawRoundedRect(QRectF(6, 3, 9, 16), 1.5, 1.5)
    p.drawLine(QPointF(12, 3), QPointF(12, 6))
    p.drawLine(QPointF(12, 6), QPointF(15, 6))


def _open(p):
    path = QPainterPath()
    path.moveTo(4, 7)
    path.lineTo(8, 7)
    path.lineTo(9.5, 9)
    path.lineTo(18, 9)
    path.lineTo(18, 17)
    path.lineTo(4, 17)
    path.closeSubpath()
    p.drawPath(path)


def _save(p):
    p.drawRoundedRect(QRectF(4, 4, 14, 14), 1.5, 1.5)
    p.drawRect(QRectF(7, 4, 8, 4))       # slider
    p.drawRect(QRectF(7, 12, 8, 6))      # label


def _copy(p):
    p.drawRoundedRect(QRectF(5, 4, 8, 10), 1.2, 1.2)
    p.drawRoundedRect(QRectF(9, 8, 8, 10), 1.2, 1.2)


def _paste(p):
    p.drawRoundedRect(QRectF(5, 5, 12, 13), 1.5, 1.5)
    p.drawRect(QRectF(8, 3, 6, 3))       # clip
    p.drawLine(QPointF(8, 10), QPointF(14, 10))
    p.drawLine(QPointF(8, 13), QPointF(14, 13))


def _fill_down(p):
    p.drawLine(QPointF(11, 3), QPointF(11, 14))
    path = QPainterPath()
    path.moveTo(7, 11)
    path.lineTo(11, 16)
    path.lineTo(15, 11)
    p.drawPath(path)
    p.drawLine(QPointF(6, 19), QPointF(16, 19))


def _find(p):
    p.drawEllipse(QRectF(5, 5, 8, 8))
    p.drawLine(QPointF(12.5, 12.5), QPointF(17, 17))


def _calc(p, display=None):
    p.drawRoundedRect(QRectF(5, 3, 12, 16), 1.8, 1.8)
    if display is not None:
        p.fillRect(QRectF(7, 5, 8, 3), display)
    p.drawRect(QRectF(7, 5, 8, 3))
    for r in range(3):
        for c in range(3):
            p.drawEllipse(QPointF(8 + c * 3, 11 + r * 3), 0.7, 0.7)


def _hp16c(p):
    _calc(p, display=QColor("#7bf2a8"))   # HP-green display to distinguish


def _graph(p):
    p.drawLine(QPointF(5, 4), QPointF(5, 17))
    p.drawLine(QPointF(5, 17), QPointF(18, 17))
    path = QPainterPath()
    path.moveTo(5, 14)
    path.cubicTo(9, 5, 12, 16, 18, 7)
    p.drawPath(path)


def _terminal(p):
    p.drawRoundedRect(QRectF(4, 5, 14, 12), 1.5, 1.5)
    path = QPainterPath()
    path.moveTo(7, 9)
    path.lineTo(9.5, 11)
    path.lineTo(7, 13)
    p.drawPath(path)
    p.drawLine(QPointF(10.5, 13), QPointF(14, 13))


def _equation(p):
    # square-root radical reads as "math"
    path = QPainterPath()
    path.moveTo(4, 12)
    path.lineTo(7, 12)
    path.lineTo(9.5, 17)
    path.lineTo(13, 5)
    path.lineTo(18, 5)
    p.drawPath(path)


def _python(p):
    for i, x in enumerate((6, 9.5)):
        path = QPainterPath()
        path.moveTo(x, 7)
        path.lineTo(x + 3, 11)
        path.lineTo(x, 15)
        p.drawPath(path)
    p.drawLine(QPointF(13.5, 15), QPointF(17, 15))


def _palette(p):
    p.drawRoundedRect(QRectF(4, 5, 14, 5), 2, 2)
    p.drawLine(QPointF(6, 14), QPointF(14, 14))
    p.drawLine(QPointF(6, 17), QPointF(12, 17))


def _undo(p):
    path = QPainterPath()
    path.moveTo(13, 7)
    path.cubicTo(17, 7, 17, 16, 11, 16)     # curved arrow shaft
    p.drawPath(path)
    head = QPainterPath()                    # arrowhead at the left
    head.moveTo(9, 4)
    head.lineTo(5, 7.5)
    head.lineTo(9, 11)
    p.drawPath(head)


def _redo(p):
    path = QPainterPath()
    path.moveTo(9, 7)
    path.cubicTo(5, 7, 5, 16, 11, 16)
    p.drawPath(path)
    head = QPainterPath()
    head.moveTo(13, 4)
    head.lineTo(17, 7.5)
    head.lineTo(13, 11)
    p.drawPath(head)


def _text_glyph(p, ch, bold=False, italic=False, underline=False):
    f = QFont()
    f.setPixelSize(15)
    f.setBold(bold)
    f.setItalic(italic)
    f.setUnderline(underline)
    p.setFont(f)
    p.drawText(QRectF(0, 0, _SIZE, _SIZE), int(Qt.AlignmentFlag.AlignCenter), ch)


def _bold(p):
    _text_glyph(p, "B", bold=True)


def _italic(p):
    _text_glyph(p, "I", italic=True)


def _underline(p):
    _text_glyph(p, "U", underline=True)
    p.drawLine(QPointF(7, 18), QPointF(15, 18))


def _hlines(p, anchor):
    for i, w in enumerate((12, 8, 12, 7)):
        y = 5 + i * 4
        x0 = 4 if anchor == "left" else (18 - w if anchor == "right" else 11 - w / 2)
        p.drawLine(QPointF(x0, y), QPointF(x0 + w, y))


def _align_left(p):
    _hlines(p, "left")


def _align_center(p):
    _hlines(p, "center")


def _align_right(p):
    _hlines(p, "right")


def _text_color(p):
    _text_glyph(p, "A")
    p.fillRect(QRectF(5, 18, 12, 2.5), QColor(220, 70, 70))   # red bar (sample swatch)


def _fill_color(p):
    path = QPainterPath()                                     # tilted paint bucket
    path.moveTo(6, 10)
    path.lineTo(12, 4)
    path.lineTo(17, 9)
    path.lineTo(11, 15)
    path.closeSubpath()
    p.drawPath(path)
    p.fillRect(QRectF(6, 16, 11, 3), QColor(90, 150, 230))    # paint puddle


def _sort(p):
    for i, w in enumerate((12, 9, 6, 3)):                     # descending bars + arrow
        p.drawLine(QPointF(4, 5 + i * 4), QPointF(4 + w, 5 + i * 4))
    p.drawLine(QPointF(17, 4), QPointF(17, 16))
    arr = QPainterPath()
    arr.moveTo(14, 13); arr.lineTo(17, 17); arr.lineTo(20, 13)
    p.drawPath(arr)


def _filter(p):
    path = QPainterPath()                                     # funnel
    path.moveTo(4, 5)
    path.lineTo(18, 5)
    path.lineTo(12.5, 11)
    path.lineTo(12.5, 18)
    path.lineTo(9.5, 16)
    path.lineTo(9.5, 11)
    path.closeSubpath()
    p.drawPath(path)


def _grid(p):
    p.drawRoundedRect(QRectF(4, 4, 14, 14), 1.2, 1.2)
    for t in (1, 2):
        p.drawLine(QPointF(4 + t * 14 / 3, 4), QPointF(4 + t * 14 / 3, 18))
        p.drawLine(QPointF(4, 4 + t * 14 / 3), QPointF(18, 4 + t * 14 / 3))


def _plus(p, cx, cy):
    p.drawLine(QPointF(cx - 2.4, cy), QPointF(cx + 2.4, cy))
    p.drawLine(QPointF(cx, cy - 2.4), QPointF(cx, cy + 2.4))


def _minus(p, cx, cy):
    p.drawLine(QPointF(cx - 2.4, cy), QPointF(cx + 2.4, cy))


def _band_row(p):
    p.fillRect(QRectF(4, 4, 14, 14 / 3), _accent())


def _band_col(p):
    p.fillRect(QRectF(4, 4, 14 / 3, 14), _accent())


def _insert_row(p):
    _band_row(p); _grid(p); _plus(p, 11, 4 + 14 / 6)


def _insert_col(p):
    _band_col(p); _grid(p); _plus(p, 4 + 14 / 6, 11)


def _delete_row(p):
    _band_row(p); _grid(p); _minus(p, 11, 4 + 14 / 6)


def _delete_col(p):
    _band_col(p); _grid(p); _minus(p, 4 + 14 / 6, 11)


def _stats(p):
    # ascending bar chart
    for x, top in ((5, 12), (10, 8), (15, 5)):
        r = QRectF(x, top, 3, 18 - top)
        p.fillRect(r, _accent())
        p.drawRect(r)


def _pivot(p):
    # grid with a highlighted header row + column (a pivot summary)
    p.fillRect(QRectF(4, 4, 14, 14 / 3), _accent())
    p.fillRect(QRectF(4, 4, 14 / 3, 14), _accent())
    _grid(p)


def _histogram(p):
    for x, top in ((5, 13), (9, 9), (13, 6), (17, 11)):
        r = QRectF(x, top, 3, 18 - top)
        p.fillRect(r, _accent())
        p.drawRect(r)


def _sheets(p):
    p.drawRoundedRect(QRectF(4, 6, 11, 12), 1.2, 1.2)
    p.drawRoundedRect(QRectF(8, 3, 11, 12), 1.2, 1.2)


_GLYPHS = {
    "new": _new, "open": _open, "save": _save, "copy": _copy, "paste": _paste,
    "stats": _stats, "pivot": _pivot, "histogram": _histogram, "sheets": _sheets,
    "fill_down": _fill_down, "undo": _undo, "redo": _redo,
    "bold": _bold, "italic": _italic, "underline": _underline,
    "align_left": _align_left, "align_center": _align_center,
    "align_right": _align_right, "text_color": _text_color,
    "fill_color": _fill_color, "sort": _sort, "filter": _filter,
    "find": _find, "calc": _calc, "hp16c": _hp16c,
    "graph": _graph, "terminal": _terminal, "equation": _equation,
    "python": _python, "palette": _palette,
    "insert_row": _insert_row, "insert_col": _insert_col,
    "delete_row": _delete_row, "delete_col": _delete_col, "grid": _grid,
}


def make_icon(name: str, size: int = _SIZE) -> QIcon:
    color = _icon_color()
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(color)
    pen.setWidthF(1.6)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    glyph = _GLYPHS.get(name)
    if glyph is not None:
        glyph(p)
    else:
        p.drawEllipse(QPointF(11, 11), 2, 2)
    p.end()
    return QIcon(pm)
