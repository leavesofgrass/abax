"""TI-82/83/84-style graphing calculator faceplate — procedurally drawn.

Mirrors the HP :class:`abax.gui.faceplate.VoyagerFaceplate` approach: the whole
calculator (body, screen bezel, key caps, the blue **2nd** legends printed above
each key) is rendered with ``QPainter`` onto a base pixmap, and mouse clicks are
hit-tested against key rectangles. One brain
(:class:`abax.core.calc.ti_engine.TIEngine`) drives a home screen, a Y= editor, a
graph (with a live TRACE cursor), or a table.

The 82/83/84 (and the colour 84 Plus CE) differ only by a cosmetic SKIN — case
colour, model name, the TI-82's ``RANGE`` vs ``WINDOW`` label, and whether the
screen is the classic mono LCD or the CE colour panel.
"""

from __future__ import annotations

from .._qtcompat import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QWidget,
)
from ...core.calc.ti_engine import SCREEN_H, SCREEN_W, TIEngine
from ...core.graphing import compile_expr

# Per-model skin: (display name, body colour, accent, window-key label, colour screen?).
SKINS = {
    "ti83": ("TI-83 Plus", "#34373d", "#9fb4cc", "WINDOW", False),
    "ti82": ("TI-82", "#3a3a32", "#bdbd8a", "RANGE", False),
    "ti84": ("TI-84 Plus", "#243b54", "#8fc0e8", "WINDOW", False),
    "ti84ce": ("TI-84 Plus CE", "#7a1f2b", "#f0a6ad", "WINDOW", True),
}

_LCD_BG = QColor(0xc6, 0xd4, 0xbe)   # classic greenish-grey mono LCD
_LCD_INK = QColor(0x14, 0x18, 0x12)
_CE_BG = QColor(0xff, 0xff, 0xff)    # CE colour screen
_TRACE_COLOURS = [QColor("#0050ef"), QColor("#d80073"), QColor("#008a00"),
                  QColor("#a800ff"), QColor("#e07000"), QColor("#00a0a0")]

# Per-skin key-cap colours by kind. `second` is also the colour of the 2nd
# legends printed above each key, so the model's 2nd colour stays consistent.
#   TI-83 Plus: yellow 2nd, green ALPHA, blue setup/math/ENTER/arrow keys.
#   TI-82:      blue accents, grey ALPHA.   TI-84: blue 2nd + accents, green ALPHA.
#   TI-84 CE:   teal 2nd, green ALPHA, grey keys.
_SKIN_COLORS = {
    "ti83":   {"second": "#f0cf3a", "alpha": "#5cbf6a", "accent": "#2f6fb0",
               "func": "#4a4e57", "num": "#cdd1d7"},
    "ti82":   {"second": "#3a6ea5", "alpha": "#8a8f98", "accent": "#3a6ea5",
               "func": "#4a4e57", "num": "#cdd1d7"},
    "ti84":   {"second": "#3f7bbf", "alpha": "#5cbf6a", "accent": "#3f7bbf",
               "func": "#464a52", "num": "#cdd1d7"},
    "ti84ce": {"second": "#37b6c9", "alpha": "#5cbf6a", "accent": "#5e636c",
               "func": "#4a4e57", "num": "#d2d6db"},
}


def _text_color(hexc: str) -> QColor:
    """Black or white cap text, by the cap colour's luminance."""
    c = QColor(hexc)
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return QColor("#141414") if lum > 165 else QColor("#f4f4f6")

# Virtual canvas + screen window (key coords below are in this space).
_CANVAS_W, _CANVAS_H = 360, 604
_SCR_X, _SCR_Y, _SCR_W, _SCR_H = 30, 36, 300, 150
_COLX = [20, 88, 156, 224, 292]
_KW, _KH = 52, 30

class _Key:
    __slots__ = ("x", "y", "w", "h", "label", "action", "second_label",
                 "second", "kind")

    def __init__(self, x, y, w, h, label, action, second_label, second, kind):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.label, self.action = label, action
        self.second_label, self.second, self.kind = second_label, second, kind


def _build_keys(win_label: str) -> "list[_Key]":
    keys: list[_Key] = []

    def add(x, y, w, h, label, action, slabel, second, kind):
        keys.append(_Key(x, y, w, h, label, action, slabel, second, kind))

    def row(y, items, h=_KH):
        for i, it in enumerate(items):
            add(_COLX[i], y, _KW, h, *it)

    # Graphing function row (blue "setup/display" keys, just under the screen).
    row(196, [
        ("Y=", "@yedit", "STAT PLOT", "@statplot", "accent"),
        (win_label, "@window", "TBLSET", "@table", "accent"),
        ("ZOOM", "@zoom", "FORMAT", "@format", "accent"),
        ("TRACE", "@trace", "CALC", "@calc", "accent"),
        ("GRAPH", "@graph", "TABLE", "@table", "accent"),
    ], h=26)
    # 2nd (yellow) / MODE / DEL  +  the blue arrow diamond on the right.
    add(_COLX[0], 234, _KW, _KH, "2nd", "@2nd", "", None, "second")
    add(_COLX[1], 234, _KW, _KH, "MODE", "@mode", "QUIT", "@quit", "func")
    add(_COLX[2], 234, _KW, _KH, "DEL", "@del", "INS", "@ins", "func")
    add(248, 230, 64, 22, "▲", "@up", "", None, "accent")
    add(240, 256, 34, 22, "◄", "@left", "", None, "accent")
    add(286, 256, 34, 22, "►", "@right", "", None, "accent")
    add(248, 282, 64, 22, "▼", "@down", "", None, "accent")
    # ALPHA (green) / X,T,θ,n / STAT
    add(_COLX[0], 272, _KW, _KH, "ALPHA", "@alpha", "A-LOCK", "@alpha", "alpha")
    add(_COLX[1], 272, _KW, _KH, "X,T,θ,n", "X", "LINK", None, "func")
    add(_COLX[2], 272, _KW, _KH, "STAT", "@stat", "LIST", "@stat", "func")
    # Full rows.
    row(318, [
        ("MATH", "@math", "", None, "func"), ("APPS", "@apps", "", None, "accent"),
        ("PRGM", "@prgm", "", None, "func"), ("VARS", "@vars", "", None, "func"),
        ("CLEAR", "@clear", "", None, "func"),
    ])
    row(356, [
        ("x⁻¹", "^-1", "MATRIX", None, "func"),
        ("SIN", "sin(", "SIN⁻¹", "asin(", "func"),
        ("COS", "cos(", "COS⁻¹", "acos(", "func"),
        ("TAN", "tan(", "TAN⁻¹", "atan(", "func"),
        ("^", "^", "π", "pi", "func"),
    ])
    row(394, [
        ("x²", "^2", "√", "sqrt(", "func"),
        (",", ",", "EE", None, "func"),
        ("(", "(", "{", None, "func"),
        (")", ")", "}", None, "func"),
        ("÷", "/", "e", None, "accent"),
    ])
    row(432, [
        ("LOG", "log10(", "10ˣ", "10^(", "func"),
        ("7", "7", "", None, "num"), ("8", "8", "", None, "num"),
        ("9", "9", "", None, "num"), ("×", "*", "[", None, "accent"),
    ])
    row(470, [
        ("LN", "ln(", "eˣ", "exp(", "func"),
        ("4", "4", "", None, "num"), ("5", "5", "", None, "num"),
        ("6", "6", "", None, "num"), ("−", "-", "]", None, "accent"),
    ])
    row(508, [
        ("STO→", "@sto", "RCL", None, "func"),
        ("1", "1", "", None, "num"), ("2", "2", "", None, "num"),
        ("3", "3", "", None, "num"), ("+", "+", "MEM", None, "accent"),
    ])
    row(546, [
        ("ON", "@on", "OFF", None, "func"),
        ("0", "0", "", None, "num"), (".", ".", "", None, "num"),
        ("(-)", "-", "ANS", "Ans", "num"),
        ("ENTER", "@enter", "ENTRY", "@entry", "accent"),
    ])
    return keys


_STUB = {"@statplot", "@format", "@calc", "@ins", "@alpha", "@prgm",
         "@vars", "@sto"}

# Faithful TI-83/84 menus. Each item is (label, paste) — `paste` is the token
# inserted onto the entry line (TI behaviour), or None for an item we render but
# can't evaluate (shows the label as a message). Tokens are chosen so the ones
# our evaluator supports actually compute; calculus/RNG/list items stay None.
MENUS = {
    "math": {"title": "MATH", "tabs": [
        ("MATH", [("▶Frac", None), ("▶Dec", None), ("³", "^3"), ("³√(", "cbrt("),
                  ("ˣ√", "xroot("), ("fMin(", None), ("fMax(", None),
                  ("nDeriv(", None), ("fnInt(", None), ("Σ(", None),
                  ("logBASE(", "logBASE(")]),
        ("NUM", [("abs(", "abs("), ("round(", "round("), ("iPart(", "iPart("),
                 ("fPart(", "fPart("), ("int(", "int("), ("min(", "min("),
                 ("max(", "max("), ("lcm(", "lcm("), ("gcd(", "gcd("),
                 ("remainder(", "remainder(")]),
        ("CPX", [("conj(", None), ("real(", None), ("imag(", None),
                 ("angle(", None), ("abs(", "abs("), ("▶Rect", None),
                 ("▶Polar", None)]),
        ("PRB", [("rand", None), ("nPr", "perm("), ("nCr", "comb("),
                 ("!", "factorial("), ("randInt(", None), ("randNorm(", None),
                 ("randBin(", None)]),
    ]},
    "stat": {"title": "STAT", "tabs": [
        ("EDIT", [("Edit", None), ("SortA(", None), ("SortD(", None),
                  ("ClrList", None), ("SetUpEditor", None)]),
        ("CALC", [("1-Var Stats", None), ("2-Var Stats", None), ("Med-Med", None),
                  ("LinReg(ax+b)", None), ("QuadReg", None), ("CubicReg", None),
                  ("QuartReg", None), ("LinReg(a+bx)", None), ("LnReg", None),
                  ("ExpReg", None), ("PwrReg", None), ("Logistic", None),
                  ("SinReg", None)]),
        ("TESTS", [("Z-Test…", None), ("T-Test…", None), ("2-SampZTest…", None),
                   ("2-SampTTest…", None), ("1-PropZTest…", None),
                   ("2-PropZTest…", None), ("ZInterval…", None),
                   ("TInterval…", None), ("LinRegTTest…", None)]),
    ]},
    "apps": {"title": "APPLICATIONS", "tabs": [
        ("APPS", [("Finance", None), ("CabriJr", None), ("CelSheet", None),
                  ("Conics", None), ("EasyData", None), ("Inequalz", None),
                  ("PlySmlt2", None), ("Prob Sim", None), ("Science Tools", None),
                  ("Transfrm", None)]),
    ]},
}


class TIScreen(QWidget):
    """The LCD: renders home / Y-editor / graph / trace / table from the engine."""

    def __init__(self, faceplate) -> None:
        super().__init__(faceplate)
        self._fp = faceplate
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    @property
    def _bg(self) -> QColor:
        return _CE_BG if self._fp.color else _LCD_BG

    def _trace_colour(self, idx: int) -> QColor:
        if self._fp.color:
            return _TRACE_COLOURS[(idx - 1) % len(_TRACE_COLOURS)]
        return _LCD_INK

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        p.setPen(QPen(_LCD_INK, 1))
        mode = self._fp.mode
        if mode == "menu":
            self._paint_menu(p)
        elif mode in ("graph", "trace"):
            self._paint_graph(p)
        elif mode == "yeditor":
            self._paint_yeditor(p)
        elif mode == "table":
            self._paint_table(p)
        else:
            self._paint_home(p)
        flags = []
        if self._fp.shift:
            flags.append("2nd")
        if self._fp.message:
            flags.append(self._fp.message)
        if flags:
            self._indicator(p, "  ".join(flags))
        p.end()

    def _font(self, px: int = 13) -> QFont:
        f = QFont("Consolas")
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPixelSize(max(9, int(px * self.height() / 150)))
        return f

    def _indicator(self, p, text: str) -> None:
        p.setFont(self._font(11))
        p.setPen(QPen(_LCD_INK, 1))
        p.drawText(self.width() - 6 - p.fontMetrics().horizontalAdvance(text), 13, text)

    def _paint_home(self, p) -> None:
        p.setFont(self._font())
        fm = p.fontMetrics()
        step = fm.height()
        y = step
        for entry, result in self._fp.engine.history()[-5:]:
            p.drawText(6, y, entry)
            y += step
            p.drawText(self.width() - 6 - fm.horizontalAdvance(result), y, result)
            y += step
        p.drawText(6, y, f">{self._fp.input}_")

    def _paint_yeditor(self, p) -> None:
        p.setFont(self._font())
        step = p.fontMetrics().height() + 2
        y = step
        p.drawText(6, y, "Plot1 Plot2 Plot3")
        for i in range(1, 7):
            y += step
            cur = (i == self._fp.y_index)
            text = self._fp.input if cur else self._fp.engine.get_function(i)
            p.setPen(QPen(self._trace_colour(i), 1))
            marker = "►" if cur else " "
            p.drawText(6, y, f"{marker}Y{i}={text}{'_' if cur else ''}")

    def _paint_menu(self, p) -> None:
        m = self._fp._menu
        p.setFont(self._font(12))
        fm = p.fontMetrics()
        step = fm.height()
        # tab header — current tab inverse-highlighted
        x = 6
        for i, (name, _items) in enumerate(m["tabs"]):
            w = fm.horizontalAdvance(name)
            if i == m["tab"]:
                p.fillRect(x - 3, 2, w + 6, step + 2, _LCD_INK)
                p.setPen(self._bg)
                p.drawText(x, step, name)
                p.setPen(_LCD_INK)
            else:
                p.drawText(x, step, name)
            x += w + 12
        p.drawLine(0, step + 5, self.width(), step + 5)
        # items, windowed so the selection is always visible
        items = m["tabs"][m["tab"]][1]
        avail = self.height() - (step + 10)
        per = max(1, avail // step)
        start = m["sel"] - per + 1 if m["sel"] >= per else 0
        y = step * 2 + 8
        for i in range(start, min(len(items), start + per)):
            label = items[i][0]
            line = f"{(i + 1) % 10}:{label}"
            if i == m["sel"]:
                p.fillRect(4, y - step + 4, self.width() - 8, step, _LCD_INK)
                p.setPen(self._bg)
                p.drawText(8, y, line)
                p.setPen(_LCD_INK)
            else:
                p.drawText(8, y, line)
            y += step

    def _paint_table(self, p) -> None:
        p.setFont(self._font(12))
        step = p.fontMetrics().height()
        y = step
        for r in self._fp.engine.table(0, 1, 7):
            p.drawText(6, y, "  ".join(f"{c:>7}" for c in r))
            y += step

    def _paint_graph(self, p) -> None:
        w, h = self.width(), self.height()
        eng = self._fp.engine
        sx, sy = w / SCREEN_W, h / SCREEN_H
        axes = eng.axes_pixels()
        grid = QColor(0xb0, 0xb0, 0xb0) if self._fp.color else QColor(0x5a, 0x6a, 0x55)
        p.setPen(QPen(grid, 1))
        if axes.get("x_axis_row") is not None:
            p.drawLine(0, int(axes["x_axis_row"] * sy), w, int(axes["x_axis_row"] * sy))
        if axes.get("y_axis_col") is not None:
            p.drawLine(int(axes["y_axis_col"] * sx), 0, int(axes["y_axis_col"] * sx), h)
        from .._qtcompat import QPointF
        for idx, pts in eng.graph_pixels().items():
            p.setPen(QPen(self._trace_colour(idx), max(1.0, sx)))
            last = None
            for px, py in pts:
                X, Y = px * sx, py * sy
                if last is not None:
                    p.drawLine(QPointF(*last), QPointF(X, Y))
                last = (X, Y)
        if self._fp.mode == "trace":
            pt = self._fp.trace_point()
            if pt is not None:
                x, y, px, py = pt
                cx, cy = px * sx, py * sy
                p.setPen(QPen(self._trace_colour(self._fp.trace_fn), 1))
                p.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))
                p.drawLine(QPointF(cx, cy - 5), QPointF(cx, cy + 5))
                p.setFont(self._font(12))
                p.setPen(QPen(_LCD_INK, 1))
                p.drawText(4, 14, f"Y{self._fp.trace_fn} X={x:.4g} Y={y:.4g}")
        p.setPen(QPen(_LCD_INK, 1))
        p.setFont(self._font(11))
        win = eng.window
        p.drawText(4, h - 4, f"X[{win.xmin:g},{win.xmax:g}] Y[{win.ymin:g},{win.ymax:g}]")


class TIFaceplate(QWidget):
    def __init__(self, parent=None, skin: str = "ti83") -> None:
        super().__init__(parent)
        self.engine = TIEngine()
        self.mode = "home"
        self.input = ""
        self.message = ""
        self.y_index = 1
        self.shift = ""            # "" | "2nd"
        self.trace_fn = 1
        self.trace_col = SCREEN_W // 2
        self._menu = None          # active MATH/STAT/APPS menu, or None
        self._menu_prev = "home"
        self._skin_key = skin if skin in SKINS else "ti83"
        self._skin = SKINS[self._skin_key]
        self._colors = _SKIN_COLORS[self._skin_key]
        self.color = self._skin[4]
        self._keys = _build_keys(self._skin[3])
        self._scale = 1.0
        self._ox = self._oy = 0
        self._pressed: "_Key | None" = None
        self._base = self._compose_base()
        self.setMinimumSize(_CANVAS_W // 2, _CANVAS_H // 2)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._screen = TIScreen(self)
        self._recompute_geometry()

    # -- interop -----------------------------------------------------------

    def value(self) -> float:
        return self.engine.ans

    def set_value(self, v: float) -> None:
        self.input = repr(v)
        self.mode = "home"
        self._screen.update()

    def sizeHint(self) -> QSize:
        return QSize(_CANVAS_W, _CANVAS_H)

    # -- base composition --------------------------------------------------

    def _compose_base(self) -> QPixmap:
        name, body, accent, _win, _color = self._skin
        pm = QPixmap(_CANVAS_W, _CANVAS_H)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(body))
        p.drawRoundedRect(QRectF(0, 0, _CANVAS_W, _CANVAS_H), 22, 22)
        p.setBrush(QColor(body).darker(118))
        p.drawRoundedRect(QRectF(6, 6, _CANVAS_W - 12, _CANVAS_H - 12), 18, 18)
        # brand
        bf = QFont(); bf.setBold(True); bf.setPointSizeF(11)
        p.setFont(bf); p.setPen(QColor(accent))
        p.drawText(QRectF(0, 8, _CANVAS_W, 22), int(Qt.AlignmentFlag.AlignCenter), name)
        # screen bezel + recess
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0x0a, 0x0c, 0x0f))
        p.drawRoundedRect(QRectF(_SCR_X - 10, _SCR_Y - 10, _SCR_W + 20, _SCR_H + 20), 8, 8)
        p.setBrush(_CE_BG if self.color else _LCD_BG)
        p.drawRect(QRectF(_SCR_X, _SCR_Y, _SCR_W, _SCR_H))
        for key in self._keys:
            self._draw_key(p, key)
        p.end()
        return pm

    def _draw_key(self, p: QPainter, key: "_Key") -> None:
        cap = self._colors[key.kind]
        cap_c = QColor(cap)
        fg = _text_color(cap)
        # 2nd legend printed above the key, on the body (matches the 2nd-key colour).
        if key.second_label:
            lf = QFont(); lf.setPointSizeF(6.2)
            p.setFont(lf); p.setPen(QColor(self._colors["second"]))
            p.drawText(QRectF(key.x - 4, key.y - 12, key.w + 8, 11),
                       int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom),
                       key.second_label)
        # cap with a soft top-down gradient + dark outline + drop shadow
        rect = QRectF(key.x, key.y, key.w, key.h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawRoundedRect(rect.translated(0, 1.6), 5, 5)
        grad = QLinearGradient(key.x, key.y, key.x, key.y + key.h)
        grad.setColorAt(0.0, cap_c.lighter(122))
        grad.setColorAt(0.5, cap_c)
        grad.setColorAt(1.0, cap_c.darker(118))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(0x10, 0x12, 0x16), 1.0))
        p.drawRoundedRect(rect, 5, 5)
        # primary label
        size = 8.5 if len(key.label) <= 4 else (6.8 if len(key.label) <= 7 else 5.6)
        kf = QFont(); kf.setBold(True); kf.setPointSizeF(size)
        p.setFont(kf); p.setPen(fg)
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), key.label)

    # -- geometry ----------------------------------------------------------

    def _recompute_geometry(self) -> None:
        self._scale = min(self.width() / _CANVAS_W, self.height() / _CANVAS_H) or 1.0
        if self._scale <= 0:
            self._scale = 1.0
        self._ox = int((self.width() - _CANVAS_W * self._scale) / 2)
        self._oy = int((self.height() - _CANVAS_H * self._scale) / 2)
        self._screen.setGeometry(self._canvas_rect(_SCR_X + 3, _SCR_Y + 3,
                                                   _SCR_W - 6, _SCR_H - 6))

    def _canvas_rect(self, x, y, w, h) -> QRect:
        s = self._scale
        return QRect(self._ox + int(x * s), self._oy + int(y * s),
                     int(w * s), int(h * s))

    def resizeEvent(self, _event) -> None:  # noqa: N802
        self._recompute_geometry()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(0x0d, 0x0f, 0x12))
        target = QRect(self._ox, self._oy, int(_CANVAS_W * self._scale),
                       int(_CANVAS_H * self._scale))
        p.drawPixmap(target, self._base)
        # armed-2nd highlight
        if self.shift == "2nd":
            for k in self._keys:
                if k.action == "@2nd":
                    glow = QColor(self._colors["second"]); glow.setAlpha(120)
                    p.setPen(Qt.PenStyle.NoPen); p.setBrush(glow)
                    p.drawRoundedRect(self._canvas_rect(k.x, k.y, k.w, k.h), 5, 5)
        if self._pressed is not None:
            k = self._pressed
            p.fillRect(self._canvas_rect(k.x, k.y, k.w, k.h), QColor(0, 0, 0, 70))
        p.end()

    # -- mouse -------------------------------------------------------------

    def _key_at(self, pos: QPoint) -> "_Key | None":
        cx = (pos.x() - self._ox) / self._scale
        cy = (pos.y() - self._oy) / self._scale
        for key in self._keys:
            if key.x <= cx < key.x + key.w and key.y <= cy < key.y + key.h:
                return key
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._pressed = self._key_at(event.position().toPoint())
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        key = self._pressed
        self._pressed = None
        self.update()
        if key is not None and self._key_at(event.position().toPoint()) is key:
            self._press(key.action, key.second)

    # -- trace -------------------------------------------------------------

    def trace_point(self):
        expr = self.engine.get_function(self.trace_fn)
        if not expr:
            return None
        win = self.engine.window
        col = max(0, min(SCREEN_W - 1, self.trace_col))
        x = win.xmin + col / (SCREEN_W - 1) * (win.xmax - win.xmin)
        try:
            y = compile_expr(expr.replace("X", "x"))(x)
        except Exception:
            return None
        if not (win.ymin <= y <= win.ymax):
            return None
        py = round((win.ymax - y) / (win.ymax - win.ymin) * (SCREEN_H - 1))
        return x, y, col, py

    def _next_defined_fn(self, start: int) -> int:
        for off in range(10):
            i = (start - 1 + off) % 10 + 1
            if self.engine.get_function(i):
                return i
        return self.trace_fn

    # -- input / actions ---------------------------------------------------

    def _press(self, primary: str, second) -> None:
        if self.shift == "2nd" and second is not None:
            self._do(second)
        else:
            self._do(primary)

    def _do(self, action: str) -> None:
        if action == "@2nd":
            self.shift = "" if self.shift == "2nd" else "2nd"
            self.message = ""
            self.update()
            return
        if self.mode == "menu":
            self._menu_key(action)
            return
        self.message = ""
        if action in ("@math", "@apps", "@stat"):
            self._open_menu(action[1:])
            self._screen.update()
            self.update()
            return
        if not action.startswith("@"):
            self.input += action
        elif action == "@enter":
            self._enter()
        elif action == "@clear":
            self.input = ""
            if self.mode in ("graph", "trace"):
                self.mode = "home"
        elif action == "@del":
            self.input = self.input[:-1]
        elif action == "@on":
            self.input = ""
            self.mode = "home"
        elif action == "@mode":
            self.engine.degrees = not getattr(self.engine, "degrees", False)
            self.message = "DEG" if self.engine.degrees else "RAD"
        elif action == "@quit":
            self.mode = "home"
        elif action == "@entry":
            hist = self.engine.history()
            if hist:
                self.input = hist[-1][0]
        elif action in _STUB:
            self.message = action[1:].upper()
        elif action == "@yedit":
            self.mode = "yeditor"
            self.input = self.engine.get_function(self.y_index)
        elif action == "@graph":
            self._commit_yslot()
            self.mode = "graph"
        elif action == "@trace":
            self._commit_yslot()
            self.mode = "trace"
            self.trace_fn = self._next_defined_fn(self.trace_fn)
        elif action == "@table":
            self.mode = "table"
        elif action == "@window":
            self.engine.zoom_standard()
            self.mode = "graph"
        elif action == "@zoom":
            self._cycle_zoom()
            self.mode = "graph"
        elif action in ("@up", "@down", "@left", "@right"):
            self._arrow(action)
        self.shift = ""
        self._screen.update()
        self.update()

    # -- MATH / STAT / APPS menus -----------------------------------------

    def _open_menu(self, kind: str) -> None:
        spec = MENUS[kind]
        self._menu_prev = self.mode if self.mode in ("home", "yeditor") else "home"
        self._menu = {
            "title": spec["title"],
            "tabs": [(name, list(items)) for name, items in spec["tabs"]],
            "tab": 0, "sel": 0}
        self.mode = "menu"

    def _close_menu(self) -> None:
        self.mode = self._menu_prev
        self._menu = None

    def _menu_select(self) -> None:
        label, paste = self._menu["tabs"][self._menu["tab"]][1][self._menu["sel"]]
        self._close_menu()
        if paste is not None:
            self.input += paste
        else:
            self.message = label

    def _menu_key(self, action: str) -> None:
        m = self._menu
        items = m["tabs"][m["tab"]][1]
        if action == "@left":
            m["tab"] = (m["tab"] - 1) % len(m["tabs"])
            m["sel"] = 0
        elif action == "@right":
            m["tab"] = (m["tab"] + 1) % len(m["tabs"])
            m["sel"] = 0
        elif action == "@up":
            m["sel"] = (m["sel"] - 1) % len(items)
        elif action == "@down":
            m["sel"] = (m["sel"] + 1) % len(items)
        elif action in ("@clear", "@quit", "@on"):
            self._close_menu()
        elif action == "@enter":
            self._menu_select()
        elif not action.startswith("@") and action.isdigit():
            idx = 9 if action == "0" else int(action) - 1
            if idx < len(items):
                m["sel"] = idx
                self._menu_select()
        elif action in ("@graph", "@yedit", "@window", "@trace", "@table", "@zoom"):
            self._close_menu()
            self._do(action)
            return
        self._screen.update()
        self.update()

    def _enter(self) -> None:
        if self.mode == "yeditor":
            self._commit_yslot()
            self.y_index = self.y_index % 10 + 1
            self.input = self.engine.get_function(self.y_index)
        else:
            self.engine.home_eval(self.input)
            self.input = ""
            self.mode = "home"

    def _commit_yslot(self) -> None:
        if self.mode == "yeditor":
            try:
                self.engine.set_function(self.y_index, self.input)
            except Exception:
                pass

    def _cycle_zoom(self) -> None:
        order = ["standard", "decimal", "fit"]
        nxt = order[(order.index(getattr(self, "_zoom", "fit")) + 1) % 3]
        self._zoom = nxt
        {"standard": self.engine.zoom_standard,
         "decimal": self.engine.zoom_decimal,
         "fit": self.engine.zoom_fit}[nxt]()

    def _arrow(self, action: str) -> None:
        if self.mode == "trace":
            if action == "@left":
                self.trace_col = max(0, self.trace_col - 1)
            elif action == "@right":
                self.trace_col = min(SCREEN_W - 1, self.trace_col + 1)
            elif action in ("@up", "@down"):
                self.trace_fn = self._next_defined_fn(self.trace_fn % 10 + 1)
            return
        if self.mode == "yeditor":
            if action == "@right":
                self._commit_yslot()
                self.y_index = self.y_index % 10 + 1
            elif action == "@left":
                self._commit_yslot()
                self.y_index = (self.y_index - 2) % 10 + 1
            self.input = self.engine.get_function(self.y_index)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        text, key = event.text(), event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._do("@enter")
        elif key == Qt.Key.Key_Backspace:
            self._do("@del")
        elif key == Qt.Key.Key_Left:
            self._do("@left")
        elif key == Qt.Key.Key_Right:
            self._do("@right")
        elif key == Qt.Key.Key_Up:
            self._do("@up")
        elif key == Qt.Key.Key_Down:
            self._do("@down")
        elif text and text in "0123456789.+-*/^()xX":
            self._do("X" if text in "xX" else text)
        else:
            super().keyPressEvent(event)
