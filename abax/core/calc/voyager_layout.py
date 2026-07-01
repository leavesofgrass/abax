"""Parse a Nonpareil Voyager KML into an image-based faceplate layout.

abax ships no calculator artwork itself: at runtime the user points it at an
external asset directory holding a Nonpareil-style ``.kml`` text layout, a
``background.png`` body, an optional ``overlay.png`` of printed legends, and a
``keys/`` subdir of per-key PNGs. This module reads that directory (stdlib
only, no image decoder) and returns the LCD rectangle plus the per-key button
rectangles -- position from the KML ``button`` lines, size from each key PNG.

Derived from the author's earlier calculator project; the hardware
keycode mapping is dropped here -- only button *numbers* are kept.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_BUTTON_RE = re.compile(
    r'button\s+(\d+)\s+image\s+"([^"]+)"\s+offset\s+(\d+)\s+(\d+)')
_DISPLAY_RE = re.compile(
    r'display\s+offset\s+(\d+)\s+(\d+)\s+size\s+(\d+)\s+(\d+)')

# Fallback key-cap size (common Voyager key) when a key PNG is absent.
_DEFAULT_KEY_W = 39
_DEFAULT_KEY_H = 33


class LayoutError(Exception):
    """Raised when an asset directory is not a usable faceplate layout."""


def png_size(path: str | Path) -> tuple[int, int]:
    """Return ``(width, height)`` of a PNG from its IHDR, without a decoder.

    Verifies the 8-byte PNG signature, then reads the big-endian width and
    height from bytes 16:24 of the IHDR chunk. Raises :class:`LayoutError`
    for anything that is not a PNG.
    """
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != _PNG_SIGNATURE:
        raise LayoutError(f"not a PNG: {path}")
    width, height = struct.unpack(">II", head[16:24])
    return width, height


@dataclass(frozen=True)
class Button:
    number: int
    x: int
    y: int
    w: int
    h: int
    image: str          # key image filename (relative to the keys/ dir)


@dataclass(frozen=True)
class Layout:
    canvas_w: int
    canvas_h: int
    lcd_x: int
    lcd_y: int
    lcd_w: int
    lcd_h: int
    buttons: list[Button]
    background: Path     # the body background PNG
    overlay: Path | None  # printed legends overlay, if present
    keys_dir: Path


def parse_layout(asset_dir: str | Path) -> Layout:
    """Build the :class:`Layout` from an external faceplate asset directory.

    ``asset_dir`` must contain exactly one ``*.kml`` file, a ``background.png``,
    an optional ``overlay.png``, and a ``keys/`` subdir of key PNGs. Raises
    :class:`LayoutError` if the KML, its ``display`` rect, or the background is
    missing.
    """
    asset_dir = Path(asset_dir)

    kmls = sorted(asset_dir.glob("*.kml"))
    if not kmls:
        raise LayoutError(f"no .kml file in {asset_dir}")
    kml_path = kmls[0]
    kml_text = kml_path.read_text(encoding="utf-8", errors="replace")

    m = _DISPLAY_RE.search(kml_text)
    if not m:
        raise LayoutError(f"no display rect in {kml_path}")
    lcd_x, lcd_y, lcd_w, lcd_h = (int(g) for g in m.groups())

    background = asset_dir / "background.png"
    if not background.exists():
        raise LayoutError(f"missing background.png in {asset_dir}")
    canvas_w, canvas_h = png_size(background)

    overlay = asset_dir / "overlay.png"
    keys_dir = asset_dir / "keys"

    buttons: list[Button] = []
    for match in _BUTTON_RE.finditer(kml_text):
        number = int(match.group(1))
        image = match.group(2)
        x, y = int(match.group(3)), int(match.group(4))
        key_png = keys_dir / image
        if key_png.exists():
            w, h = png_size(key_png)
        else:
            w, h = _DEFAULT_KEY_W, _DEFAULT_KEY_H
        buttons.append(Button(number=number, x=x, y=y, w=w, h=h, image=image))

    return Layout(
        canvas_w=canvas_w, canvas_h=canvas_h,
        lcd_x=lcd_x, lcd_y=lcd_y, lcd_w=lcd_w, lcd_h=lcd_h,
        buttons=buttons,
        background=background,
        overlay=overlay if overlay.exists() else None,
        keys_dir=keys_dir)
