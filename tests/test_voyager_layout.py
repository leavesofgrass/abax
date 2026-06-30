"""Nonpareil-KML faceplate layout parser (PNG sizing + KML rects)."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from qcell.core.calc.voyager_layout import (
    Button,
    Layout,
    LayoutError,
    parse_layout,
    png_size,
)


def make_png(path: Path, w: int, h: int) -> None:
    """Write a minimal valid-enough PNG of size ``w`` x ``h``."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", w, h) + b"\x08\x06\x00\x00\x00"
    path.write_bytes(sig + ihdr + b"\x00\x00\x00\x00")


_KML = """\
display offset 73 29 size 305 55
button 36 image "key_36.png" offset 100 200
button 40 image "key_40.png" offset 150 250
button 99 image "key_99.png" offset 300 400
"""


def _make_asset_dir(tmp_path: Path, *, overlay: bool = True, kml: bool = True,
                    display: bool = True) -> Path:
    asset = tmp_path / "faceplate"
    asset.mkdir()
    make_png(asset / "background.png", 558, 350)
    if overlay:
        make_png(asset / "overlay.png", 558, 350)
    keys = asset / "keys"
    keys.mkdir()
    # key_36 present (39x72), key_40 present (39x33); key_99 deliberately absent.
    make_png(keys / "key_36.png", 39, 72)
    make_png(keys / "key_40.png", 39, 33)
    if kml:
        text = _KML if display else "\n".join(
            ln for ln in _KML.splitlines() if not ln.startswith("display"))
        (asset / "calc.kml").write_text(text, encoding="utf-8")
    return asset


def test_png_size_reads_synthetic_dimensions(tmp_path: Path) -> None:
    p = tmp_path / "a.png"
    make_png(p, 558, 350)
    assert png_size(p) == (558, 350)
    q = tmp_path / "b.png"
    make_png(q, 39, 72)
    assert png_size(q) == (39, 72)


def test_png_size_rejects_non_png(tmp_path: Path) -> None:
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not a png at all..............")
    with pytest.raises(LayoutError):
        png_size(bad)


def test_parse_layout_lcd_and_canvas(tmp_path: Path) -> None:
    layout = parse_layout(_make_asset_dir(tmp_path))
    assert isinstance(layout, Layout)
    assert (layout.lcd_x, layout.lcd_y, layout.lcd_w, layout.lcd_h) == (73, 29, 305, 55)
    assert (layout.canvas_w, layout.canvas_h) == (558, 350)
    assert layout.keys_dir == tmp_path / "faceplate" / "keys"
    assert layout.background == tmp_path / "faceplate" / "background.png"


def test_parse_layout_buttons(tmp_path: Path) -> None:
    layout = parse_layout(_make_asset_dir(tmp_path))
    assert len(layout.buttons) == 3
    by_num = {b.number: b for b in layout.buttons}

    b36 = by_num[36]
    assert isinstance(b36, Button)
    assert (b36.x, b36.y) == (100, 200)
    assert (b36.w, b36.h) == (39, 72)   # from key_36.png
    assert b36.image == "key_36.png"

    b40 = by_num[40]
    assert (b40.x, b40.y) == (150, 250)
    assert (b40.w, b40.h) == (39, 33)   # from key_40.png

    b99 = by_num[99]
    assert (b99.x, b99.y) == (300, 400)
    assert (b99.w, b99.h) == (39, 33)   # fallback: key_99.png absent


def test_parse_layout_overlay_present(tmp_path: Path) -> None:
    layout = parse_layout(_make_asset_dir(tmp_path, overlay=True))
    assert layout.overlay == tmp_path / "faceplate" / "overlay.png"


def test_parse_layout_overlay_absent(tmp_path: Path) -> None:
    layout = parse_layout(_make_asset_dir(tmp_path, overlay=False))
    assert layout.overlay is None


def test_parse_layout_requires_kml(tmp_path: Path) -> None:
    asset = _make_asset_dir(tmp_path, kml=False)
    with pytest.raises(LayoutError):
        parse_layout(asset)


def test_parse_layout_requires_display_line(tmp_path: Path) -> None:
    asset = _make_asset_dir(tmp_path, display=False)
    with pytest.raises(LayoutError):
        parse_layout(asset)


def test_parse_layout_requires_background(tmp_path: Path) -> None:
    asset = _make_asset_dir(tmp_path)
    (asset / "background.png").unlink()
    with pytest.raises(LayoutError):
        parse_layout(asset)
