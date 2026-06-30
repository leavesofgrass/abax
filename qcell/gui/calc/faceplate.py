"""Procedurally-drawn HP Voyager calculator faceplate for qcell.

Derived from the author's earlier ``vector_faceplate`` work. This draws a
de-branded Voyager calculator entirely with
``QPainter`` — a dark two-tone body, sculpted trapezoidal key caps with the HP-15C
functional legends (primary white, gold ``f``, blue ``g``), an LCD window, and a
``qv`` badge — using NO HP/Nonpareil artwork.

The qv original wired the keys to a Nut-engine + keycode + model stack and used a
417-line segmented LCD renderer. Here that is all replaced by qcell's pure-Python
HP-15C keypad (:class:`qcell.core.calc.voyager.VoyagerKeypad`) and a plain right-aligned
monospace :class:`QLabel` for the LCD phosphor window. Key positions are computed
from the Voyager button numbers (a functional 4×10 matrix) via
:func:`qcell.core.calc.voyager.grid_pos`, so this needs no KML files.

Qt comes through the binding shim (``qcell.gui._qtcompat``), like the rest of the
GUI, so this paint-heavy widget runs on PySide6 or PyQt6 unchanged.
"""

from __future__ import annotations

import math

from .._qtcompat import (
    QBrush,
    QColor,
    QFont,
    QLabel,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QWidget,
)
from ...core.calc.rpn12 import LEGENDS_12C, Voyager12Keypad
from ...core.calc.rpn16 import LEGENDS_16C, Voyager16Keypad
from ...core.calc.voyager import BUTTONS, LEGENDS_15C, VoyagerKeypad, grid_pos

# Virtual canvas + layout metrics (match qv's image-faceplate proportions).
_CANVAS_W, _CANVAS_H = 558, 350
_LCD_X, _LCD_Y, _LCD_W, _LCD_H = 73, 29, 305, 55
_LCD_INSET_X, _LCD_INSET_Y = 0.03, 0.10
_COL_X0, _COL_PITCH = 16, 54
_ROW_Y0, _ROW_PITCH = 130, 56
_KEY_W, _KEY_H = 39, 33

_ENTER = 36   # double-height key
_KEY_F = 42   # gold-shift key
_KEY_G = 43   # blue-shift key

# Fixed Voyager palette (qv used a FaceTheme; qcell's Theme has no faceplate
# tokens, so the calculator-specific colors are inlined here).
_BODY = "#23262b"
_BODY2 = "#16181c"
_BEZEL = "#0a0c0f"
_LCD_BG = "#0c1410"
_LCD_ON = "#7bf2a8"
_KEY_TOP = "#3a3e46"
_KEY_BOTTOM = "#2a2d34"
_KEY_OUTLINE = "#101216"
_PRIMARY = "#f2f2f2"
_GOLD = "#d9b25a"
_BLUE = "#7fb6e8"
_SURROUND = "#0d0f12"

# Legend tokens that read better as math/functional symbols.
_PRETTY = {
    "divide": "÷", "multiply": "×", "subtract": "−", "add": "+",
    "decimal": ".", "backspace": "←",
    "sqrt": "√x", "x^2": "x²", "10^x": "10ˣ", "e^x": "eˣ", "y^x": "yˣ",
    "x<>y": "x↔y", "x<>I": "x↔I", "x<>(i)": "x↔(i)", "x<>": "x↔",
    "Re<>Im": "Re↔Im", "Rdn": "R↓", "Rup": "R↑",
    "x<=y": "x≤y", "x/=y": "x≠y", "x/=0": "x≠0", "x=0": "x=0",
    "pi": "π", "Pi": "π", "Sigma+": "Σ+", "Sigma-": "Σ−", "CL Sigma": "CLΣ",
    "->R": "→R", "->P": "→P", "->H": "→H", "->H.MS": "→H.MS",
    "->DEG": "→DEG", "->RAD": "→RAD",
    "SIN-1": "SIN⁻¹", "COS-1": "COS⁻¹", "TAN-1": "TAN⁻¹",
    "HYP-1": "HYP⁻¹", "Delta%": "Δ%",
}


def _pretty(text: str) -> str:
    return _PRETTY.get(text, text)


def _rounded_poly(points: "list[tuple[float, float]]", r: float) -> QPainterPath:
    """A QPainterPath for a (convex) polygon with corners rounded by radius ``r``
    — used to draw the slightly trapezoidal Voyager key caps."""
    path = QPainterPath()

    def toward(a, b, dist):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1.0
        return QPointF(a[0] + dx / length * dist, a[1] + dy / length * dist)

    n = len(points)
    for i in range(n):
        p0, p1, p2 = points[(i - 1) % n], points[i], points[(i + 1) % n]
        start = toward(p1, p0, r)
        end = toward(p1, p2, r)
        if i == 0:
            path.moveTo(start)
        else:
            path.lineTo(start)
        path.quadTo(QPointF(p1[0], p1[1]), end)
    path.closeSubpath()
    return path


def _legend_size(text: str) -> float:
    """A gold/blue legend point size that keeps long labels inside the key span."""
    n = len(text)
    if n <= 6:
        return 6.0
    return max(4.2, 6.0 * 6.0 / n)


class _Key:
    __slots__ = ("number", "x", "y", "w", "h", "primary", "gold", "blue")

    def __init__(self, number, x, y, w, h, primary, gold, blue):
        self.number = number
        self.x, self.y, self.w, self.h = x, y, w, h
        self.primary, self.gold, self.blue = primary, gold, blue


def _build_keys(legends) -> "list[_Key]":
    keys: list[_Key] = []
    for number in BUTTONS:
        row, col = grid_pos(number)
        x = _COL_X0 + col * _COL_PITCH
        y = _ROW_Y0 + row * _ROW_PITCH
        h = _KEY_H + _ROW_PITCH if number == _ENTER else _KEY_H
        primary, gold, blue = legends.get(number, ("", "", ""))
        keys.append(_Key(number, x, y, _KEY_W, h,
                         _pretty(primary), _pretty(gold), _pretty(blue)))
    return keys


def _build_keymap(legends) -> "dict[str, int]":
    """PC-key text -> button number, derived from a model's legends.

    Covers the numeric keypad and main keyboard identically (digits, the four
    operators, decimal point) plus 16C hex letters (typed ``a``-``f`` → ``A``-``F``).
    Enter/Backspace are handled by name in :meth:`keyPressEvent`.
    """
    label = {p: n for n, (p, _g, _b) in legends.items()}
    m: dict[str, int] = {}
    for d in "0123456789":
        if d in label:
            m[d] = label[d]
    for txt, name in (("+", "add"), ("-", "subtract"), ("*", "multiply"),
                      ("/", "divide"), (".", "decimal")):
        if name in label:
            m[txt] = label[name]
    for c in "ABCDEF":               # 16C hex digits: lowercase a-f -> A-F
        if c in label:
            m[c.lower()] = label[c]
    return m


def _button_for_event(event, keymap: "dict[str, int]", labels: "dict[str, int]"):
    """Map a Qt key event to a button number (None if unmapped).

    Numpad and main-keyboard keys arrive with the same ``text`` so both work;
    Enter and Backspace are matched by their legend names.
    """
    key = event.key()
    text = event.text()
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        return labels.get("ENTER")
    if key == Qt.Key.Key_Backspace:
        return labels.get("backspace")
    if text:
        if text in keymap:
            return keymap[text]
        low = text.lower()
        if low in keymap:
            return keymap[low]
    return None


# Model registry: short key -> (legends dict, keypad factory, display name).
MODELS = {
    "16c": (LEGENDS_16C, Voyager16Keypad, "HP-16C"),
    "15c": (LEGENDS_15C, VoyagerKeypad, "HP-15C"),
    "12c": (LEGENDS_12C, Voyager12Keypad, "HP-12C"),
}
DEFAULT_MODEL = "16c"


class VoyagerFaceplate(QWidget):
    """Procedurally-drawn HP-15C Voyager faceplate over a :class:`VoyagerKeypad`.

    Mouse clicks on a key call ``keypad.press(number)`` and refresh the LCD; the
    ``f``/``g`` keys highlight when their shift is active.
    """

    def __init__(self, keypad=None, legends=None,
                 parent: "QWidget | None" = None, model_name: str = "15C") -> None:
        super().__init__(parent)
        self._keypad = keypad or VoyagerKeypad()
        self._legends = legends or LEGENDS_15C
        self._model_name = model_name
        self._keymap = _build_keymap(self._legends)
        self._labels = {p: n for n, (p, _g, _b) in self._legends.items()}
        self._keys = _build_keys(self._legends)
        self._base = self._compose_base()
        self._scale = 1.0
        self._ox = self._oy = 0
        self._pressed: "_Key | None" = None

        self.setObjectName("voyagerFaceplate")
        self.setAccessibleName(f"HP-{model_name} calculator")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._lcd = QLabel(self)
        self._lcd.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._lcd.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setBold(True)
        self._lcd.setFont(font)
        self._lcd.setStyleSheet(
            f"QLabel {{ background: {_LCD_BG}; color: {_LCD_ON};"
            f" padding-right: 6px; }}")

        self._recompute_geometry()
        self._refresh_lcd()

    # -- public API --------------------------------------------------------

    @property
    def keypad(self) -> "VoyagerKeypad":
        return self._keypad

    def display(self) -> str:
        """The current LCD text (mirrors ``keypad.display()``)."""
        return self._keypad.display()

    # -- composition -------------------------------------------------------

    def _compose_base(self) -> QPixmap:
        pm = QPixmap(_CANVAS_W, _CANVAS_H)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(_BODY))
        p.drawRoundedRect(QRectF(0, 0, _CANVAS_W, _CANVAS_H), 16, 16)
        p.setBrush(QColor(_BODY2))
        p.drawRoundedRect(QRectF(8, _ROW_Y0 - 18, _CANVAS_W - 16,
                                 _CANVAS_H - (_ROW_Y0 - 18) - 8), 14, 14)
        p.setBrush(QColor(_BEZEL))
        p.drawRoundedRect(QRectF(_LCD_X - 12, _LCD_Y - 12, _LCD_W + 24,
                                 _LCD_H + 24), 8, 8)
        p.setBrush(QColor(_LCD_BG))
        p.drawRect(QRectF(_LCD_X, _LCD_Y, _LCD_W, _LCD_H))
        for key in self._keys:
            self._draw_key(p, key)
        self._draw_badge(p)
        rim = max(2.0, _CANVAS_W * 0.013)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0), rim))
        p.drawRoundedRect(QRectF(rim / 2, rim / 2, _CANVAS_W - rim,
                                 _CANVAS_H - rim), 16, 16)
        p.end()
        return pm

    def _draw_key(self, p: QPainter, key: "_Key") -> None:
        x, y, w, h = key.x, key.y, key.w, key.h
        taper = w * 0.045
        skirt = min(max(8.0, h * 0.32), 12.0)
        top_h = h - skirt
        ct = taper * top_h / h
        top_c = QColor(_KEY_TOP)
        bot_c = QColor(_KEY_BOTTOM)
        front_c = bot_c.darker(150)
        corners = [(x, y), (x + w, y),
                   (x + w - taper, y + h), (x + taper, y + h)]
        cap_path = _rounded_poly(corners, 4.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 85))
        p.drawPath(_rounded_poly([(cx, cy + 1.8) for cx, cy in corners], 4.5))
        grad = QLinearGradient(x, y, x, y + h)
        grad.setColorAt(0.0, top_c.lighter(125))
        grad.setColorAt(0.16, top_c.lighter(107))
        grad.setColorAt(0.52, top_c)
        grad.setColorAt(max(0.0, top_h / h - 0.02), bot_c)
        grad.setColorAt(top_h / h, front_c.lighter(118))
        grad.setColorAt(1.0, front_c)
        p.setPen(QPen(QColor(_KEY_OUTLINE), 1.0))
        p.setBrush(QBrush(grad))
        p.drawPath(cap_path)
        # f/g active-shift highlight on the cap.
        if (key.number == _KEY_F and self._keypad.shift == "f") or \
           (key.number == _KEY_G and self._keypad.shift == "g"):
            glow = QColor(_GOLD if key.number == _KEY_F else _BLUE)
            glow.setAlpha(110)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawPath(cap_path)
        p.setPen(QPen(top_c.lighter(155), 1.2))
        p.drawLine(QPointF(x + 5, y + 1.6), QPointF(x + w - 5, y + 1.6))
        p.setPen(QPen(front_c.darker(115), 1.0))
        p.drawLine(QPointF(x + ct + 2, y + top_h),
                   QPointF(x + w - ct - 2, y + top_h))
        # Primary on the top face. f/g show their own colored glyph.
        if key.primary:
            if key.number == _KEY_F:
                colour = _GOLD
            elif key.number == _KEY_G:
                colour = _BLUE
            else:
                colour = _PRIMARY
            self._text(p, x, y, w, top_h, key.primary, colour, 8.0, bold=True)
        # Blue (g) legend ON the key's front face (as on the real Voyager).
        if key.blue:
            self._text(p, x - 3, y + top_h, w + 6, skirt, key.blue,
                       _BLUE, _legend_size(key.blue))
        # Gold (f) legend above the key, on the body (tight to the key top).
        if key.gold:
            self._text(p, x - 6, y - 10, w + 12, 9, key.gold,
                       _GOLD, _legend_size(key.gold))

    def _text(self, p: QPainter, x, y, w, h, text, colour, size,
              bold: bool = False) -> None:
        font = QFont()
        font.setStyleHint(QFont.StyleHint.SansSerif)
        font.setPointSizeF(size)
        font.setBold(bold)
        p.setFont(font)
        p.setPen(QColor(colour))
        p.drawText(QRectF(x, y, w, h), int(Qt.AlignmentFlag.AlignCenter), text)

    def _draw_badge(self, p: QPainter) -> None:
        """The 'qv' badge (QRPN-Voyager) — our own mark, not HP's."""
        cy = _LCD_Y + _LCD_H / 2.0
        side = _LCD_H * 0.84
        cx = (_LCD_X + _LCD_W + _CANVAS_W) / 2.0
        left, top = cx - side / 2.0, cy - side / 2.0
        plate = QLinearGradient(left, top, left, top + side)
        plate.setColorAt(0.0, QColor(0xea, 0xea, 0xec))
        plate.setColorAt(0.45, QColor(0xc6, 0xc6, 0xc8))
        plate.setColorAt(1.0, QColor(0x96, 0x96, 0x98))
        p.setPen(QPen(QColor(0x10, 0x10, 0x10), max(1.0, side * 0.05)))
        p.setBrush(QBrush(plate))
        p.drawRect(QRectF(left, top, side, side))
        disc = side * 0.50
        disc_cy = top + side * 0.33
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0x0a, 0x0a, 0x0a))
        p.drawEllipse(QRectF(cx - disc / 2, disc_cy - disc / 2, disc, disc))
        qv_font = QFont()
        qv_font.setStyleHint(QFont.StyleHint.SansSerif)
        qv_font.setWeight(QFont.Weight.Black)
        qv_font.setItalic(True)
        qv_font.setPointSizeF(disc * 0.46)
        path = QPainterPath()
        path.addText(0.0, 0.0, qv_font, "qv")
        br = path.boundingRect()
        path.translate(cx - br.center().x(), disc_cy - br.center().y())
        sheen = QLinearGradient(0.0, disc_cy - disc / 2, 0.0, disc_cy + disc / 2)
        sheen.setColorAt(0.0, QColor(0xf4, 0xf4, 0xf6))
        sheen.setColorAt(0.55, QColor(0xe8, 0xe8, 0xec))
        sheen.setColorAt(1.0, QColor(0x8c, 0x8c, 0x92))
        p.fillPath(path, QBrush(sheen))
        p.strokePath(path, QPen(QColor(0x16, 0x16, 0x1a), max(0.8, disc * 0.05)))
        div_y = top + side * 0.70
        p.setPen(QPen(QColor(0x0a, 0x0a, 0x0a), max(1.0, side * 0.045)))
        p.drawLine(QPointF(left + side * 0.14, div_y),
                   QPointF(left + side * 0.86, div_y))
        nfont = QFont()
        nfont.setStyleHint(QFont.StyleHint.SansSerif)
        nfont.setBold(False)
        nfont.setPointSizeF(side * 0.12)
        p.setFont(nfont)
        p.setPen(QColor(0x0c, 0x0c, 0x0c))
        p.drawText(QRectF(left, div_y, side, top + side - div_y),
                   int(Qt.AlignmentFlag.AlignCenter), self._model_name)

    # -- geometry / scaling ------------------------------------------------

    def _recompute_geometry(self) -> None:
        avail_w, avail_h = self.width(), self.height()
        self._scale = min(avail_w / _CANVAS_W, avail_h / _CANVAS_H) or 1.0
        if self._scale <= 0:
            self._scale = 1.0
        self._ox = int((avail_w - _CANVAS_W * self._scale) / 2)
        self._oy = int((avail_h - _CANVAS_H * self._scale) / 2)
        ix, iy = _LCD_W * _LCD_INSET_X, _LCD_H * _LCD_INSET_Y
        self._lcd.setGeometry(self._canvas_rect(
            _LCD_X + ix, _LCD_Y + iy, _LCD_W - 2 * ix, _LCD_H - 2 * iy))
        fs = max(8.0, 22.0 * self._scale)
        f = self._lcd.font()
        f.setPointSizeF(fs)
        self._lcd.setFont(f)

    def _canvas_rect(self, x, y, w, h) -> QRect:
        s = self._scale
        return QRect(self._ox + int(x * s), self._oy + int(y * s),
                     int(w * s), int(h * s))

    def sizeHint(self) -> QSize:
        return QSize(_CANVAS_W, _CANVAS_H)

    def minimumSizeHint(self) -> QSize:
        return QSize(_CANVAS_W // 2, _CANVAS_H // 2)

    def resizeEvent(self, _event) -> None:
        self._recompute_geometry()

    # -- keypad wiring -----------------------------------------------------

    def _refresh_lcd(self) -> None:
        self._lcd.setText(self._keypad.display())

    def _press(self, number: int) -> None:
        self._keypad.press(number)
        self._base = self._compose_base()   # f/g highlight may have changed
        self._refresh_lcd()
        self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        btn = _button_for_event(event, self._keymap, self._labels)
        if btn is not None:
            self._press(btn)
            event.accept()
        else:
            super().keyPressEvent(event)

    def set_model(self, keypad, legends, model_name: str = "15C") -> None:
        """Switch the calculator model (keypad + legends) and repaint."""
        self._keypad = keypad
        self._legends = legends
        self._model_name = model_name
        self._keymap = _build_keymap(legends)
        self._labels = {p: n for n, (p, _g, _b) in legends.items()}
        self._keys = _build_keys(legends)
        self._base = self._compose_base()
        self._recompute_geometry()
        self._refresh_lcd()
        self.update()

    # -- mouse -------------------------------------------------------------

    def _key_at(self, pos: QPoint) -> "_Key | None":
        cx = (pos.x() - self._ox) / self._scale
        cy = (pos.y() - self._oy) / self._scale
        for key in self._keys:
            if key.x <= cx < key.x + key.w and key.y <= cy < key.y + key.h:
                return key
        return None

    def mousePressEvent(self, event) -> None:
        self._pressed = self._key_at(event.position().toPoint())
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        key = self._pressed
        self._pressed = None
        self.update()
        if key is not None and self._key_at(event.position().toPoint()) is key:
            self._press(key.number)

    # -- painting ----------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(_SURROUND))
        target = QRect(self._ox, self._oy, int(_CANVAS_W * self._scale),
                       int(_CANVAS_H * self._scale))
        p.drawPixmap(target, self._base)
        if self._pressed is not None:
            k = self._pressed
            p.fillRect(self._canvas_rect(k.x, k.y, k.w, k.h),
                       QColor(0, 0, 0, 70))
        p.end()
