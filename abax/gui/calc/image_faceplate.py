"""Image-based Voyager faceplate — composites faceplate art from an EXTERNAL folder.

abax ships **no** calculator artwork. This widget loads a faceplate image set
(background + optional legend overlay + per-key cap PNGs, described by a Nonpareil
KML) from a directory the user points at — e.g. their own faceplate assets
— via :func:`abax.core.calc.voyager_layout.parse_layout`, and renders it over a
abax keypad (:class:`abax.core.calc.voyager.VoyagerKeypad` /
:class:`abax.core.calc.rpn16.Voyager16Keypad`). Clicks are hit-tested against the KML
button rectangles and routed to ``keypad.press(number)``.

Derived from the author's earlier ``image_faceplate`` work, but the HP badge /
branding rendering is intentionally omitted and the live LCD is a plain QLabel —
no trademark is drawn by abax.
"""

from __future__ import annotations

import os
from pathlib import Path

from .._qtcompat import (
    QColor,
    QFont,
    QImage,
    QLabel,
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
from ...core.calc.voyager_layout import Layout, parse_layout

_SURROUND = QColor(18, 18, 20)
_LCD_BG = "#0c1410"
_LCD_ON = "#7bf2a8"
_LCD_INSET_X = 0.03
_LCD_INSET_Y = 0.10


def find_assets_dir(settings_dir: str = "", model: str = "16c") -> "Path | None":
    """Resolve an external faceplate-asset directory for ``model``.

    Search order: an explicit ``settings_dir``; the ``ABAX_FACEPLATE_DIR`` env var
    (both point at an assets root holding per-model subfolders, e.g.
    ``…/qrpn/assets/voyager``); a local ``qrpn-voyager``/``qv`` checkout next to the
    working directory or the abax tree; then any assets fetched into abax's cache.
    Returns the directory with the model's KML + ``background.png``, or ``None``.
    abax bundles no artwork and never copies these files; it only reads them in place.
    """
    # 1) An explicitly configured folder (setting, then env var) WINS — and a
    #    folder pointing ABOVE the assets root still resolves: users pick the
    #    qrpn-voyager checkout (or its qrpn/ package dir) rather than
    #    .../qrpn/assets/voyager, so after the direct candidates we search a
    #    few levels down (bounded, so a big tree stays cheap).
    for base in (settings_dir, os.environ.get("ABAX_FACEPLATE_DIR", "")):
        if not base:
            continue
        for cand in (Path(base) / model, Path(base)):
            if _has_art(cand):
                return cand
        found = _deep_find_model(Path(base), model)
        if found is not None:
            return found
    # 2) A local qrpn-voyager / qv checkout kept beside the project or working
    #    dir — contributors who have it handy get the artwork with no config.
    candidates: list[Path] = []
    rel = Path("qrpn") / "assets" / "voyager" / model
    roots = [Path.cwd(), Path.cwd().parent]
    _anc = Path(__file__).resolve().parents
    if len(_anc) > 3:
        roots.append(_anc[3])  # a sibling of the abax project tree
    for root in roots:
        candidates += [root / "qrpn-voyager" / rel, root / "qv" / rel]
    # 3) assets the user fetched from a GitHub repo into the cache (Tools → Fetch…)
    try:
        from ...core import faceplate_assets

        cached = faceplate_assets.model_dir(model)
        if cached is not None:
            candidates.append(cached)
    except Exception:
        pass
    for cand in candidates:
        if _has_art(cand):
            return cand
    return None


def _has_art(cand: "Path") -> bool:
    """True when ``cand`` holds a faceplate (background.png + a KML layout)."""
    try:
        return (cand.is_dir() and (cand / "background.png").exists()
                and any(cand.glob("*.kml")))
    except OSError:
        return False


def _deep_find_model(root: "Path", model: str, max_depth: int = 4) -> "Path | None":
    """Bounded walk under ``root`` for a ``<model>/`` dir holding faceplate art."""
    try:
        if not root.is_dir():
            return None
        base_depth = len(root.resolve().parts)
    except OSError:
        return None
    for dirpath, dirnames, _files in os.walk(root):
        cur = Path(dirpath)
        if len(cur.parts) - base_depth >= max_depth:
            dirnames[:] = []            # too deep — stop descending here
            continue
        # Prune junk trees that can be huge and never hold artwork.
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".")
                       and d not in ("__pycache__", "node_modules", "build", "dist")]
        if model in dirnames:
            cand = cur / model
            try:
                if (cand / "background.png").exists() and any(cand.glob("*.kml")):
                    return cand
            except OSError:
                pass
    return None


class ImageFaceplate(QWidget):
    """Image-composited faceplate over a abax keypad (press/display interface)."""

    def __init__(self, keypad, asset_dir, parent: "QWidget | None" = None,
                 legends=None) -> None:
        super().__init__(parent)
        from .faceplate import _build_keymap

        self._keypad = keypad
        self._layout: Layout = parse_layout(asset_dir)
        self._base = self._compose_base()
        self._scale = 1.0
        self._ox = self._oy = 0
        self._pressed = None
        # keyboard / numpad entry: PC key -> button number (from the model legends)
        self._keymap = _build_keymap(legends) if legends else {}
        self._labels = ({p: n for n, (p, _g, _b) in legends.items()}
                        if legends else {})

        self.setObjectName("voyagerImageFaceplate")
        self.setAccessibleName("Voyager-style RPN calculator")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._lcd = QLabel(self)
        self._lcd.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._lcd.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lcd.setMinimumSize(0, 0)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setBold(True)
        self._lcd.setFont(font)
        self._lcd.setStyleSheet(
            f"QLabel {{ background: {_LCD_BG}; color: {_LCD_ON};"
            f" padding-right: 6px; }}")

        self._recompute_geometry()
        self._refresh_lcd()

    @property
    def keypad(self):
        return self._keypad

    def display(self) -> str:
        return self._keypad.display()

    # -- composition (user's image files; no abax-drawn branding) ----------
    def _compose_base(self) -> QPixmap:
        lay = self._layout
        canvas = QImage(lay.canvas_w, lay.canvas_h, QImage.Format.Format_ARGB32)
        canvas.fill(QColor(0, 0, 0, 0))
        painter = QPainter(canvas)
        painter.drawImage(0, 0, QImage(str(lay.background)))
        if lay.overlay is not None:
            painter.drawImage(0, 0, QImage(str(lay.overlay)))
        for btn in lay.buttons:
            img = QImage(str(lay.keys_dir / btn.image))
            if not img.isNull():
                painter.drawImage(QPoint(btn.x, btn.y), img)
        rim = max(2.0, lay.canvas_w * 0.013)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0), rim))
        painter.drawRoundedRect(
            QRectF(rim / 2.0, rim / 2.0,
                   lay.canvas_w - rim, lay.canvas_h - rim), 16.0, 16.0)
        painter.end()
        return QPixmap.fromImage(canvas)

    # -- geometry -----------------------------------------------------------
    def _recompute_geometry(self) -> None:
        lay = self._layout
        avail_w, avail_h = self.width(), self.height()
        self._scale = min(avail_w / lay.canvas_w, avail_h / lay.canvas_h) or 1.0
        if self._scale <= 0:
            self._scale = 1.0
        drawn_w, drawn_h = lay.canvas_w * self._scale, lay.canvas_h * self._scale
        self._ox = int((avail_w - drawn_w) / 2)
        self._oy = int((avail_h - drawn_h) / 2)
        ix = lay.lcd_w * _LCD_INSET_X
        iy = lay.lcd_h * _LCD_INSET_Y
        self._lcd.setGeometry(self._canvas_rect(
            lay.lcd_x + ix, lay.lcd_y + iy,
            lay.lcd_w - 2 * ix, lay.lcd_h - 2 * iy))

    def _canvas_rect(self, x, y, w, h) -> QRect:
        s = self._scale
        return QRect(self._ox + int(x * s), self._oy + int(y * s),
                     int(w * s), int(h * s))

    def sizeHint(self) -> QSize:
        return QSize(self._layout.canvas_w, self._layout.canvas_h)

    def minimumSizeHint(self) -> QSize:
        return QSize(self._layout.canvas_w // 2, self._layout.canvas_h // 2)

    def resizeEvent(self, _event) -> None:  # noqa: N802
        self._recompute_geometry()

    # -- keypad wiring ------------------------------------------------------
    def _refresh_lcd(self) -> None:
        self._lcd.setText(self._keypad.display())

    def _press(self, number: int) -> None:
        self._keypad.press(number)
        self._refresh_lcd()
        self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        from .faceplate import _button_for_event

        btn = _button_for_event(event, self._keymap, self._labels)
        if btn is not None:
            self._press(btn)
            event.accept()
        else:
            super().keyPressEvent(event)

    def set_model(self, keypad, asset_dir) -> None:
        self._keypad = keypad
        self._layout = parse_layout(asset_dir)
        self._base = self._compose_base()
        self._recompute_geometry()
        self._refresh_lcd()
        self.update()

    # -- mouse --------------------------------------------------------------
    def _button_at(self, pos: QPoint):
        cx = (pos.x() - self._ox) / self._scale
        cy = (pos.y() - self._oy) / self._scale
        for btn in self._layout.buttons:
            if btn.x <= cx < btn.x + btn.w and btn.y <= cy < btn.y + btn.h:
                return btn
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._pressed = self._button_at(event.position().toPoint())
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        btn = self._pressed
        self._pressed = None
        self.update()
        if btn is not None and self._button_at(event.position().toPoint()) is btn:
            self._press(btn.number)

    # -- painting -----------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), _SURROUND)
        target = QRect(self._ox, self._oy,
                       int(self._layout.canvas_w * self._scale),
                       int(self._layout.canvas_h * self._scale))
        painter.drawPixmap(target, self._base)
        if self._pressed is not None:
            painter.fillRect(self._canvas_rect(
                self._pressed.x, self._pressed.y,
                self._pressed.w, self._pressed.h), QColor(0, 0, 0, 70))
        painter.end()
