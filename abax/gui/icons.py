"""Hand-drawn vector toolbar/menu icons (QPainter, theme-tinted, no asset files).

``make_icon(name)`` returns a crisp monochrome ``QIcon`` drawn from primitives in
a 22-px box, tinted with the active abax theme's foreground so it reads on any
theme. Keeps abax asset-free — no PNG/SVG files to bundle. Unknown names yield a
small neutral dot so the toolbar never breaks.

Tint: call :func:`set_icon_color` on theme change so glyphs track the abax theme
(``Theme.fg_primary``) rather than the OS palette; icons already placed on actions
must be re-created (see ``MainWindow._icon_actions`` / ``apply_current_theme``).
Rendering scales to the requested ``size`` and honours the display's device-pixel
ratio, so glyphs stay crisp at any toolbar size and on HiDPI screens.
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
_M = 4    # margin -> content area ~[4, 18]
_R = 1.5  # shared corner radius for panel/card glyphs (one value across the set)

# A small, deliberate accent vocabulary. The set is otherwise monochrome; these
# three fixed hues are semantic wayfinding pops (they read the same on every
# theme). Kept intentionally minimal — do not add a fourth without cause.
ACCENT_TEXT = QColor(216, 74, 74)    # text-colour swatch (red)
ACCENT_FILL = QColor(74, 128, 224)   # fill-colour swatch (blue)
ACCENT_LCD = QColor(90, 214, 140)    # calculator display (green)

# When set (via set_icon_color), pins the monochrome tint so icons follow the
# abax theme instead of the OS palette's windowText.
_COLOR_OVERRIDE: QColor | None = None


def set_icon_color(color: QColor | None) -> None:
    """Pin the monochrome tint used by every glyph. Call on theme change with the
    theme's ``fg_primary``; pass ``None`` to fall back to the application palette."""
    global _COLOR_OVERRIDE
    _COLOR_OVERRIDE = color


def _icon_color() -> QColor:
    if _COLOR_OVERRIDE is not None:
        return _COLOR_OVERRIDE
    app = QApplication.instance()
    if app is not None:
        return app.palette().windowText().color()
    return QColor("#c8d0da")


def _accent(alpha: int = 60) -> QColor:
    """A tinted fill derived from the current tint (for highlighted bands/bars)."""
    c = _icon_color()
    return QColor(c.red(), c.green(), c.blue(), alpha)


# --- individual glyphs (painter is set up with a rounded 1.8px pen) -----------

def _new(p):
    p.drawRoundedRect(QRectF(6.5, 4, 9, 14), _R, _R)     # centred, inside the box
    p.drawLine(QPointF(12.5, 4), QPointF(12.5, 7))
    p.drawLine(QPointF(12.5, 7), QPointF(15.5, 7))


def _open(p):
    path = QPainterPath()                # folder, tab raised so it sits larger
    path.moveTo(4, 6)
    path.lineTo(8, 6)
    path.lineTo(9.5, 8)
    path.lineTo(18, 8)
    path.lineTo(18, 17)
    path.lineTo(4, 17)
    path.closeSubpath()
    p.drawPath(path)


def _save(p):
    p.drawRoundedRect(QRectF(4, 4, 14, 14), _R, _R)
    p.drawRect(QRectF(8.5, 5, 5.5, 3))   # metal shutter, inset & offset (reads as floppy)
    p.drawRect(QRectF(7, 11, 8, 5.5))    # label area, clear of the bottom edge


def _copy(p):
    p.drawRoundedRect(QRectF(5, 4, 8, 10), _R, _R)
    p.drawRoundedRect(QRectF(9, 8, 8, 10), _R, _R)


def _paste(p):
    p.drawRoundedRect(QRectF(5, 5, 12, 13), _R, _R)
    p.drawRect(QRectF(8, 3, 6, 3))       # clip
    p.drawLine(QPointF(8, 11), QPointF(14, 11))
    p.drawLine(QPointF(8, 14), QPointF(13, 14))


def _cut(p):
    # scissors: two finger-loops at the bottom, blades crossing up to open tips
    p.drawEllipse(QPointF(7, 15), 2.3, 2.3)              # loops sized to stay open at 16px
    p.drawEllipse(QPointF(13, 15), 2.3, 2.3)
    p.drawLine(QPointF(8.7, 13.3), QPointF(15.5, 4.5))   # left loop -> upper-right blade
    p.drawLine(QPointF(11.3, 13.3), QPointF(4.5, 4.5))   # right loop -> upper-left blade


def _fill_down(p):
    p.drawLine(QPointF(11, 3), QPointF(11, 14))
    path = QPainterPath()
    path.moveTo(7, 11)
    path.lineTo(11, 16)
    path.lineTo(15, 11)
    p.drawPath(path)
    p.drawLine(QPointF(6, 18), QPointF(16, 18))


def _find(p):
    p.drawEllipse(QRectF(5.5, 5, 8, 8))                  # lens shifted down-right
    p.drawLine(QPointF(13, 13), QPointF(16.5, 16.5))     # shorter handle, off the corner


def _calc(p, display=None):
    p.drawRoundedRect(QRectF(5, 3, 12, 16), _R, _R)
    if display is not None:
        p.fillRect(QRectF(7, 5, 8, 4), display)          # enlarged LCD
    p.drawRect(QRectF(7, 5, 8, 4))
    for r in range(2):                                   # 2x2 keys survive downscale
        for c in range(2):
            p.drawEllipse(QPointF(8.5 + c * 5, 12.5 + r * 3.3), 1.15, 1.15)


def _hp16c(p):
    _calc(p, display=ACCENT_LCD)   # green LCD from the accent vocabulary


def _graph(p):
    p.drawLine(QPointF(5.5, 4), QPointF(5.5, 16.5))      # y-axis (half-pixel)
    p.drawLine(QPointF(5.5, 16.5), QPointF(17.5, 16.5))  # x-axis
    path = QPainterPath()
    path.moveTo(5.5, 13.5)
    path.cubicTo(9, 5, 12, 16, 17.5, 7)
    p.drawPath(path)


def _terminal(p):
    p.drawRoundedRect(QRectF(4, 5, 14, 12), _R, _R)
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
    # a `>>>` REPL prompt — three chevrons + an input line, distinct from the
    # windowed `terminal` glyph (which reads as a shell).
    for i in range(3):
        x0 = 4 + i * 3.2
        ch = QPainterPath()
        ch.moveTo(x0, 7.5)
        ch.lineTo(x0 + 2.2, 10.5)
        ch.lineTo(x0, 13.5)
        p.drawPath(ch)
    p.drawLine(QPointF(13.8, 13.5), QPointF(17, 13.5))


def _palette(p):
    # command palette: a rounded command bar with a `>` prompt + input text — a
    # command runner (distinct from the `terminal` window and from a colour swatch).
    p.drawRoundedRect(QRectF(3.5, 8, 15, 6), 2.5, 2.5)
    chev = QPainterPath()
    chev.moveTo(6, 9.7)
    chev.lineTo(7.8, 11)
    chev.lineTo(6, 12.3)
    p.drawPath(chev)
    p.drawLine(QPointF(9.5, 11), QPointF(15, 11))


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
    f.setPixelSize(16)                       # fills the box better post-downscale
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
    p.drawLine(QPointF(7, 17.5), QPointF(15, 17.5))


def _hlines(p, anchor):
    # three rules with a ragged/flush edge so alignment reads even at 16px
    for i, w in enumerate((11, 6, 9)):
        y = 6.5 + i * 4
        if anchor == "left":
            x0 = 5
        elif anchor == "right":
            x0 = 17 - w
        else:
            x0 = 11 - w / 2
        p.drawLine(QPointF(x0, y), QPointF(x0 + w, y))


def _align_left(p):
    _hlines(p, "left")


def _align_center(p):
    _hlines(p, "center")


def _align_right(p):
    _hlines(p, "right")


def _text_color(p):
    _text_glyph(p, "A")
    p.fillRect(QRectF(5, 16.5, 12, 2.2), ACCENT_TEXT)   # swatch under the A (in the box)


def _fill_color(p):
    path = QPainterPath()                                     # tilted paint bucket
    path.moveTo(6, 10)
    path.lineTo(12, 4)
    path.lineTo(17, 9)
    path.lineTo(11, 15)
    path.closeSubpath()
    p.drawPath(path)
    p.fillRect(QRectF(6, 16, 11, 3), ACCENT_FILL)            # paint puddle


def _sort_bars(p, widths):
    for i, w in enumerate(widths):
        y = 5.5 + i * 4                       # half-pixel centres
        p.drawLine(QPointF(4, y), QPointF(4 + w, y))


def _varrow(p, x, up):
    """A vertical arrow at column ``x`` pointing up or down (for sort direction)."""
    head = QPainterPath()
    if up:
        p.drawLine(QPointF(x, 17), QPointF(x, 5))
        head.moveTo(x - 2.5, 8); head.lineTo(x, 5); head.lineTo(x + 2.5, 8)
    else:
        p.drawLine(QPointF(x, 5), QPointF(x, 17))
        head.moveTo(x - 2.5, 14); head.lineTo(x, 17); head.lineTo(x + 2.5, 14)
    p.drawPath(head)


def _sort(p):
    # generic (neutral) sort: descending bars + a plain down arrow — for the
    # "Sort..." dialog, where no direction is implied.
    _sort_bars(p, (12, 9, 6, 3))
    p.drawLine(QPointF(15, 4), QPointF(15, 15.5))
    arr = QPainterPath()
    arr.moveTo(12, 12.5); arr.lineTo(15, 15.5); arr.lineTo(18, 12.5)
    p.drawPath(arr)


def _sort_asc(p):
    # short -> tall bars with an up arrow: Sort ascending (A->Z / small->large)
    _sort_bars(p, (3, 6, 8, 10))
    _varrow(p, 15.5, up=True)


def _sort_desc(p):
    # tall -> short bars with a down arrow: Sort descending (Z->A / large->small)
    _sort_bars(p, (10, 8, 6, 3))
    _varrow(p, 15.5, up=False)


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
    # a 2x2 lattice: cells stay open when the icon is shrunk to 16px (a 3x3 grid
    # collapses into a solid block). The base for pivot/condformat.
    p.drawRoundedRect(QRectF(4, 4, 14, 14), _R, _R)
    p.drawLine(QPointF(11, 4), QPointF(11, 18))     # single vertical divider
    p.drawLine(QPointF(4, 11), QPointF(18, 11))     # single horizontal divider


def _grid_rows(p):
    # outer frame + one horizontal divider (two rows, no vertical rule) — leaves a
    # clean row for the +/- so the insert/delete mark never crosses a line.
    p.drawRoundedRect(QRectF(4, 4, 14, 14), _R, _R)
    p.drawLine(QPointF(4, 11), QPointF(18, 11))


def _grid_cols(p):
    p.drawRoundedRect(QRectF(4, 4, 14, 14), _R, _R)
    p.drawLine(QPointF(11, 4), QPointF(11, 18))


_ARM = 3.0  # half-length of the +/- arms (~6px) — dominant at small sizes


def _plus(p, cx, cy):
    p.drawLine(QPointF(cx - _ARM, cy), QPointF(cx + _ARM, cy))
    p.drawLine(QPointF(cx, cy - _ARM), QPointF(cx, cy + _ARM))


def _minus(p, cx, cy):
    p.drawLine(QPointF(cx - _ARM, cy), QPointF(cx + _ARM, cy))


def _insert_row(p):          # generic (= "above"); kept for the toolbar
    p.fillRect(QRectF(4, 4, 14, 7), _accent(100))   # highlighted top row
    _grid_rows(p)
    _plus(p, 11, 7.5)                                # bold + in the clear top row


def _insert_row_above(p):
    _insert_row(p)


def _insert_row_below(p):
    p.fillRect(QRectF(4, 11, 14, 7), _accent(100))   # highlighted bottom row
    _grid_rows(p)
    _plus(p, 11, 14.5)


def _insert_col(p):          # generic (= "left"); kept for the toolbar
    p.fillRect(QRectF(4, 4, 7, 14), _accent(100))    # highlighted left column
    _grid_cols(p)
    _plus(p, 7.5, 11)


def _insert_col_left(p):
    _insert_col(p)


def _insert_col_right(p):
    p.fillRect(QRectF(11, 4, 7, 14), _accent(100))   # highlighted right column
    _grid_cols(p)
    _plus(p, 14.5, 11)


def _delete_row(p):
    p.fillRect(QRectF(4, 4, 14, 7), _accent(100))
    _grid_rows(p)
    _minus(p, 11, 7.5)


def _delete_col(p):
    p.fillRect(QRectF(4, 4, 7, 14), _accent(100))
    _grid_cols(p)
    _minus(p, 7.5, 11)


def _condformat(p):
    # a table with one cell coloured by a rule
    _grid(p)
    p.fillRect(QRectF(11.5, 11.5, 6, 6), _accent(150))


def _stats(p):
    # ascending bar chart — solid tinted bars on a shared baseline (no outline mud)
    for x, top in ((4, 12), (9, 8), (14, 4)):
        p.fillRect(QRectF(x, top, 4, 18 - top), _accent(150))


def _pivot(p):
    # a summary table: bold header row + column framing the body (distinct from
    # the insert/grid family, which have no header framing).
    p.drawRoundedRect(QRectF(4, 4, 14, 14), _R, _R)
    p.fillRect(QRectF(4, 4, 14, 5), _accent(110))   # header row
    p.fillRect(QRectF(4, 4, 5, 14), _accent(110))   # header column
    p.drawLine(QPointF(9, 4), QPointF(9, 18))        # header column divider
    p.drawLine(QPointF(4, 9), QPointF(18, 9))        # header row divider


def _histogram(p):
    # four contiguous bins (a distribution), solid tinted, within the box
    for x, top in ((4, 13), (7.5, 8), (11, 5), (14.5, 10)):
        p.fillRect(QRectF(x, top, 3, 18 - top), _accent(150))


def _sheets(p):
    p.drawRoundedRect(QRectF(7.5, 4, 10.5, 11), _R, _R)   # back page
    p.drawRoundedRect(QRectF(4, 7, 10.5, 11), _R, _R)     # front page (on top)
    p.drawLine(QPointF(5.5, 10.5), QPointF(13, 10.5))     # header rule -> reads as a sheet


_GLYPHS = {
    "new": _new, "open": _open, "save": _save, "copy": _copy, "paste": _paste,
    "cut": _cut,
    "stats": _stats, "pivot": _pivot, "histogram": _histogram, "sheets": _sheets,
    "fill_down": _fill_down, "undo": _undo, "redo": _redo,
    "bold": _bold, "italic": _italic, "underline": _underline,
    "align_left": _align_left, "align_center": _align_center,
    "align_right": _align_right, "text_color": _text_color,
    "fill_color": _fill_color, "sort": _sort, "sort_asc": _sort_asc,
    "sort_desc": _sort_desc, "filter": _filter, "condformat": _condformat,
    "find": _find, "calc": _calc, "hp16c": _hp16c,
    "graph": _graph, "terminal": _terminal, "equation": _equation,
    "python": _python, "palette": _palette,
    "insert_row": _insert_row, "insert_col": _insert_col,
    "insert_row_above": _insert_row_above, "insert_row_below": _insert_row_below,
    "insert_col_left": _insert_col_left, "insert_col_right": _insert_col_right,
    "delete_row": _delete_row, "delete_col": _delete_col, "grid": _grid,
}


def make_icon(name: str, size: int = _SIZE, color: QColor | None = None) -> QIcon:
    """Render glyph ``name`` at ``size`` logical px, tinted with ``color`` (or the
    current icon colour). Scales the painter so any size renders true, and draws at
    the display's device-pixel ratio so strokes stay crisp on HiDPI screens."""
    app = QApplication.instance()
    dpr = float(app.devicePixelRatio()) if app is not None else 1.0
    if color is not None:
        prev = _COLOR_OVERRIDE
        set_icon_color(color)
    try:
        col = _icon_color()
        px = max(1, round(size * dpr))
        pm = QPixmap(px, px)
        pm.fill(Qt.GlobalColor.transparent)
        pm.setDevicePixelRatio(dpr)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.scale(px / _SIZE, px / _SIZE)   # map the 22-px design box to device pixels
        pen = QPen(col)
        pen.setWidthF(1.8)
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
    finally:
        if color is not None:
            set_icon_color(prev)
